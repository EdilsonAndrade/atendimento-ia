import os
import psycopg
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from infrastructure.connection import DB_URI

print("🚀 [GLOBAL] Carregando modelo HuggingFace na memória...")
_GLOBAL_EMBEDDINGS = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")

# COMENTÁRIO: O modelo trunca silenciosamente qualquer texto acima do seu max_seq_length
# na hora de gerar o embedding (sem erro, sem aviso) — por isso o split usa o tokenizer
# real do modelo como length_function, garantindo que nenhum chunk ultrapasse essa janela.
_MAX_SEQ_LENGTH = _GLOBAL_EMBEDDINGS._client.get_max_seq_length() or 128
_TEXT_SPLITTER = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    _GLOBAL_EMBEDDINGS._client.tokenizer,
    chunk_size=_MAX_SEQ_LENGTH - 20,  # margem para os tokens especiais ([CLS]/[SEP])
    chunk_overlap=30,
)

class GerenciadorVetores:
    def __init__(self, collection_name: str = "interasis_knowledge"):
        """
        COMENTÁRIO: Inicializa o gerenciador conectando ao PostgreSQL (pgvector).
        Mantém o modelo local do HuggingFace para gerar os embeddings.
        """
        raw_db_url = os.getenv("DATABASE_URL", DB_URI)
        
        # COMENTÁRIO: Substitui a declaração do protocolo tradicional pelo driver psycopg3 se necessário
        if raw_db_url.startswith("postgresql://"):
            self.db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        else:
            self.db_url = raw_db_url
            
        self.collection_name = collection_name
        print("Inicializando modelo de Embeddings local HuggingFace...")
        # COMENTÁRIO: Conecta ao PostgreSQL através do PGVector
        self.banco = PGVector(
            embeddings=_GLOBAL_EMBEDDINGS,
            collection_name=self.collection_name,
            connection=self.db_url,
            use_jsonb=True,
        )

    def criar_banco_com_textos(self, textos: list, tenant_id: str, item_id: str = None):
        """
        COMENTÁRIO: Divide cada texto em chunks dentro da janela de tokens do modelo de
        embedding, converte em vetores via HuggingFace e salva no PostgreSQL, injetando
        o tenant_id nos metadados para garantir o isolamento entre clientes.

        Quando `item_id` é informado (EDI-39), cada chunk também carrega esse metadado,
        permitindo apagar/reindexar só os vetores daquele item (`deletar_por_item`) sem
        afetar os demais itens do mesmo tenant.
        """
        # COMENTÁRIO: Sem esse split, um texto maior que a janela do modelo (128 tokens)
        # era truncado silenciosamente na hora do embedding — só o início virava vetor.
        metadata_base = {"tenant_id": tenant_id}
        if item_id is not None:
            metadata_base["item_id"] = item_id

        documentos = [
            Document(
                page_content=pedaco,
                metadata={**metadata_base, "source_index": indice_texto, "chunk_index": indice_chunk},
            )
            for indice_texto, texto in enumerate(textos)
            for indice_chunk, pedaco in enumerate(_TEXT_SPLITTER.split_text(texto))
        ]

        print(
            f"Vetorizando e salvando {len(documentos)} chunks (a partir de {len(textos)} texto(s)) "
            f"para o tenant '{tenant_id}' no PostgreSQL..."
        )

        # COMENTÁRIO: Insere os documentos diretamente no banco de dados vetorial
        self.banco.add_documents(documentos)
        print("Vetores salvos com sucesso no PostgreSQL!")

    def deletar_por_tenant(self, tenant_id: str) -> None:
        """
        COMENTÁRIO: Remove todos os vetores de um tenant específico desta collection.
        Usado antes de reindexar (edição da base de conhecimento) e ao excluí-la —
        garante que a edição substitui o conteúdo anterior em vez de acumular vetores
        antigos e novos coexistindo.
        """
        delete_query = """
            DELETE FROM langchain_pg_embedding
            WHERE collection_id = (
                SELECT uuid FROM langchain_pg_collection WHERE name = %s
            )
            AND cmetadata->>'tenant_id' = %s;
        """
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(delete_query, (self.collection_name, tenant_id))

    def deletar_por_item(self, tenant_id: str, item_id: str) -> None:
        """
        COMENTÁRIO: Remove só os vetores de um item específico do tenant (EDI-39) —
        os demais itens do mesmo tenant permanecem intactos. Usado antes de reindexar
        (edição/substituição de um item) e ao excluí-lo individualmente.
        """
        delete_query = """
            DELETE FROM langchain_pg_embedding
            WHERE collection_id = (
                SELECT uuid FROM langchain_pg_collection WHERE name = %s
            )
            AND cmetadata->>'tenant_id' = %s
            AND cmetadata->>'item_id' = %s;
        """
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(delete_query, (self.collection_name, tenant_id, item_id))

    def search_context(self, pergunta: str, tenant_id: str, quantidade_resultados: int = 1):
        """
        COMENTÁRIO: Busca os textos mais semelhantes à pergunta, filtrando obrigatoriamente pelo tenant_id.
        """
        if not self.banco:
            raise ValueError("O banco vetorial não foi inicializado.")
        
        print(f"Buscando no banco por: '{pergunta}' (Tenant: {tenant_id})")
        
        # COMENTÁRIO: O parâmetro filter garante a busca isolada apenas nos registros daquele cliente
        resultados = self.banco.similarity_search(
            query=pergunta,
            k=quantidade_resultados,
            filter={"tenant_id": tenant_id}
        )
        
        # Retorna apenas o texto puro de cada resultado encontrado
        return [doc.page_content for doc in resultados]
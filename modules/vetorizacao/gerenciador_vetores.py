import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

class GerenciadorVetores:
    def __init__(self, pasta_db: str = "dados_vetoriais"):
        """
        Inicializa o gerenciador de banco vetorial.
        :param pasta_db: Nome da pasta onde o ChromaDB vai salvar os dados no seu notebook.
        """
        self.pasta_db = pasta_db
        print("Inicializando modelo de Embeddings local...")
        self.embeddings = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        self.banco = None
        
        # Se a pasta já existir, nós carregamos o banco existente automaticamente
        if os.path.exists(self.pasta_db):
            print(f"Carregando banco vetorial existente da pasta: {self.pasta_db}")
            self.banco = Chroma(persist_directory=self.pasta_db, embedding_function=self.embeddings)

    def criar_banco_com_textos(self, textos: list):
        """
        Pega uma lista de textos, converte em vetores e salva no disco.
        """
        print(f"Vetorizando e salvando {len(textos)} pedaços de texto em '{self.pasta_db}'...")
        self.banco = Chroma.from_texts(
            texts=textos,
            embedding=self.embeddings,
            persist_directory=self.pasta_db
        )
        print("Banco vetorial criado com sucesso no disco!")

    def buscar_contexto(self, pergunta: str, quantidade_resultados: int = 1):
        """
        Busca no banco os pedaços de texto mais parecidos com a pergunta.
        """
        if not self.banco:
            raise ValueError("O banco vetorial não foi inicializado ou está vazio.")
        
        print(f"Buscando no banco por: '{pergunta}'")
        resultados = self.banco.similarity_search(pergunta, k=quantidade_resultados)
        
        # Retorna apenas o texto puro de cada resultado encontrado
        return [doc.page_content for doc in resultados]
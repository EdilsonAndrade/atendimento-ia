# modules/vectorization/vector_manager.py
import os
from langchain_huggingface import HuggingFaceEmbeddings
# CORREÇÃO: Usando o pacote atualizado e definitivo recomendado pelo LangChain
from langchain_chroma import Chroma

class VectorManager:
    def __init__(self, db_directory: str):
        """
        Initializes the vector database manager for a specific directory.
        """
        self.db_directory = db_directory
        print(f"Initializing Multilingual Embeddings for: {self.db_directory}...")
        self.embeddings = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        self.db = None
        
        if os.path.exists(self.db_directory):
            self.db = Chroma(persist_directory=self.db_directory, embedding_function=self.embeddings)
        

    def save_documents(self, texts: list):
        """
        Converte textos em vetores e adiciona de forma incremental ao banco em disco,
        evitando sobrescritas destrutivas.
        """

        print(f"Preparando persistência para {len(texts)} chunks em '{self.db_directory}'...")

        # Se o banco já existe em disco, nós apenas carregamos a instância existente
        if os.path.exists(self.db_directory) and os.listdir(self.db_directory):
            self.db = Chroma(
                persist_directory=self.db_directory,
                embedding_function=self.embeddings
            )
            # Adiciona os novos textos de forma incremental à coleção existente
            self.db.add_texts(texts=texts)
            print("Dados adicionados de forma incremental com sucesso!")
        else:
            # Se o banco não existe, cria a estrutura inicial do zero
            self.db = Chroma.from_texts(
                texts=texts,
                embedding=self.embeddings,
                persist_directory=self.db_directory
            )
            print("Banco de dados vetorial inicial criado com sucesso no disco!")

    def search_context(self, query: str, num_results: int = 5):
        """
        Searches the database enforcing diversity using MMR.
        """
        if not self.db:
            raise ValueError(f"The database at {self.db_directory} is not initialized or empty.")
        
        # O MMR vai buscar candidatos e filtrar os mais diversos
        results = self.db.max_marginal_relevance_search(
            query, 
            k=num_results,
            fetch_k=20 
        )
        
        return [doc.page_content for doc in results]
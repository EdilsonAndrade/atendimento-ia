# modules/ia/chat_com_meus_dados.py
import os
import shutil
import pandas as pd
from pypdf import PdfReader

from langchain_huggingface import HuggingFaceEmbeddings
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document

def estruturar_bancos_de_dados():
    pasta_documentos = "data"
    
    # Definindo os caminhos dos nossos dois domínios separados
    pasta_operational_db = "db/operational_db"
    pasta_institutional_db = "db/institutional_db"

    print("=" * 60)
    print(" SINCRO-RAG: CONSTRUINDO ARQUITETURA MULTI-DOMÍNIO (DDD)")
    print("=" * 60)

    # 1. Limpeza dos bancos antigos
    for banco in [pasta_operational_db, pasta_institutional_db]:
        if os.path.exists(banco):
            print(f"-> Limpando banco antigo em '{banco}'...")
            shutil.rmtree(banco)

    embeddings_local = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
    quebrador_semantico = SemanticChunker(
        embeddings_local, 
        breakpoint_threshold_type="percentile"
    )

    # Listas separadas para cada domínio
    docs_operacionais = []
    docs_institucionais = []
    
    arquivos = os.listdir(pasta_documentos)

    print("\n[Fase 1] Lendo e classificando arquivos por Domínio...")
    for nome_arquivo in arquivos:
        caminho_completo = os.path.join(pasta_documentos, nome_arquivo)
        
        # DOMÍNIO OPERACIONAL (Tabelas e Dados Dinâmicos)
        if nome_arquivo.endswith(('.xlsx', '.xls', '.csv')):
            try:
                df = pd.read_csv(caminho_completo) if nome_arquivo.endswith('.csv') else pd.read_excel(caminho_completo)
                for _, linha in df.iterrows():
                    texto_linha = f"Arquivo: [{nome_arquivo}] -> " + ", ".join([f"{col}: {linha[col]}" for col in df.columns])
                    # Adicionamos o metadado de domínio para o futuro
                    docs_operacionais.append(Document(page_content=texto_linha, metadata={"dominio": "operacional", "source": nome_arquivo}))
                print(f"✔ [Operacional] Tabela '{nome_arquivo}' classificada ({len(df)} registros).")
            except Exception as e:
                print(f"❌ Erro ao ler tabela {nome_arquivo}: {e}")
            continue

        # DOMÍNIO INSTITUCIONAL (Documentos, Regras, Currículos)
        texto_bruto = ""
        if nome_arquivo.endswith('.txt'):
            with open(caminho_completo, 'r', encoding='utf-8') as f:
                texto_bruto = f.read()
        elif nome_arquivo.endswith('.pdf'):
            try:
                leitor_pdf = PdfReader(caminho_completo)
                texto_bruto = "".join([pag.extract_text() or "" for pag in leitor_pdf.pages])
            except Exception:
                continue

        if texto_bruto.strip():
            chunks = quebrador_semantico.split_text(texto_bruto)
            for chunk in chunks:
                texto_com_origem = f"Arquivo: [{nome_arquivo}] -> {chunk}"
                # Adicionamos o metadado de domínio para o futuro
                docs_institucionais.append(Document(page_content=texto_com_origem, metadata={"dominio": "institucional", "source": nome_arquivo}))
            print(f"✔ [Institucional] Arquivo '{nome_arquivo}' classificado ({len(chunks)} blocos).")

    print("\n[Fase 2] Salvando dados no Banco OPERACIONAL...")
    if docs_operacionais:
        gerenciador_op = GerenciadorVetores(pasta_db=pasta_operational_db)
        gerenciador_op.banco = gerenciador_op.banco or __import__('langchain_community').vectorstores.Chroma(persist_directory=pasta_operational_db, embedding_function=embeddings_local)
        gerenciador_op.banco.add_documents(docs_operacionais)
        print(f"-> {len(docs_operacionais)} blocos salvos no domínio Operacional.")
    else:
        print("-> Nenhum dado operacional encontrado.")

    print("\n[Fase 3] Salvando dados no Banco INSTITUCIONAL...")
    if docs_institucionais:
        gerenciador_inst = GerenciadorVetores(pasta_db=pasta_institutional_db)
        gerenciador_inst.banco = gerenciador_inst.banco or __import__('langchain_community').vectorstores.Chroma(persist_directory=pasta_institutional_db, embedding_function=embeddings_local)
        gerenciador_inst.banco.add_documents(docs_institucionais)
        print(f"-> {len(docs_institucionais)} blocos salvos no domínio Institucional.")
    else:
        print("-> Nenhum dado institucional encontrado.")

    print("\n" + "=" * 50)
    print(" ARQUITETURA MULTI-BANCO PRONTA COM SUCESSO!")
    print("=" * 50)

if __name__ == "__main__":
    estruturar_bancos_de_dados()
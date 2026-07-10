# modules/ia/chat_com_meus_dados.py
import os
import shutil
import pandas as pd
from pypdf import PdfReader

from langchain_community.embeddings import HuggingFaceEmbeddings
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores
from modules.ia.assistante_rag import AssistenteRAG
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document

def iniciar_sistema_completo():
    pasta_documentos = "data"
    pasta_banco = "db/banco_real"

    print("=" * 60)
    print(" SINCRO-RAG: PREPARANDO SEU ECOSSISTEMA LOCAL DE DADOS")
    print("=" * 60)

    if os.path.exists(pasta_banco):
        print(f"-> Limpando resquícios do banco antigo em '{pasta_banco}'...")
        shutil.rmtree(pasta_banco)

    embeddings_local = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
    quebrador_semantico = SemanticChunker(
        embeddings_local, 
        breakpoint_threshold_type="percentile"
    )

    documentos_para_o_banco = []
    arquivos = os.listdir(pasta_documentos)

    print("\n[Fase 1] Lendo e fatiando arquivos (Garantindo o 'Crachá' de Origem)...")
    for nome_arquivo in arquivos:
        caminho_completo = os.path.join(pasta_documentos, nome_arquivo)
        
        # 1. Tratamento de Tabelas
        if nome_arquivo.endswith(('.xlsx', '.xls', '.csv')):
            try:
                df = pd.read_csv(caminho_completo) if nome_arquivo.endswith('.csv') else pd.read_excel(caminho_completo)
                for _, linha in df.iterrows():
                    texto_linha = f"Arquivo: [{nome_arquivo}] -> " + ", ".join([f"{col}: {linha[col]}" for col in df.columns])
                    documentos_para_o_banco.append(Document(page_content=texto_linha))
                print(f"✔ Tabela '{nome_arquivo}' lida com sucesso.")
            except Exception as e:
                print(f"❌ Erro ao ler tabela {nome_arquivo}: {e}")
            continue

        # 2. Tratamento de Textos e PDFs
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

        # Fatiamento e injeção do crachá EM CADA PEDAÇO INDIVIDUAL
        if texto_bruto.strip():
            chunks = quebrador_semantico.split_text(texto_bruto)
            for chunk in chunks:
                # O PULO DO GATO: Cada bloco ganha o nome do arquivo para não perder o contexto
                texto_com_origem = f"Arquivo: [{nome_arquivo}] -> {chunk}"
                documentos_para_o_banco.append(Document(page_content=texto_com_origem))
            print(f"✔ Arquivo '{nome_arquivo}' fatiado em {len(chunks)} blocos semânticos puros.")

    print(f"\n[Fase 2] Indexando {len(documentos_para_o_banco)} blocos no ChromaDB...")
    gerenciador = GerenciadorVetores(pasta_db=pasta_banco)
    textos_finais = [doc.page_content for doc in documentos_para_o_banco]
    gerenciador.criar_banco_com_textos(textos_finais)

    print("\n[Fase 3] Carregando o Llama3/DeepSeek no Ollama...")
    assistente = AssistenteRAG(gerenciador_vetores=gerenciador, modelo_nome="llama3")

    print("\n" + "=" * 50)
    print(" ECOSSISTEMA RAG SEMÂNTICO PRONTO! DIGITE 'SAIR' PARA ENCERRAR.")
    print("=" * 50)

    while True:
        pergunta = input("\nPergunte algo sobre seus dados: ")
        if pergunta.strip().lower() == "sair":
            print("Encerrando o chat. Até logo!")
            break
        
        if not pergunta.strip():
            continue

        try:
            resposta = assistente.perguntar(pergunta)
            print(f"\n🤖 IA: {resposta}")
            print("=" * 50)
        except Exception as e:
            print(f"❌ Ocorreu um erro ao processar a resposta: {e}")

if __name__ == "__main__":
    iniciar_sistema_completo()
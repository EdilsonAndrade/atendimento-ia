# modules/vectorization/setup_tenant_database.py
import os
import pandas as pd
from pypdf import PdfReader
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores 

def initialize_tenant_data(tenant_id: str, pdf_path: str = None, excel_path: str = None, txt_path: str = None):
    """
    Função de Engenharia de Dados para processar e vetorizar os arquivos de um Tenant específico.
    Isola os dados criando coleções e diretórios exclusivos por cliente.
    """
    print("\n" + "=" * 60)
    print(f" INICIANDO INGESTÃO DE DADOS PARA O TENANT: [{tenant_id}]")
    print("=" * 60)

    if pdf_path is None and excel_path is None and txt_path is None:
        print("❌ ERRO: Pelo menos um dos arquivos (PDF, Excel ou TXT) deve ser fornecido.")
        return
    # ============================================================================
    # 1. PROCESSAMENTO E VETORIZAÇÃO DO PDF (DADOS INSTITUCIONAIS)
    # ============================================================================
    db_path = f"db/{tenant_id}/knowledge_db"
    
     
    print(f"\n[1/2] Processando PDF Institucional para: {db_path}")
    row_chunks_db = []
    if pdf_path:
         
        if (not os.path.exists(pdf_path)):
            print(f"❌ ERRO: Arquivo PDF não encontrado em: {pdf_path}")
            return

        # Lendo o PDF e extraindo o texto de cada página
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # Adicionamos metadados implícitos no chunk para ajudar o RAG
                chunk_formatado = f"[Documento: Currículo] [Página: {i+1}]\n{text.strip()}"
                row_chunks_db.append(chunk_formatado)

    else:
        print("⚠ PDF não fornecido.")

    # ============================================================================
    # 2. PROCESSAMENTO E VETORIZAÇÃO DO EXCEL (DADOS OPERACIONAIS)
    # ============================================================================
    
    # ============================================================================
    # 3. PROCESSAMENTO E VETORIZAÇÃO DO TXT (DADOS ADICIONAIS) para o RAG também em operacional
    # ============================================================================

    if txt_path:
        print(f"\n[3/3] Processando TXT Adicional para: {db_path}")

        if not os.path.exists(txt_path):
            print(f"❌ ERRO: Arquivo TXT não encontrado em: {txt_path}")
            return

        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()

        if text:
            row_chunks_db.append(f"[Dados Operacionais linhas TXT:]\n{text.strip()}")
            print(f" -> Sucesso! O TXT foi vetorizado.")
        else:
            print("⚠ Nenhum texto pôde ser extraído do TXT.")
    else:
        print("[-] Ignorando TXT (Não fornecido).")
   
    

    if excel_path:
        print(f"\n[3/3] Processando Planilha Excel para: {db_path}")
        if not os.path.exists(excel_path):
            print(f"❌ ERRO: Arquivo Excel não encontrado em: {excel_path}")
            return

        
        # Lendo a planilha de horários/serviços
        df = pd.read_excel(excel_path) if excel_path else pd.DataFrame()
    
        
        # Varre cada linha da planilha e transforma em uma frase descritiva rica para o RAG
        for index, row in df.iterrows():
            partes_linha = [f"{coluna}: {valor}" for coluna, valor in row.items() if pd.notna(valor)]
            linha_texto = " | ".join(partes_linha)
            # Contextualiza o chunk para que a busca semântica por IA funcione perfeitamente
            chunk_operacional = f"[Dados Operacionais] [Linha Planilha: {index+1}]\n{linha_texto}"
            row_chunks_db.append(chunk_operacional)
    else:
        print("⚠ Excell ignorado, não fornecido")

    if row_chunks_db:
        # COMENTÁRIO: Instancia o gerenciador de vetores conectado ao PostgreSQL (pgvector)
        gerenciador = GerenciadorVetores()
        
        # COMENTÁRIO: Salva todos os chunks extraídos passando o tenant_id para garantir o isolamento no banco
        gerenciador.criar_banco_com_textos(textos=row_chunks_db, tenant_id=tenant_id)
        
        print(f" -> Sucesso! {len(row_chunks_db)} chunks foram vetorizados e salvos no PostgreSQL para o tenant [{tenant_id}].")
        print("\n" + "=" * 60)
        print(f" INGESTÃO DO TENANT [{tenant_id}] CONCLUÍDA COM SUCESSO!")
        print("=" * 60)
    else:
        print(f" NÃO REALIZADA INGESTÃO DO TENANT - FALTA DE INFORMAÇÃO")



if __name__ == "__main__":
    # CONFIGURAÇÃO DOS CAMINHOS DOS SEUS ARQUIVOS BRUTOS DE TESTE
    # Ajuste os nomes e caminhos aqui abaixo se os seus arquivos originais tiverem nomes diferentes!
    ID_CLIENTE_TESTE = "987654"
    CAMINHO_TXT = "data/temp/987654/regras_api.txt"  # Onde está o seu PDF original
    

    initialize_tenant_data(
        tenant_id=ID_CLIENTE_TESTE,
        txt_path=CAMINHO_TXT,
    
    )
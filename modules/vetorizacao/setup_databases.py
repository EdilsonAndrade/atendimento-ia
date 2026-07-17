# modules/vectorization/setup_tenant_database.py
import os
import pandas as pd
from pypdf import PdfReader
from modules.vetorizacao.vector_manager import VectorManager

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
    inst_db_path = f"db/{tenant_id}/institutional_db"
    oper_db_path = f"db/{tenant_id}/operational_db"
     
    print(f"\n[1/2] Processando PDF Institucional para: {inst_db_path}")

    if pdf_path:
         
        if (not os.path.exists(pdf_path)):
            print(f"❌ ERRO: Arquivo PDF não encontrado em: {pdf_path}")
            return

        # Lendo o PDF e extraindo o texto de cada página
        reader = PdfReader(pdf_path)
        text_chunks = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # Adicionamos metadados implícitos no chunk para ajudar o RAG
                chunk_formatado = f"[Documento: Currículo] [Página: {i+1}]\n{text.strip()}"
                text_chunks.append(chunk_formatado)

        if text_chunks:
            # Instancia o gerenciador do ChromaDB na pasta isolada do cliente
            inst_manager = VectorManager(db_directory=inst_db_path)
            # Salva os pedaços de texto indexados no banco vetorial dele
            inst_manager.save_documents(text_chunks)
            print(f" -> Sucesso! {len(text_chunks)} páginas do PDF foram vetorizadas.")
        else:
            print("⚠ Nenhum texto pôde ser extraído do PDF.")

    # ============================================================================
    # 2. PROCESSAMENTO E VETORIZAÇÃO DO EXCEL (DADOS OPERACIONAIS)
    # ============================================================================
    
    # ============================================================================
    # 3. PROCESSAMENTO E VETORIZAÇÃO DO TXT (DADOS ADICIONAIS) para o RAG também em operacional
    # ============================================================================
    row_chunks_operational = []
    if txt_path:
        print(f"\n[3/3] Processando TXT Adicional para: {oper_db_path}")

        if not os.path.exists(txt_path):
            print(f"❌ ERRO: Arquivo TXT não encontrado em: {txt_path}")
            return

        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()

        if text:
            row_chunks_operational.append(f"[Dados Operacionais linhas TXT:]\n{text.strip()}")
            print(f" -> Sucesso! O TXT foi vetorizado.")
        else:
            print("⚠ Nenhum texto pôde ser extraído do TXT.")
   
    

    if excel_path and not os.path.exists(excel_path):
        print(f"❌ ERRO: Arquivo Excel não encontrado em: {excel_path}")
        return

    if excel_path is None:
        print("⚠ Aviso: Nenhum arquivo Excel fornecido.")

    # Lendo a planilha de horários/serviços
    df = pd.read_excel(excel_path) if excel_path else pd.DataFrame()
  
    
    # Varre cada linha da planilha e transforma em uma frase descritiva rica para o RAG
    for index, row in df.iterrows():
        partes_linha = [f"{coluna}: {valor}" for coluna, valor in row.items() if pd.notna(valor)]
        linha_texto = " | ".join(partes_linha)
        # Contextualiza o chunk para que a busca semântica por IA funcione perfeitamente
        chunk_operacional = f"[Dados Operacionais] [Linha Planilha: {index+1}]\n{linha_texto}"
        row_chunks_operational.append(chunk_operacional)

    if row_chunks_operational:
        # Instancia o gerenciador operacional na pasta isolada do cliente
        oper_manager = VectorManager(db_directory=oper_db_path)
        # Salva as linhas indexadas no banco vetorial operacional dele
        oper_manager.save_documents(row_chunks_operational)
        print(f" -> Sucesso! {len(row_chunks_operational)} linhas da planilha foram vetorizadas.")
    else:
        print("⚠ Nenhuma linha válida foi encontrada na planilha.")

    print("\n" + "=" * 60)
    print(f" INGESTÃO DO TENANT [{tenant_id}] CONCLUÍDA COM SUCESSO!")
    print("=" * 60)


if __name__ == "__main__":
    # CONFIGURAÇÃO DOS CAMINHOS DOS SEUS ARQUIVOS BRUTOS DE TESTE
    # Ajuste os nomes e caminhos aqui abaixo se os seus arquivos originais tiverem nomes diferentes!
    ID_CLIENTE_TESTE = "interasis_barber"
    CAMINHO_CURRICULO = "data/curriculum.pdf"  # Onde está o seu PDF original
    CAMINHO_PLANILHA = "data/Agenda de Horários - Barbearia (Exemplo).xlsx"   # Onde está o seu Excel original

    initialize_tenant_data(
        tenant_id=ID_CLIENTE_TESTE,
        pdf_path=CAMINHO_CURRICULO,
        excel_path=CAMINHO_PLANILHA
    )
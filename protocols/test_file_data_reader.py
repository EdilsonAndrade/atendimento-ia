import os
import pandas as pd
from pypdf import PdfReader


def testar_leitura_texto_ou_pdf(caminho_arquivo):
    """
    Testa a leitura de um arquivo de texto ou PDF e retorna o conteúdo como uma string.
    
    Args:
        caminho_arquivo (str): Caminho para o arquivo a ser lido.
        
    Returns:
        str: Conteúdo do arquivo como uma string.
    """
    # Verifica se o arquivo realmente existe
    if not os.path.exists(caminho_arquivo):
        print(f"Erro: O arquivo {caminho_arquivo} não foi encontrado!")
        return

    # Se for PDF
    if caminho_arquivo.endswith('.pdf'):
        leitor = PdfReader(caminho_arquivo)
        # Pega apenas o texto da primeira página como teste
        texto_primeira_pagina = leitor.pages[0].extract_text()
        print("Trecho inicial do PDF extraído com sucesso:")
        print(texto_primeira_pagina[:1000]) # Mostra os primeiros 1000 caracteres
        
    # Se for um arquivo de texto comum (.txt)
    elif caminho_arquivo.endswith('.txt'):
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            texto = f.read()
        print("Trecho inicial do TXT extraído com sucesso:")
        print(texto[:1000])


def testar_leitura_tabela(caminho_tabela):
        print(f"\n--- Lendo tabela: {caminho_tabela} ---")
        
        if not os.path.exists(caminho_tabela):
            print(f"Erro: A tabela {caminho_tabela} não foi encontrada!")
            return

        # Se for Excel
        if caminho_tabela.endswith('.xlsx') or caminho_tabela.endswith('.xls'):
            df = pd.read_excel(caminho_tabela)
        # Se for CSV
        elif caminho_tabela.endswith('.csv'):
            df = pd.read_csv(caminho_tabela)
        else:
            print("Formato de tabela não suportado neste teste.")
            return

        print("Estrutura da tabela lida com sucesso!")
        print("Colunas encontradas:", list(df.columns))
        print("Primeiras 3 linhas da tabela:")
        print(df.head(3))

# Execução do teste
if __name__ == "__main__":
    # COLOQUE AQUI O CAMINHO DE ALGUM ARQUIVO SEU PARA TESTAR:
    # Exemplo: testar_leitura_texto_ou_pdf("minha_pasta/documento.txt")
    # Exemplo: testar_leitura_tabela("minha_pasta/agenda.xlsx")
    
    print("Iniciando o teste de leitura de dados locais...")
    
    # leitura do arquvo curriculum.pdf que esta na pasta raiz/data
    
    testar_leitura_texto_ou_pdf("./data/curriculum.pdf")
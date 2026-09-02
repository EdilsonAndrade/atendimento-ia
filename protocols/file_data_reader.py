# modules/vetorizacao/leitor_pasta.py
import os
from typing import BinaryIO

import pandas as pd
from pypdf import PdfReader


def extract_text_from_pdf(file: BinaryIO) -> str:
    """Extrai o texto de todas as páginas de um PDF a partir de um stream binário."""
    leitor = PdfReader(file)
    texto_pdf = ""
    for pagina in leitor.pages:
        texto_extraido = pagina.extract_text()
        if texto_extraido:
            texto_pdf += texto_extraido + "\n"
    return texto_pdf.strip()


def _dataframe_to_lines(df: pd.DataFrame, origem: str) -> list:
    linhas_texto = []
    for _, linha in df.iterrows():
        partes_linha = [f"{coluna}: {linha[coluna]}" for coluna in df.columns]
        # Exemplo: "Serviço: Barba, Preço: 35, Tempo: 20 min"
        linhas_texto.append(f"Origem [{origem}] -> " + ", ".join(partes_linha))
    return linhas_texto


def extract_text_from_table(file: BinaryIO, filename: str) -> str:
    """Extrai o texto de uma tabela (CSV, XLS ou XLSX) a partir de um stream binário,
    convertendo cada linha em uma frase descritiva estruturada para o banco vetorial.
    Para arquivos Excel com múltiplas abas, todas as abas são lidas e identificadas
    na origem de cada linha (ex.: "arquivo.xlsx | aba: Serviços")."""
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(file)
        return "\n".join(_dataframe_to_lines(df, filename))

    planilhas = pd.read_excel(file, sheet_name=None)

    linhas_texto = []
    for nome_aba, df in planilhas.items():
        origem = f"{filename} | aba: {nome_aba}"
        linhas_texto.extend(_dataframe_to_lines(df, origem))

    return "\n".join(linhas_texto)


def extract_text_from_txt(file: BinaryIO) -> str:
    """Extrai o texto de um arquivo .txt a partir de um stream binário."""
    conteudo = file.read()
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("utf-8")
    return conteudo.strip()


class FileDataReader:
    def __init__(self, pasta_origem: str):
        """
        Inicializa o leitor apontando para a pasta onde estão seus arquivos reais.
        """
        self.pasta_origem = pasta_origem

    def ler_todos_os_arquivos(self) -> list:
        """
        Varre a pasta e extrai o texto de arquivos .txt, .pdf, .csv e .xlsx.
        Retorna uma lista de strings (textos).
        """
        if not os.path.exists(self.pasta_origem):
            print(f"Aviso: A pasta {self.pasta_origem} não existe. Criando pasta vazia...")
            os.makedirs(self.pasta_origem)
            return []

        todos_os_textos = []
        arquivos = os.listdir(self.pasta_origem)
        print(f"Encontrados {len(arquivos)} arquivos na pasta '{self.pasta_origem}'. Iniciando leitura...")

        for nome_arquivo in arquivos:
            caminho_completo = os.path.join(self.pasta_origem, nome_arquivo)

            # 1. Tratamento para arquivos de texto comuns
            if nome_arquivo.endswith('.txt'):
                try:
                    with open(caminho_completo, 'rb') as f:
                        conteudo = extract_text_from_txt(f)
                        if conteudo:
                            todos_os_textos.append(conteudo)
                            print(f"✔ Lido com sucesso: {nome_arquivo} (TXT)")
                except Exception as e:
                    print(f"❌ Erro ao ler {nome_arquivo}: {e}")

            # 2. Tratamento para arquivos PDF
            elif nome_arquivo.endswith('.pdf'):
                try:
                    with open(caminho_completo, 'rb') as f:
                        texto_pdf = extract_text_from_pdf(f)
                    if texto_pdf:
                        todos_os_textos.append(texto_pdf)
                        print(f"✔ Lido com sucesso: {nome_arquivo} (PDF)")
                except Exception as e:
                    print(f"❌ Erro ao ler PDF {nome_arquivo}: {e}")

            # 3. Tratamento para Tabelas (Excel e CSV)
            elif nome_arquivo.endswith('.xlsx') or nome_arquivo.endswith('.xls') or nome_arquivo.endswith('.csv'):
                try:
                    with open(caminho_completo, 'rb') as f:
                        texto_linha = extract_text_from_table(f, nome_arquivo)

                    if texto_linha:
                        todos_os_textos.append(texto_linha)
                        print(f"✔ Lido com sucesso: {nome_arquivo} (Tabela)")
                except Exception as e:
                    print(f"❌ Erro ao processar tabela {nome_arquivo}: {e}")

        return todos_os_textos

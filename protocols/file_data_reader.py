# modules/vetorizacao/leitor_pasta.py
import os
import pandas as pd
from pypdf import PdfReader

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
                    with open(caminho_completo, 'r', encoding='utf-8') as f:
                        conteudo = f.read().strip()
                        if conteudo:
                            todos_os_textos.append(conteudo)
                            print(f"✔ Lido com sucesso: {nome_arquivo} (TXT)")
                except Exception as e:
                    print(f"❌ Erro ao ler {nome_arquivo}: {e}")

            # 2. Tratamento para arquivos PDF
            elif nome_arquivo.endswith('.pdf'):
                try:
                    leitor = PdfReader(caminho_completo)
                    texto_pdf = ""
                    for pagina in leitor.pages:
                        texto_extraido = pagina.extract_text()
                        if texto_extraido:
                            texto_pdf += texto_extraido + "\n"
                    
                    texto_pdf = texto_pdf.strip()
                    if texto_pdf:
                        todos_os_textos.append(texto_pdf)
                        print(f"✔ Lido com sucesso: {nome_arquivo} (PDF - {len(leitor.pages)} págs)")
                except Exception as e:
                    print(f"❌ Erro ao ler PDF {nome_arquivo}: {e}")

            # 3. Tratamento para Tabelas (Excel e CSV)
            elif nome_arquivo.endswith('.xlsx') or nome_arquivo.endswith('.xls') or nome_arquivo.endswith('.csv'):
                try:
                    if nome_arquivo.endswith('.csv'):
                        df = pd.read_csv(caminho_completo)
                    else:
                        df = pd.read_excel(caminho_completo)
                    
                    print(f"✔ Lido com sucesso: {nome_arquivo} (Tabela com {len(df)} linhas)")
                    
                    # Converte cada linha da tabela em uma frase descritiva estruturada para o banco vetorial
                    for index, linha in df.iterrows():
                        partes_linha = []
                        for coluna in df.columns:
                            partes_linha.append(f"{coluna}: {linha[coluna]}")
                        
                        # Junta os dados da linha separados por vírgula
                        # Exemplo: "Serviço: Barba, Preço: 35, Tempo: 20 min"
                        texto_linha = f"Origem [{nome_arquivo}] -> " + ", ".join(partes_linha)
                        todos_os_textos.append(texto_linha)
                        
                except Exception as e:
                    print(f"❌ Erro ao processar tabela {nome_arquivo}: {e}")

        return todos_os_textos
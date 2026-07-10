# modules/vetorizacao/test_integracao_pasta.py
import os
import shutil

from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores
from protocols.file_data_reader import FileDataReader
# modules/vetorizacao/test_integracao_pasta.py

def rodar_integracao():
    pasta_documentos = "data"  # Sua pasta com os 6 arquivos
    pasta_banco = "db/banco_real"

    # --- PASSO CRUCIAL: Limpar o banco velho para evitar o "vício" de duplicados ---
    if os.path.exists(pasta_banco):
        print(f"Limpando o banco de dados antigo em '{pasta_banco}' para evitar duplicações...")
        shutil.rmtree(pasta_banco)

    print("\n--- PASSO 1: Lendo arquivos da pasta ---")
    leitor = FileDataReader(pasta_origem=pasta_documentos)
    textos_brutos = leitor.ler_todos_os_arquivos()

    if not textos_brutos:
        print("Nenhum texto pôde ser extraído dos arquivos. Abortando.")
        return

    print("\n--- PASSO 2: Quebrando textos grandes em pedaços menores (Chunking) ---")
    # Configura o quebrador: pedaços de 1000 caracteres com sobreposição de 200
    # para não cortar nenhuma frase importante ao meio
    quebrador_texto = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    
    # Executa a quebra em todos os textos extraídos
    pedacos_finais = quebrador_texto.split_text("\n\n".join(textos_brutos))
    print(f"Os arquivos brutos foram fragmentados em {len(pedacos_finais)} pedaços menores para melhor governança.")

    print(f"\n--- PASSO 3: Enviando pedaços para o Banco Vetorial ---")
    gerenciador = GerenciadorVetores(pasta_db=pasta_banco)
    gerenciador.criar_banco_com_textos(pedacos_finais)

    print("\n--- PASSO 4: Testando a busca semântica corrigida ---")
    
    # Teste 1: Sua pergunta sobre experiência
    pergunta_1 = "Quantos anos de experiência tem o profissional Edilson com React?"
    resultados_1 = gerenciador.buscar_contexto(pergunta_1, quantidade_resultados=1)
    print(f"\nBusca por: '{pergunta_1}'")
    print("[Resultado 1]:", resultados_1)

    # Teste 2: Pergunta sobre cancelamento
    pergunta_2 = "Qual foi a ultima empresa que ele trabalhou ou a atual?"
    resultados_2 = gerenciador.buscar_contexto(pergunta_2, quantidade_resultados=1)
    print(f"\nBusca por: '{pergunta_2}'")
    print("[Resultado 2]:", resultados_2)

if __name__ == "__main__":
    rodar_integracao()
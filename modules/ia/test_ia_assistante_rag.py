# modules/ia/test_ia_rag.py
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores
from modules.ia.assistante_rag import AssistenteRAG

def executar_chat_com_meus_dados():
    # 1. Aponta para a pasta do banco que já contém seu currículo indexado
    pasta_banco = "db/banco_real"
    gerenciador = GerenciadorVetores(pasta_db=pasta_banco)

    # 2. Instancia o assistente com o modelo local (mude para 'deepseek-r1' se preferir)
    assistente = AssistenteRAG(gerenciador_vetores=gerenciador, modelo_nome="llama3.1")

    print("\n" + "="*50)
    print("SISTEMA PRONTO PARA PERGUNTAS")
    print("="*50)

    # Pergunta 1
    p1 = "Quantos anos de experiência tem o profissional Edilson com React?"
    print(f"\nUser: {p1}")
    resposta_1 = assistente.perguntar(p1)
    print(f"IA: {resposta_1}")

    print("-" * 40)

    # Pergunta 2
    p2 = "Qual foi a última empresa que ele trabalhou ou qual a atual?"
    print(f"\nUser: {p2}")
    resposta_2 = assistente.perguntar(p2)
    print(f"IA: {resposta_2}")
    
    p3 = "Quais são os nomes dos profissionais do seu salão e quais horários e dias disponíveis para eu agendar?"
    print(f"\nUser: {p3}")
    resposta_3 = assistente.perguntar(p3)
    print(f"IA: {resposta_3}")

if __name__ == "__main__":
    executar_chat_com_meus_dados()
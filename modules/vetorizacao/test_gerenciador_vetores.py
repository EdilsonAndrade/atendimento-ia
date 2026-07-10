import os
import shutil
from gerenciador_vetores import GerenciadorVetores

def testar_fluxo_da_classe():
    # Limpa a pasta de teste antiga se ela existir para garantir um teste limpo
    pasta_teste = "db/test_chroma"
    if os.path.exists(pasta_teste):
        shutil.rmtree(pasta_teste)

    print("--- PASSO 1: Instanciando a classe e criando novo banco ---")
    gerenciador = GerenciadorVetores(pasta_db=pasta_teste)

    textos_agenda = [
        "O preço do corte de cabelo na barbearia é R$ 50.",
        "Não funcionamos aos domingos. Sábado abrimos das 9h às 19h.",
        "O barbeiro João atende por ordem de chegada na quinta-feira."
    ]

    # Salva no disco
    gerenciador.criar_banco_com_textos(textos_agenda)

    print("\n--- PASSO 2: Testando a busca com o banco recém-criado ---")
    resposta = gerenciador.buscar_contexto("Que dia o João atende?", quantidade_resultados=1)
    print("Resultado da busca:", resposta)

    print("\n--- PASSO 3: Simulando reinício do app (Carregando do disco) ---")
    # Criamos uma nova instância apontando para a mesma pasta para ver se ela lê o que foi salvo
    novo_gerenciador = GerenciadorVetores(pasta_db=pasta_teste)
    resposta_disco = novo_gerenciador.buscar_contexto("Qual o valor do cabelo?", quantidade_resultados=1)
    print("Resultado vindo direto do disco:", resposta_disco)

if __name__ == "__main__":
    testar_fluxo_da_classe()

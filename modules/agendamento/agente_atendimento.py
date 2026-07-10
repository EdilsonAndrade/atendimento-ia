import sys
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

#1 Inicializando o modelo que baixamos no Ollama
# Pode substituir o llama3 por deepseek se tiver baixado ele no Ollama

modelo_local = OllamaLLM(model="llama3.1")

# 2 Criando o prompt ) As instruçõed de como a IA deve comportar
# servicos é um array de strings que contém os serviços que a IA pode agendar
def criar_prompt(servicos: list) -> ChatPromptTemplate:
    system: str
    
    system = f"""
        Você é um assistente virtual prestativo focado em ajudar com o agendamentos dos servços disponíveis: {', '.join(servicos)}.
    """
    
    
    
    prompt = ChatPromptTemplate.from_messages([
    ("system", system),
    ("user", "{pergunta}")    
    ])

    return prompt

def main (servicos: list) -> str:
    prompt = criar_prompt(servicos)


    #3 criando um parser (Garante que a resposta saia puramente como o texto)
    parse_saida = StrOutputParser()

    # 4. Montando a Cadeia (Chain) usando a sintaxe do LangChain (LCEL)
    # O operador '|' conecta a saída de um como entrada do próximo
    cadeia_chat = prompt | modelo_local | parse_saida

    # 5 Executando o chat na pratica
    pergunta_usuario = "Olá! Gostaria de saber como funciona o agendamento de serviços?"
    resposta = cadeia_chat.invoke({ "pergunta": pergunta_usuario })


    print("---- Resposta da IA----")

    print(resposta)
    return resposta


if __name__ == "__main__":
    servicos = sys.argv[1:]  # Recebe os serviços como argumentos de linha de comando
    if not servicos:
        servicos = ["Corte de Cabelo", "Manicure", "Pedicure", "Massagem"]
    main(servicos)

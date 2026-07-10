# modules/ai/test_tool_calling.py
import os
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from modules.vetorizacao.vector_manager import VectorManager

# 1. Instanciamos os dois gerenciadores apontando para os nossos bancos reais do disco
operational_manager = VectorManager(db_directory="db/operational_db")
institutional_manager = VectorManager(db_directory="db/institutional_db")

# 2. Definição das ferramentas com as buscas de verdade conectadas
@tool
def search_operational_db(query: str) -> str:
    """
    Use this tool to search for schedules, time slots, barber names, prices, 
    and operational data of the barbershop/store.
    """
    print(f" -> [EXECUÇÃO] Acessando banco OPERACIONAL para buscar: '{query}'")
    results = operational_manager.search_context(query, num_results=5)
    return "\n\n".join(results)

@tool
def search_institutional_db(query: str) -> str:
    """
    Use this tool to search for resumes, professional experience, 
    company rules, policies, and contracts.
    """
    print(f" -> [EXECUÇÃO] Acessando banco INSTITUCIONAL para buscar: '{query}'")
    results = institutional_manager.search_context(query, num_results=5)
    return "\n\n".join(results)


def testar_roteamento_real():
    print("\n" + "=" * 60)
    print(" EXECUTANDO ROTEAMENTO REAL COM MULTI-BANCOS")
    print("=" * 60)

    llm = ChatOllama(model="llama3.1", temperature=0)
    tools_list = [search_operational_db, search_institutional_db]
    
    # Criamos o mapeamento para facilitar a chamada dinâmica baseada no nome que a IA escolher
    tools_map = {
        "search_operational_db": search_operational_db,
        "search_institutional_db": search_institutional_db
    }
    
    llm_com_ferramentas = llm.bind_tools(tools_list)

    # Bateria de testes para ver se ele acha seus dados
    perguntas_teste = [
        "What is Edilson surname?",
        "Quem é que atende às 10h?",
        "Em que ano o Edilson trabalhou na BSI?",
        "Em que ano o Edilson estudou com CrewAI?"
    ]

    for pergunta in perguntas_teste:
        print(f"\nUser: '{pergunta}'")
        
        # Passo A: IA decide qual ferramenta usar
        resposta_ia = llm_com_ferramentas.invoke(pergunta)
        
        if resposta_ia.tool_calls:
            for chamada in resposta_ia.tool_calls:
                tool_name = chamada['name']
                tool_args = tuple(chamada['args'].values())[0] # Pega o texto da query gerada pela IA
                
                # Passo B: Executamos dinamicamente a ferramenta que o banco escolheu
                funcao_real = tools_map[tool_name]
                conteudo_do_banco = funcao_real.invoke({"query": tool_args})
                
                # Passo C: Damos o veredito final para a IA ler o dado real e responder o usuário de forma limpa
                print(" -> IA formulando resposta final baseada no banco...")
                prompt_final = (
                    f"You are an expert assistant. Answer the user's question based strictly on the provided context below.\n"
                    f"CRITICAL: Detect the language of the user's question and respond EXCLUSIVELY in that same language (e.g., if the question is in English, reply in English; if in Portuguese, reply in Portuguese).\n"
                    f"Do not include any conversational meta-text like 'The question is in English' or explanations about your language detection. Go straight to the answer.\n"
                    f"Provide a complete, polite, and professional answer based only on his question. Avoid extremely short or dry responses.\n"
                    f"CRITICAL: Dont anwser with information that was not user question.\n"
                    f"Note: The user might use acronyms (like BSI) for company names that could be spelled out fully (like HBSIS) in the context. Make this connection if it makes sense.\n\n"
                    f"{conteudo_do_banco}\n\n"
                    f"User Question: {pergunta}"
                )
                resposta_final = llm.invoke(prompt_final)
                print(f"🤖 IA: {resposta_final.content}")
        else:
            print(f"🤖 IA (Sem ferramenta): {resposta_ia.content}")
        print("-" * 50)

if __name__ == "__main__":
    testar_roteamento_real()
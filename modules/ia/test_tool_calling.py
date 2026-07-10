from langchain_core.tools import tool
from langchain_ollama import ChatOllama


#1 Criamos uma ferramente simulada para o Banco Operaciona
# A DOCSTRING (texto entre aspsas triplas) é fundamental. É lendo esse texto que a IA sabe quando usar a ferramenta!

@tool
def search_operational_db(query: str) -> str:
    """
    Use this tool to search for schedules, time slots, barber names, prices, 
    and operational data of the barbershop/store.
    """
    return "Simulating response from operational database..."


@tool
def search_institutional_db(query: str) -> str:
    """
    Use this tool to search for resumes, professional experience, 
    company rules, policies, and contracts.
    """
    return "Simulating response from institutional database..."



def test_ia_decision():
    print("=" * 60) 
    print(" TEST DE TOOL CALLING: A IA SABE ESCOLHER O BANCO?")
    print("=" * 60 )
    
    # 3. Inicializamos o modelo (Usamos ChatOllama porque ele tem suporte nativo a ferramentas)
    # temperature=0 faz a IA ser fria, lógica e direta na decisão
    llm = ChatOllama(model="llama3.1", temperature=0)
    
    # 4 Colocamos o conto de utilidades na IA
    
    ferramentas = [search_operational_db, search_institutional_db]
    llm_com_ferramentas = llm.bind_tools(ferramentas)
    
    # 5. Bateroa de testes
    
    perguntas =[
        "Qual a experiência profissional do Edilson?",
        "Tem horário com o barbeiro Carlos as 10h?",
        "Como funciona a política de cancelamento em cima da hora?",
        "Qual o nome completo do Edilson?"
    ]
    
    for pergunta in perguntas:
        print("\n" + "-" * 40)
        print(f"Usuário Pergunta: {pergunta}")
        
        # A IA não vai gerar um texto de resposta, ela vai devolver um objeto de 'tool_call'
        resposta_ia = llm_com_ferramentas.invoke(pergunta)
        print(f"Resposta da IA: {resposta_ia}")
        
        # Lendo a decisão da IA
        if resposta_ia.tool_calls:
            for chamada in resposta_ia.tool_calls:
                nome_da_ferramenta = chamada["name"]
                argumentos = chamada["args"]
                print(f"✅ DECISÃO: A IA decidiu chamar a ferramenta -> [{nome_da_ferramenta}]")
                print(f"   E ela vai pesquisar por: {argumentos}")
        else:
            print("❌ ERRO: A IA tentou responder direto em vez de usar uma ferramenta.")
            

if __name__ == "__main__":
    test_ia_decision()
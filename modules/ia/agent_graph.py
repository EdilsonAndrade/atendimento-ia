# modules/ai/agent_graph.py
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage
from modules.vetorizacao.vector_manager import VectorManager
from langgraph.graph import StateGraph, END

# Instanciamos o gerenciador do banco institucional para o nó usar
institutional_manager = VectorManager(db_directory="db/institutional_db")

# Instanciamos o gerenciador do banco operacional
operational_manager = VectorManager(db_directory="db/operational_db")

# Inicializamos o LLM que controlará as decisões do grafo
# temperature=0 para garantir escolhas lógicas e sem invenções
llm = ChatOllama(model="llama3.1", temperature=0)

# Este é o nosso Estado Central (o "quadro negro" do agente)
class AgentState(TypedDict):
    # 'messages' vai guardar todo o histórico da conversa (perguntas e respostas).
    # O 'add_messages' avisa o LangGraph que, toda vez que uma nova mensagem chegar,
    # ela deve ser adicionada no fim da lista (append), em vez de apagar as antigas.
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # Aqui guardamos metadados de controle do nosso fluxo de agendamento
    current_date: str          # Guarda a data que o usuário quer (ex: "2026-07-10")
    selected_slot: str         # Guarda o horário escolhido (ex: "10:00")
    alternatives_suggested: list  # Lista de horários alternativos que oferecemos a ele
    

# ============================================================================
# PASSO 2: CRIAÇÃO DO PRIMEIRO NÓ (O Agente Roteador)
# ============================================================================

# Inicializamos o modelo local Llama 3 (temperature=0 para decisões lógicas)
llm = ChatOllama(model="llama3.1", temperature=0)

def routing_agent(state: AgentState):
    """
    Nó (Node) responsável por analisar o histórico da conversa 
    e decidir para qual braço do grafo o fluxo deve seguir.
    """
    print("\n --- [NÓ: routing_agent] IA analisando a intenção do usuário... ---")
    
    # 1. Resgatamos a lista de mensagens atual do estado
    historico_mensagens = state["messages"]
    
    # 2. Criamos a instrução de roteamento do sistema
    system_prompt = (
        "You are an orchestrator router. Analyze the conversation history and the last user message.\n"
        "Your job is to classify the user's intent into one of these categories:\n"
        "1. 'OPERATIONAL': If the user wants to book, reschedule, cancel, check available time slots, or ask about business hours/barbers.\n"
        "2. 'INSTITUTIONAL': If the user is asking about professional experience, resumes, company history, or contracts.\n"
        "3. 'CHITCHAT': If it's just a greeting, goodbye, or general casual talk.\n\n"
        "CRITICAL: Reply with EXACTLY one word: either 'OPERATIONAL', 'INSTITUTIONAL', or 'CHITCHAT'. Do not add punctuation or explanation."
    )
    
    # Montamos o payload combinando o prompt de sistema com o histórico real
    mensagens_para_ia = [AIMessage(content=system_prompt)] + list(historico_mensagens)
    
    # 3. Disparamos a chamada ao modelo
    resposta = llm.invoke(mensagens_para_ia)
    decisao = resposta.content.strip().upper()
    
    print(f" -> IA decidiu que a intenção é: [{decisao}]")
    
    # 4. Devolvemos a alteração para o LangGraph atualizar o quadro negro
    return {"messages": [AIMessage(content=f"Routing decision: {decisao}")]}

def route_decision(state: AgentState):
    """
    Função que lê a decisão tomada pelo 'routing_agent'
    e retorna o nome do proximo caminho que o grafo deve seguir.
    """
    
    print("\n --- [ARESTA CONDICIONAL] Calculando próximo nó do grafo... ---")
    # 1. Pegamos a última mensagem que o routing_agent salvou no estado
    ultima_mensagem = state["messages"][-1].content
    
    print(f" -> Última mensagem do estado: {ultima_mensagem}")
    # 2. Avaliamos o texto da decisão para escolher a rota
    if "OPERATIONAL" in ultima_mensagem:
        print(" -> Rota escolhida: Ir para o nó de dados operacionais.")
        return "operational_route"
        
    elif "INSTITUTIONAL" in ultima_mensagem:
        print(" -> Rota escolhida: Ir para o nó de dados institucionais.")
        return "institutional_route"
        
    else:
        print(" -> Rota escolhida: Ir para conversas casuais.")
        return "chitchat_route"
    

# ============================================================================
# PASSO 4: NÓ DE DADOS INSTITUCIONAIS (Busca no PDF)
# ============================================================================
def institutional_node(state: AgentState):
    """
    Nó (Node) responsável por buscar informações no banco institucional (PDFs)
    e responder à dúvida do usuário com base no contexto encontrado.
    """
    print("\n --- [NÓ: institutional_node] Buscando nos PDFs institucionais... ---")
    
    # 1. Pegamos a pergunta original do usuário (a primeira mensagem do histórico)
    # Como as mensagens acumulam, a última mensagem do tipo HumanMessage é a pergunta do usuário.
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    print(f" -> Buscando no ChromaDB por: '{pergunta_usuario}'")
    
    # 2. Executamos a busca real usando o VectorManager (trazendo os 5 melhores resultados)
    contexto_encontrado = institutional_manager.search_context(pergunta_usuario, num_results=5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    
    # 3. Preparamos o prompt em inglês para a IA consolidar a resposta no idioma correto
    prompt_final = (
        f"You are an expert assistant. Answer the user's question based strictly on the provided context below.\n"
        f"CRITICAL: Detect the language of the user's question and respond EXCLUSIVELY in that same language.\n"
        f"Do not include any conversational meta-text. Go straight to the answer.\n"
        f"Provide a complete, polite, and professional answer. Avoid extremely short or dry responses.\n"
        f"Note: The user might use acronyms (like BSI) for company names that could be spelled out fully (like HBSIS) in the context. Make this connection if it makes sense.\n\n"
        f"--- CONTEXT ---\n"
        f"{contexto_formatado}\n\n"
        f"User Question: {pergunta_usuario}"
    )
    
    # 4. Chamamos o LLM para gerar a resposta baseada no documento
    resposta_ia = llm.invoke(prompt_final)
    
    print(" -> Resposta formulada com sucesso!")
    
    # 5. Devolvemos a resposta da IA. O LangGraph vai salvar isso no nosso quadro negro.
    return {"messages": [AIMessage(content=resposta_ia.content)]}


# ============================================================================
# PASSO 5: NÓ DE DADOS OPERACIONAIS (Busca na Planilha de Horários)
# ============================================================================

def operational_node(state: AgentState):
    """
    Nó (Node) responsável por buscar informações no banco operacional (planilhas)
    e responder ao usuário sobre horários, barbeiros e preços.
    """
    print("\n --- [NÓ: operational_node] Buscando na planilha operacional... ---")
    
    # 1. Pegamos a pergunta original do usuário no histórico
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    print(f" -> Buscando no ChromaDB por: '{pergunta_usuario}'")
    
    # 2. Buscamos as linhas da planilha convertidas em vetor (trazendo até 5 resultados)
    contexto_encontrado = operational_manager.search_context(pergunta_usuario, num_results=5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    
    # 3. Prompt estruturado em inglês para a IA consolidar os dados da tabela
    prompt_final = (
        f"You are an expert booking assistant. Answer the user's question based strictly on the provided context below.\n"
        f"CRITICAL: Detect the language of the user's question and respond EXCLUSIVELY in that same language.\n"
        f"Do not include any conversational meta-text. Go straight to the answer.\n"
        f"Provide a complete, polite, and professional answer. Avoid extremely short or dry responses.\n\n"
        f"--- CONTEXT ---\n"
        f"{contexto_formatado}\n\n"
        f"User Question: {pergunta_usuario}"
    )
    
    resposta_ia = llm.invoke(prompt_final)
    
    print(" -> Resposta operacional formulada!")
    return {"messages": [AIMessage(content=resposta_ia.content)]}



# ============================================================================
# PASSO 6: NÓ DE CONVERSAS CASUAIS (Chitchat)
# ============================================================================

def chitchat_node(state: AgentState):
    """
    Nó (Node) responsável por lidar de forma simpática com saudações,
    despedidas ou interações que não exigem busca em bancos de dados.
    """
    print("\n --- [NÓ: chitchat_node] Processando conversa casual... ---")
    
    # 1. Pegamos o histórico recente
    historico = list(state["messages"])
    
    # 2. Prompt instruindo o Llama a ser acolhedor e se posicionar como assistente da barbearia
    prompt_casual = (
        "You are an AI assistant for Rubio's barbershop SaaS application.\n"
        "Respond politely, friendly and naturally to the user's message (e.g. greeting, goodbye, casual talk).\n"
        "CRITICAL: Detect the language of the user's message and respond in the same language.\n"
        "At the end of your message, gently remind the user that you can help them book an appointment or answer questions about Edilson's resume.\n"
        "Do not invent any facts about schedules or resumes here."
    )
    
    mensagens_para_ia = [AIMessage(content=prompt_casual)] + historico
    resposta_ia = llm.invoke(mensagens_para_ia)
    
    print(" -> Resposta casual gerada!")
    return {"messages": [AIMessage(content=resposta_ia.content)]}




# ============================================================================
# PASSO 7: CONSTRUÇÃO E COMPILAÇÃO DO GRAFO (Fiação do LangGraph)
# ============================================================================

# 1. Inicializamos o construtor do Grafo passando o contrato de Estado que criamos no Passo 1
builder = StateGraph(AgentState)

# 2. Registramos todos os nossos Nós (Nodes) no grafo
# O primeiro argumento é o ID ("apelido") do nó, e o segundo é a função pura que criamos
builder.add_node("routing_agent", routing_agent)
builder.add_node("institutional_node", institutional_node)
builder.add_node("operational_node", operational_node)
builder.add_node("chitchat_node", chitchat_node)

# 3. Definimos o Ponto de Entrada do sistema.
# Toda vez que enviarmos uma pergunta ao grafo, ela baterá primeiro no roteador.
builder.set_entry_point("routing_agent")

# 4. Criamos a Aresta Condicional (Conditional Edge) saindo do roteador.
# Ela diz: "Ao terminar o 'routing_agent', chame a função 'route_decision' para avaliar o estado.
# Dependendo do que ela retornar, vá para um dos três nós correspondentes."
builder.add_conditional_edges(
    "routing_agent",
    route_decision,
    {
        "operational_route": "operational_node",
        "institutional_route": "institutional_node",
        "chitchat_route": "chitchat_node"
    }
)

# 5. Definimos as Arestas Normais (as saídas de cada estação).
# Quando qualquer um dos nós de resposta terminar o seu trabalho, o fluxo deve ir para o FIM (END).
builder.add_edge("institutional_node", END)
builder.add_edge("operational_node", END)
builder.add_edge("chitchat_node", END)

# 6. Compilamos o Grafo! 
# O 'app' agora é o nosso agente inteligente unificado pronto para ser executado.
app = builder.compile()


# ============================================================================
# EXECUÇÃO DO AGENTE (Para Testes Locais)
# ============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" INICIALIZANDO SINCRO-AGENTE VIA LANGGRAPH")
    print("=" * 60)

    # 1. Simulamos a pergunta do usuário envelopada em uma HumanMessage do LangChain
    pergunta_teste = "Ola no que você pode me ajudar?"
    
    # 2. Inicializamos o nosso quadro negro (Estado) com a mensagem de entrada
    estado_inicial = {
        "messages": [HumanMessage(content=pergunta_teste)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }

    print(f"\nDisparando pergunta ao Grafo: '{pergunta_teste}'")
    
    # 3. Executamos o grafo!
    # O método 'invoke' vai rodar o fluxo inteiro passo a passo de forma automatizada
    resultado = app.invoke(estado_inicial)

    print("\n" + "=" * 60)
    print(" FLUXO DO GRAFO FINALIZADO COM SUCESSO!")
    print("=" * 60)
    
    # 4. Pegamos a última mensagem salva no estado final (que é a resposta da IA)
    resposta_final = resultado["messages"][-1].content
    print(f"\n🤖 RESPOSTA FINAL DO AGENTE:\n{resposta_final}\n")
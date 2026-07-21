# modules/ia/agent_graph.py
import psycopg
from typing import TypedDict, Annotated, Sequence
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig  # IMPORTANTE: Para receber as configs dinâmicas do FastAPI
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from modules.vetorizacao.vector_manager import VectorManager
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://postgres:2765581@localhost:5432/simplificandoai"

# ============================================================================
# PASSO 1: ESTRUTURA DO ESTADO (O "Quadro Negro" Compartilhado)
# ============================================================================
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

def routing_agent(state: AgentState, config: RunnableConfig):
    """
    Nó (Node) responsável por analisar a conversa e decidir o próximo passo do fluxo.
    Note que ele agora aceita 'config' na assinatura para manter a padronização,
    mesmo que a decisão de roteamento ainda não dependa do tenant do banco.
    """
    print("\n --- [NÓ: routing_agent] IA analisando a intenção do usuário... ---")
    
    # 1. Pegamos o histórico de mensagens que está no quadro negro
    historico_mensagens = state["messages"]
    
    # 2. Criamos uma instrução rígida para o LLM atuar como um roteador de arquitetura
    system_prompt = (
        "You are an orchestrator router. Analyze the conversation history and the last user message.\n"
        "Your job is to classify the user's intent into one of these categories:\n"
        "1. 'OPERATIONAL': If the user wants to book, reschedule, cancel, check available time slots, ask about prices, services, or barbers.\n"
        "2. 'INSTITUTIONAL': If the user is asking about professional experience, resumes, company history, address, or general rules.\n"
        "3. 'CHITCHAT': If it's just a greeting, goodbye, or general casual talk.\n\n"
        "CRITICAL: Reply with EXACTLY one word: either 'OPERATIONAL', 'INSTITUTIONAL', or 'CHITCHAT'. Do not add punctuation or explanation."
    )
    
    # Preparamos a lista de mensagens para enviar ao Llama, incluindo o nosso prompt de sistema
    mensagens_para_ia = [AIMessage(content=system_prompt)] + list(historico_mensagens)
    
    # 3. Chamamos o Llama 3.1
    resposta = llm.invoke(mensagens_para_ia)
    decisao = resposta.content.strip().upper()
    
    print(f" -> IA decidiu que a intenção é: [{decisao}]")
    
    # 4. Retornamos um dicionário com a decisão do roteador
    return {"messages": [AIMessage(content=f"Routing decision: {decisao}")]}


# ============================================================================
# PASSO 3: ARESTA CONDICIONAL (O Direcionador de Rotas)
# ============================================================================
def route_decision(state: AgentState):
    """
    Função que lê a decisão tomada pelo 'routing_agent' 
    e retorna o nome do próximo caminho que o grafo deve seguir.
    """
    print("\n --- [ARESTA CONDICIONAL] Calculando próximo nó do grafo... ---")
    # 1. Pegamos a última mensagem que o routing_agent salvou no estado
    ultima_mensagem = state["messages"][-1].content
    
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
# PASSO 4: NÓ DE DADOS INSTITUCIONAIS (Busca Dinâmica no RAG + Histórico)
# ============================================================================
def institutional_node(state: AgentState, config: RunnableConfig):
    """
    Nó responsável por buscar informações no banco institucional/geral
    e responder à dúvida do usuário mantendo o contexto do histórico.
    """
    print("\n --- [NÓ: institutional_node] Buscando na base de conhecimento... ---")
    
    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")
    
    db_path = f"db/{tenant_id}/knowledge_db"
    print(f" -> [MULTITENANT] Conectando ao banco de dados do Tenant: '{tenant_id}' em '{db_path}'")
    try:
        manager = VectorManager(db_directory=db_path)
    except Exception as e:
        print(f"Erro ao carregar banco: {e}")
        return {"messages": [AIMessage(content="Não foram encontrados dados do cliente para formular a resposta.")]}
        
    # 1. Pegamos a pergunta original do usuário (última mensagem Human)
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    print(f" -> Buscando no ChromaDB por: '{pergunta_usuario}'")
    
    # 2. Busca RAG via MMR
    contexto_encontrado = manager.search_context(pergunta_usuario, num_results=5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    
    # 3. Formata o histórico recente de conversas para o LLM lembrar do passado
    historico_texto = ""
    for msg in state["messages"][:-1]:  # Pega todas exceto a última que acabamos de enviar
        if msg.type == "human":
            historico_texto += f"User: {msg.content}\n"
        elif msg.type == "ai" and not msg.content.startswith("Routing decision:"):
            historico_texto += f"Assistant: {msg.content}\n"

    # 4. Prompt com RAG + Histórico de Conversa
    prompt_final = (
        f"You are an expert assistant for the business. Answer the user's question using the provided context below.\n"
        f"You also have access to the conversation history with this user. Use it if they refer to previous topics.\n"
        f"CRITICAL GUARDRAIL: If the answer is not in the context or history, state clearly that you do not have that information.\n"
        f"CRITICAL: Detect the language of the user's question and respond EXCLUSIVELY in that same language.\n"
        f"Provide a complete, polite, and professional answer.\n\n"
        f"--- CONVERSATION HISTORY ---\n"
        f"{historico_texto}\n\n"
        f"--- CONTEXT FROM KNOWLEDGE BASE ---\n"
        f"{contexto_formatado}\n\n"
        f"User Question: {pergunta_usuario}"
    )
    
    resposta_ia = llm.invoke(prompt_final)
    print(" -> Resposta institucional formulada com sucesso!")
    return {"messages": [AIMessage(content=resposta_ia.content)]}


# ============================================================================
# PASSO 5: NÓ DE DADOS OPERACIONAIS (Busca Dinâmica + Histórico)
# ============================================================================
def operational_node(state: AgentState, config: RunnableConfig):
    """
    Nó responsável por buscar informações operacionais e responder 
    ao usuário mantendo a memória das conversas anteriores salvas no Postgres.
    """
    print("\n --- [NÓ: operational_node] Buscando na base operacional... ---")
    
    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")
    
    db_path = f"db/{tenant_id}/knowledge_db"
    print(f" -> [MULTITENANT] Conectando ao banco de dados do Tenant: '{tenant_id}' em '{db_path}'")
    
    try:
        manager = VectorManager(db_directory=db_path)
    except Exception as e:
        print(f"Erro ao carregar banco: {e}")
        return {"messages": [AIMessage(content="Não foram encontrados dados do cliente para formular a resposta.")]}
    
    # 1. Pegamos a pergunta original do usuário
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    print(f" -> Buscando no ChromaDB por: '{pergunta_usuario}'")
    
    # 2. Busca no RAG
    contexto_encontrado = manager.search_context(pergunta_usuario, num_results=5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    
    # 3. Formata o histórico recente de conversas para o LLM lembrar do passado
    historico_texto = ""
    for msg in state["messages"][:-1]:  # Pega todas exceto a última que acabamos de enviar
        if msg.type == "human":
            historico_texto += f"User: {msg.content}\n"
        elif msg.type == "ai" and not msg.content.startswith("Routing decision:"):
            historico_texto += f"Assistant: {msg.content}\n"

    # 4. Prompt com RAG + Equivalências Semânticas + Histórico de Memória
    prompt_final = (
        f"You are an expert booking assistant for the business. Answer the user's question using the provided context and conversation history.\n"
        f"IMPORTANT: Use the Conversation History to recall previous agreements, questions, or choices made by the user in this session.\n"
        f"IMPORTANT: Understand semantic equivalences naturally (e.g., 'fazer a unha' refers to 'Manicure', 'fazer barba' refers to 'Barba Terapia' or 'Barba Express').\n"
        f"CRITICAL GUARDRAIL: Do NOT invent prices, times, or services that are completely absent from the context or history.\n"
        f"CRITICAL: Detect the language of the user's question and respond EXCLUSIVELY in that same language.\n"
        f"Provide a complete, polite, and professional answer.\n\n"
        f"--- CONVERSATION HISTORY ---\n"
        f"{historico_texto}\n\n"
        f"--- CONTEXT FROM KNOWLEDGE BASE ---\n"
        f"{contexto_formatado}\n\n"
        f"User Question: {pergunta_usuario}"
    )
    
    resposta_ia = llm.invoke(prompt_final)
    print(" -> Resposta operacional formulada com sucesso!")
    return {"messages": [AIMessage(content=resposta_ia.content)]}

# ============================================================================
# PASSO 6: NÓ DE CONVERSAS CASUAIS (Chitchat)
# ============================================================================
def chitchat_node(state: AgentState, config: RunnableConfig):
    """
    Nó (Node) responsável por lidar de forma simpática com saudações,
    despedidas ou interações que não exigem busca em bancos de dados.
    """
    print("\n --- [NÓ: chitchat_node] Processando conversa casual... ---")
    
    historico = list(state["messages"])
    
    prompt_casual = (
        "You are an AI assistant for a business SaaS application.\n"
        "Respond politely, friendly and naturally to the user's message.\n"
        "CRITICAL: Detect the language of the user's message and respond in the same language.\n"
        "At the end of your message, gently remind the user that you can help them book an appointment, check prices, or answer business-related questions.\n"
        "CRITICAL GUARDRAIL: Do not invent any business hours, prices, or addresses here."
    )
    
    mensagens_para_ia = [AIMessage(content=prompt_casual)] + historico
    resposta_ia = llm.invoke(mensagens_para_ia)
    
    print(" -> Resposta casual gerada com sucesso!")
    return {"messages": [AIMessage(content=resposta_ia.content)]}


# ============================================================================
# PASSO 7: CONSTRUÇÃO E COMPILAÇÃO DO GRAFO (Fiação do LangGraph)
# ============================================================================

# 1. Inicializamos o construtor do Grafo passando o contrato de Estado
builder = StateGraph(AgentState)

# 2. Registramos todos os nossos Nós (Nodes) no grafo
builder.add_node("routing_agent", routing_agent)
builder.add_node("institutional_node", institutional_node)
builder.add_node("operational_node", operational_node)
builder.add_node("chitchat_node", chitchat_node)

# 3. Definimos o Ponto de Entrada do sistema
builder.set_entry_point("routing_agent")

# 4. Criamos a Aresta Condicional (Conditional Edge) saindo do roteador
builder.add_conditional_edges(
    "routing_agent",
    route_decision,
    {
        "operational_route": "operational_node",
        "institutional_route": "institutional_node",
        "chitchat_route": "chitchat_node"
    }
)

# 5. Definimos as Arestas Normais (as saídas de cada estação para o Fim)
builder.add_edge("institutional_node", END)
builder.add_edge("operational_node", END)
builder.add_edge("chitchat_node", END)


def get_compiled_graph():
    """
    Instancia o Pool de conexões do PostgreSQL e compila o Grafo 
    usando o PostgresSaver para persistência real do histórico.
    """
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
    }
    
    # Estabelece a conexão com o PostgreSQL para o Checkpointer
    conn = psycopg.connect(DB_URI, **connection_kwargs)
    checkpointer = PostgresSaver(conn)
    
    # Cria automaticamente as tabelas do LangGraph no Postgres se não existirem
    checkpointer.setup()
    
    # Compila e retorna o grafo com memória persistente
    return builder.compile(checkpointer=checkpointer)


# ============================================================================
# EXECUÇÃO DO AGENTE (Simulando uma chamada de API Multi-Tenant)
# ============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" INICIALIZANDO SINCRO-AGENTE DINÂMICO (MULTI-TENANT)")
    print("=" * 60)

    # Compilamos o grafo com o PostgresSaver
    app_graph = get_compiled_graph()

    pergunta_teste = "Quero cortar o cabelo e fazer a unha na quinta-feira às 16h, é possível? E qual o preço do Corte Degradê?"
    
    estado_inicial = {
        "messages": [HumanMessage(content=pergunta_teste)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }

    # IMPORTANTE: O PostgresSaver exige 'thread_id' para saber em qual linha do banco gravar!
    configuracao_requisicao = {
        "configurable": {
            "tenant_id": "interasis_barber",
            "thread_id": "sessao_teste_123"
        }
    }

    print(f"\nDisparando pergunta ao Grafo para o Tenant [{configuracao_requisicao['configurable']['tenant_id']}]:")
    print(f" -> Pergunta: '{pergunta_teste}'")
    
    # Executando o grafo persistido
    resultado = app_graph.invoke(estado_inicial, configuracao_requisicao)

    print("\n" + "=" * 60)
    print(" FLUXO DO GRAFO FINALIZADO COM SUCESSO!")
    print("=" * 60)
    
    resposta_final = resultado["messages"][-1].content
    print(f"\n🤖 RESPOSTA FINAL DO AGENTE:\n{resposta_final}\n")
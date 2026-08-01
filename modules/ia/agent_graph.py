# modules/ia/agent_graph.py
import psycopg
import os
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig  # IMPORTANTE: Para receber as configs dinâmicas do FastAPI
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, END
from modules.vetorizacao.vector_manager import VectorManager
from langgraph.checkpoint.postgres import PostgresSaver
from modules.agendamento.booking_tools import confirmar_agendamento
from modules.agendamento.agenda_tool import consultar_horarios_disponiveis
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

DB_URI = os.getenv("POSTGRES_DATABASE_URI","postgresql://postgres:2765581@localhost:5432/simplificandoai")
llm_model = os.getenv("LLM", "llama3.3")
print(f"Acessando o banco {DB_URI}")
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
llm = ChatOpenAI(model=llm_model, temperature=0)

# Vincula a Tool de agendamento ao modelo Llama 3.1
tools = [consultar_horarios_disponiveis, confirmar_agendamento]

llm_with_tools = llm.bind_tools(tools)

# ============================================================================
# PASSO 3: NÓ ROTEADOR COM GUARDRAIL DE CONTEXTO DUAL (routing_agent)
# ============================================================================
def routing_agent(state: AgentState, config: RunnableConfig):
    """
    Classifica a intenção combinando Guardrail de estado (respostas a perguntas anteriores)
    e envio de histórico nativo para o GPT-4o-mini.
    """
    print("\n --- [NÓ: routing_agent] GPT-4o-mini analisando a intenção do usuário... ---")
    
    # 1. Filtra as mensagens reais do chat
    historico_limpo = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]
    
    # GUARDRAIL AUTOMÁTICO: Se a IA fez uma pergunta operacional na mensagem anterior
    # (ex: pediu horário, barbeiro, confirmação), a resposta do usuário É OPERACIONAL.
    if len(historico_limpo) >= 2:
        ultima_msg_ia = str(historico_limpo[-2].content).lower() if historico_limpo[-2].type == "ai" else ""
        gatilhos_operacionais = ["horário", "horario", "barbeiro", "profissional", "serviço", "servico", "agendar", "data", "dia"]
        
        if any(gatilho in ultima_msg_ia for gatilho in gatilhos_operacionais):
            print(" -> 🛡️ Guardrail Ativo: Usuário está respondendo a uma pergunta de agendamento. Forçando OPERATIONAL!")
            return {"messages": [AIMessage(content="Routing decision: OPERATIONAL")]}

    # 2. Se não caiu no guardrail, aciona o GPT-4o-mini passando as mensagens nativas
    system_prompt = SystemMessage(content=(
        "You are an orchestrator router for a business booking application.\n"
        "Classify the intent of the user's latest response based on the conversation context.\n\n"
        "CLASSIFICATION RULES:\n"
        "1. 'OPERATIONAL': The user wants to book, reschedule, cancel, or is answering a question about a booking "
        "(e.g., providing a barber name, time, date, service, or confirmation).\n"
        "2. 'INSTITUTIONAL': Questions about company address, policies, rules, or general info.\n"
        "3. 'CHITCHAT': ONLY standalone greetings ('olá', 'tudo bem'), farewells, or off-topic talk.\n\n"
        "CRITICAL: Reply with EXACTLY ONE word: 'OPERATIONAL', 'INSTITUTIONAL', or 'CHITCHAT'."
    ))
    
    # Monta o array com as mensagens reais no formato nativo da OpenAI
    mensagens_para_ia = [system_prompt] + historico_limpo[-6:]
    
    resposta = llm.invoke(mensagens_para_ia)
    decisao = resposta.content.strip().upper()
    
    if "OPERATIONAL" in decisao:
        decisao = "OPERATIONAL"
    elif "INSTITUTIONAL" in decisao:
        decisao = "INSTITUTIONAL"
    else:
        decisao = "CHITCHAT"
    
    print(f" -> Roteador definiu a intenção: [{decisao}]")
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
# PASSO 5: NÓ OPERACIONAL (Corrigido sem Loop Infinito)
# ============================================================================
def operational_node(state: AgentState, config: RunnableConfig):
    """
    Nó Operacional que preserva as ToolMessages no estado para evitar Loops Infinitos.
    """
    print("\n --- [NÓ: operational_node] GPT-4o-mini avaliando fluxo de atendimento... ---")
    
    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")
    
    db_path = f"db/{tenant_id}/knowledge_db"
    
    try:
        manager = VectorManager(db_directory=db_path)
    except Exception as e:
        print(f"Erro ao carregar banco: {e}")
        return {"messages": [AIMessage(content="Não foram encontrados dados do cliente.")]}
    
    # Busca a última pergunta do usuário apenas para o RAG
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    contexto_encontrado = manager.search_context(pergunta_usuario, num_results=5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    
    tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(30)
    tabela_calendario_str = "\n".join(tabela_dias)

    system_prompt_str = (
        f"You are an intelligent booking assistant for the business (Tenant ID: '{tenant_id}').\n\n"
        f"--- REAL-TIME CALENDAR REFERENCE (NEXT 7 DAYS COMPUTED BY SYSTEM) ---\n"
        f"{tabela_calendario_str}\n"
        f"Current Time Today: {hora_atual_str}\n\n"
        f"CRITICAL DATE MAPPING RULE:\n"
        f"- When the user specifies a day (e.g., 'hoje', 'amanhã', 'segunda-feira', 'terça-feira', etc.), "
        f"LOOK UP the corresponding ISO date (YYYY-MM-DD) from the CALENDAR REFERENCE table above.\n"
        f"- DO NOT perform date calculations yourself. STRICTLY use the exact ISO dates from the table.\n\n"
        f"YOUR RESPONSIBILITIES:\n"
        f"1. Help the user answer questions about services, prices, and barbers using KNOWLEDGE BASE CONTEXT.\n"
        f"2. Check availability using 'consultar_horarios_disponiveis' tool.\n"
        f"3. Complete bookings using 'confirmar_agendamento' tool.\n\n"
        f"FALLBACK RULE FOR PROFESSIONAL PREFERENCE:\n"
        f"- If the user says 'tanto faz', 'qualquer um', or does NOT specify a preferred professional:\n"
        f"  CALL 'consultar_horarios_disponiveis' using 'Daniel' (or primary professional) for the requested date.\n\n"
        f"TOOL EXECUTION RULES:\n"
        f"- 'consultar_horarios_disponiveis': Needs tenant_id ('{tenant_id}'), profissional, and data_agendamento (YYYY-MM-DD).\n"
        f"- MANDATORY DOUBLE-CHECK RULE BEFORE BOOKING:\n"
        f"  Before executing 'confirmar_agendamento', you MUST ALWAYS execute 'consultar_horarios_disponiveis' "
        f"  to verify if the requested time slot is STILL available in real-time. If another client booked it in the meantime, "
        f"  DO NOT call 'confirmar_agendamento', inform the user politely in Portuguese, and suggest other available slots.\n"
        f"- 'confirmar_agendamento': Call ONLY AFTER real-time availability is re-confirmed and all parameters are present: "
        f"tenant_id, cliente_nome, cliente_email, servico, profissional, email_profissional, data_agendamento (YYYY-MM-DD), horario (HH:MM).\n\n"
        f"MISSING INFORMATION RULE:\n"
        f"- If time/date or user details are missing during booking, ask politely in Portuguese.\n"
        f"- ONLY offer times AFTER current time {hora_atual_str} if booking for TODAY ({data_hoje_iso}).\n"
        f"- Always respond in natural Portuguese (Brazil).\n\n"
        f"--- KNOWLEDGE BASE CONTEXT ---\n"
        f"{contexto_formatado}"
    )

    # 1. Filtramos as decisões do roteador das mensagens
    mensagens_chat = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]

    # 2. SEGREDO DO LANGGRAPH: Montamos o SystemMessage + TODO O HISTÓRICO REAL (incluindo ToolMessages)
    mensagens_para_ia = [SystemMessage(content=system_prompt_str)] + mensagens_chat
    
    # 3. Invocamos a IA com a lista completa de mensagens do Estado
    resposta_ia = llm_with_tools.invoke(mensagens_para_ia)
    
    if hasattr(resposta_ia, 'tool_calls') and resposta_ia.tool_calls:
        print(f" -> 🚀 TOOL CALL DISPARADO AUTONOMAMENTE: {resposta_ia.tool_calls}")
    else:
        print(" -> GPT-4o-mini processou o resultado da tool e gerou a resposta em texto.")

    return {"messages": [resposta_ia]}

# ============================================================================
# PASSO 6: NÓ DE CONVERSAS CASUAIS (Chitchat)
# ============================================================================
def chitchat_node(state: AgentState, config: RunnableConfig):
    """
    Nó de conversa casual simples e direta.
    """
    print("\n --- [NÓ: chitchat_node] Processando conversa casual... ---")
    
    # Filtra histórico limpando decisões do roteador
    historico = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]
    
    prompt_casual = (
        "You are a friendly AI assistant for a business SaaS.\n"
        "Respond politely and naturally to the user's message.\n"
        "CRITICAL: Detect the language of the user's message and respond in that same language.\n"
        "Gently remind them that you can help with booking appointments or answering questions about services.\n"
        "Do NOT invent any prices or business hours."
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

# Registra os nós principais
builder.add_node("routing_agent", routing_agent)
builder.add_node("institutional_node", institutional_node)
builder.add_node("operational_node", operational_node)
builder.add_node("chitchat_node", chitchat_node)

# Registra o nó executor de Tools do LangGraph
tool_node = ToolNode(tools=tools)
builder.add_node("tools", tool_node)

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

# Aresta condicional para o nó operacional: se o LLM gerou chamada de tool, vai para 'tools', senão vai para END
builder.add_conditional_edges(
    "operational_node",
    tools_condition,
    {
        "tools": "tools",
        END: END
    }
)

# 5. Definimos as Arestas Normais (as saídas de cada estação para o Fim)
builder.add_edge("tools", "operational_node")
builder.add_edge("institutional_node", END)
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

def get_tabela_dias(quantidade_dias: int):
    now = datetime.now()
    data_hoje_iso = now.strftime("%Y-%m-%d")
    data_formatada_br = now.strftime("%d/%m/%Y")
    hora_atual_str = now.strftime("%H:%M")

    # Mapeamento dos dias da semana em português
    dias_semana_pt = {
        0: "segunda-feira",
        1: "terça-feira",
        2: "quarta-feira",
        3: "quinta-feira",
        4: "sexta-feira",
        5: "sábado",
        6: "domingo"
    }

    # Monta uma tabela dos próximos 7 dias calculados matematicamente pelo Python
    tabela_dias = []
    for i in range(quantidade_dias):
        dia_calc = now + timedelta(days=i)
        nome_dia = "hoje" if i == 0 else ("amanhã" if i == 1 else dias_semana_pt[dia_calc.weekday()])
        data_iso = dia_calc.strftime("%Y-%m-%d")
        data_br = dia_calc.strftime("%d/%m/%Y")
        tabela_dias.append(f"• {nome_dia.capitalize()} ({dias_semana_pt[dia_calc.weekday()]}): {data_br} (ISO: '{data_iso}')")
    
    return tabela_dias, hora_atual_str, data_hoje_iso

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
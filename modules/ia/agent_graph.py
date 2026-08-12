# modules/ia/agent_graph.py
import psycopg
import os
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig  # IMPORTANTE: Para receber as configs dinâmicas do FastAPI
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from modules.agendamento.booking_tools import confirmar_agendamento
from modules.agendamento.agenda_tool import consultar_horarios_disponiveis
from modules.agendamento.delete_agenda_tool import cancelar_agendamento
from modules.agendamento.consulta_agenda_tool import consulta_agendamento
from infrastructure.connection import DB_URI
from datetime import datetime, timedelta
from prompts.load_prompt import carregar_operacional_prompt
from modules.agendamento.tools.google_calendario.agenda_tool import build_agendar_tool
from modules.agendamento.tools.google_calendario.consulta_agenda_tool import build_consulta_tool
from modules.agendamento.tools.google_calendario.delete_agenda_tool import build_delete_tool
from modules.google_calendar.google_calendar_service import GoogleCalendarService
from modules.tenant.tenant_service import TenantService
# ============================================================================
# ALTERAÇÃO DE IMPORT: Substitui o VectorManager antigo pelo GerenciadorVetores
# ============================================================================
# REMOVIDO: from modules.vetorizacao.vector_manager import VectorManager
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores  # COMENTÁRIO: Utiliza a classe do PGVector
llm_model = os.getenv("LLM", "llama3.3")
api_key = os.getenv("API_KEY")
print(f"Acessando o banco {DB_URI}")

# Instâncias globais dos serviços de infraestrutura
tenant_service = TenantService()
calendar_service = GoogleCalendarService(service_account_path="credentials.json")

print("🚀 [GLOBAL] Inicializando Gerenciador de Vetores e Modelo HuggingFace...")
# O modelo sobe para a RAM APENAS UMA VEZ ao ligar o container!
vector_manager_global = GerenciadorVetores()
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
llm = ChatOpenAI(
    model=llm_model, 
    api_key=api_key,
    base_url="https://api.deepseek.com/v1", # Garanta que a base URL aponta para a API do DeepSeek
    temperature=0
    )

static_tools = [
    consultar_horarios_disponiveis, 
    confirmar_agendamento, 
    cancelar_agendamento, 
    consulta_agendamento
]
def get_tenant_tools(tenant_id: str, tenant_service, calendar_service):
    return [
        build_agendar_tool(tenant_id, tenant_service, calendar_service),
        build_consulta_tool(tenant_id, tenant_service, calendar_service),
        build_delete_tool(tenant_id, tenant_service, calendar_service),
    ]

def get_active_tools(tenant_id: str):
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    google_calendar_id = tenant.get("google_calendar_id") if tenant else None

    if google_calendar_id:
        active_tools = get_tenant_tools(tenant_id, tenant_service, calendar_service)
        backend = "google_calendar"
    else:
        active_tools = static_tools
        backend = "internal_fallback"

    print(
        f" -> [TOOL CONFIG] tenant_id={tenant_id} backend={backend} "
        f"google_calendar_id={google_calendar_id!r} "
        f"tools={[tool.name for tool in active_tools]}"
    )
    return active_tools
    
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
    
    # COMENTÁRIO: Filtra apenas mensagens de usuário e assistente (descartando ToolMessages e decisões de roteamento anteriores)
    # Isso impede que cortes no histórico deixem mensagens de ferramentas órfãs enviadas para a API.
    historico_limpo = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
        and not isinstance(m, ToolMessage)
    ]
   # Monta o array limpo sem o risco de enviar ToolMessages sem seu pai AIMessage
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
    
    # 1. Pegamos a pergunta original do usuário (última mensagem Human)
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    print(f" -> Buscando no DB por: '{pergunta_usuario}'")
    
    # 2. Busca RAG via MMR
    contexto_encontrado = vector_manager_global.search_context(pergunta_usuario,tenant_id, 5)
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
    
   
    # Busca a última pergunta do usuário apenas para o RAG
    pergunta_usuario = ""
    for msg in reversed(state["messages"]):
        if msg.type == "human":
            pergunta_usuario = msg.content
            break

    contexto_encontrado = vector_manager_global.search_context(pergunta_usuario, tenant_id, 5)
    contexto_formatado = "\n\n".join(contexto_encontrado)
    

    tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(7)
    system_prompt_str = carregar_operacional_prompt(
                            tenant_id=tenant_id,
                            tabela_calendario_str=tabela_dias, 
                            hora_atual_str=hora_atual_str, 
                            data_hoje_iso=data_hoje_iso,
                            contexto_formatado=contexto_formatado
                        )

    # 1. Filtramos as decisões do roteador das mensagens
    mensagens_chat = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]

    # 2. SEGREDO DO LANGGRAPH: Montamos o SystemMessage + TODO O HISTÓRICO REAL (incluindo ToolMessages)
    mensagens_para_ia = [SystemMessage(content=system_prompt_str)] + mensagens_chat
    
    # 3. Disponibiliza somente as tools do backend configurado para o tenant.
    all_active_tools = get_active_tools(tenant_id)
    
    llm_dynamic = llm.bind_tools(all_active_tools,parallel_tool_calls=False)
    
    resposta_ia = llm_dynamic.invoke(mensagens_para_ia)
    # BLINDAGEM: Se a API externa ignorar o parâmetro e mandar várias tool calls de uma vez,
    # mantemos apenas a primeira, forçando a execução estritamente sequencial.
    if hasattr(resposta_ia, "tool_calls") and resposta_ia.tool_calls and len(resposta_ia.tool_calls) > 1:
        print(f" -> 🛡️ [GUARDRAIL] API enviou {len(resposta_ia.tool_calls)} tool calls em paralelo. Limitando a apenas 1 por segurança.")
        resposta_ia.tool_calls = resposta_ia.tool_calls[:1]
    
    if hasattr(resposta_ia, 'tool_calls') and resposta_ia.tool_calls:
        print(f" -> 🚀 TOOL CALL DISPARADO AUTONOMAMENTE: {resposta_ia.tool_calls}")
    else:
        print(" -> LLM gerou resposta em texto (nenhuma tool foi chamada).")

    return {"messages": [resposta_ia]}

# ============================================================================
# PASSO 6: NÓ DE CONVERSAS CASUAIS (Chitchat)
# ============================================================================
def chitchat_node(state: AgentState, config: RunnableConfig):
    """
    Nó de conversa casual/chitchat protegido com SystemMessage e Guardrails.
    """
    print("\n --- [NÓ: chitchat_node] Processando conversa casual... ---")
    
    # 1. Carrega o guardrail de recusa
    caminho_guardrail = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "guardrails.md")
    guardrails_text = ""
    if os.path.exists(caminho_guardrail):
        with open(caminho_guardrail, "r", encoding="utf-8") as f:
            guardrails_text = f.read()

    # 2. Filtra APENAS mensagens de texto do usuário e assistente (descarta ToolMessages e decisões do roteador)
    historico_limpo = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            historico_limpo.append(msg)
        elif isinstance(msg, AIMessage) and not str(msg.content).startswith("Routing decision:"):
            historico_limpo.append(msg)

    # 3. MONTA O PROMPT CORRETO COMO SystemMessage (E NÃO AIMessage)
    system_prompt = SystemMessage(content=(
        f"{guardrails_text}\n\n"
        "You are a polite AI assistant for the business.\n"
        "Respond courteously to simple greetings ('olá', 'bom dia') or farewells.\n"
        "CRITICAL: If the user asks for jokes, off-topic entertainment, or uses inappropriate language, REJECT politely using the guardrail rule.\n"
        "ALWAYS respond in the exact same language as the user."
    ))
    
    # Envia o SystemMessage no topo + as últimas 4 mensagens limpas do chat
    mensagens_para_ia = [system_prompt] + historico_limpo[-4:]
    
    try:
        resposta_ia = llm.invoke(mensagens_para_ia)
        print(" -> Resposta casual/guardrail gerada com sucesso!")
        return {"messages": [AIMessage(content=resposta_ia.content)]}
    except Exception as e:
        print(f" ⚠️ ERRO NO CHITCHAT_NODE: {str(e)}")
        # Fallback seguro caso a API da LLM oscile no chitchat
        return {"messages": [AIMessage(content="Meu foco é exclusivo no atendimento e agendamento de serviços da empresa. Como posso te ajudar com nossos horários ou serviços hoje?")]}


# ============================================================================
# PASSO 7: CONSTRUÇÃO E COMPILAÇÃO DO GRAFO (Fiação do LangGraph)
# ============================================================================

# O Nó de Ferramentas precisa conseguir executar a ferramenta chamada.
# Função auxiliar para mapear dinamicamente a execução de ferramentas no ToolNode:
def dynamic_tool_node(state: AgentState, config: RunnableConfig):
    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")
    
    active_tools = get_active_tools(tenant_id)
    
    node = ToolNode(tools=active_tools, handle_tool_errors=True)
    result = node.invoke(state)

    for message in result.get("messages", []):
        print(
            f" -> [TOOL RESULT] tenant_id={tenant_id} "
            f"tool={getattr(message, 'name', None)!r} "
            f"tool_call_id={getattr(message, 'tool_call_id', None)!r} "
            f"content={message.content!r}"
        )

    return result

builder = StateGraph(AgentState)

builder.add_node("routing_agent", routing_agent)
builder.add_node("institutional_node", institutional_node)
builder.add_node("operational_node", operational_node)
builder.add_node("chitchat_node", chitchat_node)
builder.add_node("tools", dynamic_tool_node)

builder.set_entry_point("routing_agent")

builder.add_conditional_edges(
    "routing_agent",
    route_decision,
    {
        "operational_route": "operational_node",
        "institutional_route": "institutional_node",
        "chitchat_route": "chitchat_node"
    }
)

builder.add_conditional_edges(
    "operational_node",
    tools_condition,
    {
        "tools": "tools",
        END: END
    }
)

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
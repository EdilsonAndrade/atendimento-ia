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
from prompts.load_prompt import (
    carregar_operacional_prompt,
    carregar_institutional_prompt,
    carregar_chitchat_prompt,
)
from modules.agendamento.tools.google_calendario.agenda_tool import build_agendar_tool
from modules.agendamento.tools.google_calendario.consulta_agenda_tool import build_consulta_tool
from modules.agendamento.tools.google_calendario.delete_agenda_tool import build_delete_tool
from modules.google_calendar.google_calendar_service import GoogleCalendarService
from modules.tenant.tenant_service import TenantService
from util.ai_helpers import sanitize_for_openai_strict_format  # COMENTÁRIO: Importa a função de higienização de histórico
from langchain_core.messages import trim_messages
from util.ai_helpers import (
    extract_customer_profile,
    build_customer_context_block,
)
from util.time_helpers import get_tabela_dias
from util.prompt_logger import log_llm_prompt
# ============================================================================
# ALTERAÇÃO DE IMPORT: Substitui o VectorManager antigo pelo GerenciadorVetores
# ============================================================================
# REMOVIDO: from modules.vetorizacao.vector_manager import VectorManager
from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores  # COMENTÁRIO: Utiliza a classe do PGVector
llm_model = os.getenv("LLM", "llama3.3")
api_key = os.getenv("API_KEY")
print(f"Acessando o banco {DB_URI}")

# Regra anti-alucinação aplicada em cima de QUALQUER prompt (institucional, ou operacional
# vindo do banco ou do fallback local) — garante que o nome do negócio, serviços e preços
# nunca sejam inventados, mesmo que o prompt customizado do tenant no banco não a inclua.
GROUNDEDNESS_RULE = (
    "GROUNDEDNESS RULE (CRITICAL): Use ONLY the information provided in the knowledge base context to answer "
    "questions about the business name, services, prices, professionals, or history. NEVER hallucinate, invent, or assume "
    "a business name, service, or professional that is not explicitly present in that context — including generic examples "
    "like 'barbearia', 'André', or any other placeholder business. If the conversation history conflicts with the knowledge "
    "base context, the knowledge base always wins — it is the current source of truth, the history may be stale.\n"
)

# Rede de segurança do chitchat_node. Diferente dos nós institutional/operational,
# este nó NÃO recebe contexto RAG nenhum — não há base de conhecimento no prompt.
# Sem esta regra, quando o roteador erra e manda uma pergunta de negócio para cá,
# o modelo não tem o que citar e inventa a empresa inteira (já aconteceu: respondeu
# "chatbots, integrações CRM/ERP, consultoria" para um tenant que vende outra coisa).
# A regra assume o pior caso do roteador e transforma alucinação em pedido de
# reformulação, que é recuperável pelo usuário.
CHITCHAT_NO_KNOWLEDGE_RULE = (
    "SCOPE RULE (CRITICAL): You have NO knowledge base available in this turn. You therefore do "
    "NOT know this business's products, services, plans, prices, hours, address, staff, or policies. "
    "NEVER state, list, guess, or infer any of them — not even from your own earlier messages in this "
    "conversation, which may themselves be wrong. If the user asks anything factual about the business, "
    "do not answer it: briefly say you'll check that information and invite them to ask it directly "
    "(e.g. 'Sobre isso deixa eu confirmar certinho — pode me perguntar o que gostaria de saber "
    "dos nossos serviços?'), in the user's language. Only handle greetings, farewells and small talk.\n"
)

# Regra de integridade de agendamento, aplicada em cima do prompt operacional
# SOMENTE quando o tenant tem agendamento habilitado (get_active_tools devolveu
# tools de calendário). Substitui os guards antigos que inferiam por palavra
# solta ("ocupado", "livre") na RESPOSTA do modelo — o que gerava falso positivo
# em qualquer texto que mencionasse essas palavras fora de contexto de agenda
# (ex.: "não tenho esse link disponível"). Aqui a política é declarativa e
# condicionada à capacidade real do tenant, não a um casamento de substring.
#
# A privacidade de agenda (não revelar dono/motivo de evento de outro cliente)
# e a regra de um agendamento por vez viviam no guardrail GLOBAL — ou seja, todo
# tenant recebia essas regras mesmo sem nenhuma tool de agendamento habilitada
# (ex.: o simplificandoai, que não agenda nada). Migradas para cá para que só
# cheguem ao modelo quando existe agenda real para proteger.
BOOKING_INTEGRITY_RULE = (
    "BOOKING INTEGRITY RULE (CRITICAL): Never state that a time slot is busy, free, or already "
    "booked, and never confirm that a booking was made, unless a calendar tool call has just "
    "returned that result in this same turn. If the user asks about availability or wants to book, "
    "call the appropriate tool before answering — never answer from memory, from the conversation "
    "history, or from the knowledge base.\n\n"
    "CALENDAR PRIVACY RULE (CRITICAL): When reading calendar data, you will see the title, name, or "
    "description of events belonging to other clients or internal blocks. It is STRICTLY FORBIDDEN to "
    "reveal that title, name, description, or reason to the current user — refer to any such slot "
    "EXCLUSIVELY as \"(ocupado)\". If the user asks directly about the reason, whose event it is, or "
    "what is scheduled during an unavailable time, reply EXACTLY with this phrase: \"Este é um horário "
    "ocupado e, por questões de segurança e privacidade, o sistema não me fornece os detalhes internos "
    "dessa reserva.\"\n\n"
    "REGRA DE MÚLTIPLOS AGENDAMENTOS (CRITICAL): Se o cliente solicitar agendamentos para mais de uma "
    "pessoa ou mais de um horário na mesma mensagem (ex: para ele, filho, esposa), NÃO chame a "
    "ferramenta de agendamento mais de uma vez neste turno. Responda em texto explicando que o "
    "atendimento é feito um agendamento por vez e pergunte qual é o primeiro nome/horário que o "
    "cliente deseja agendar agora.\n"
)

# Instâncias globais dos serviços de infraestrutura.
# Envolvidas em try/except (mesmo padrão do graph_app em chat.py) para que a
# indisponibilidade de infra externa (Postgres, credentials.json) não impeça
# o módulo de ser importado — o erro real só aparece quando o serviço é usado.
try:
    tenant_service = TenantService()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar TenantService: {e}")
    tenant_service = None

try:
    calendar_service = GoogleCalendarService(service_account_path="credentials.json")
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar GoogleCalendarService: {e}")
    calendar_service = None

print("🚀 [GLOBAL] Inicializando Gerenciador de Vetores e Modelo HuggingFace...")
# O modelo sobe para a RAM APENAS UMA VEZ ao ligar o container!
try:
    vector_manager_global = GerenciadorVetores()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar GerenciadorVetores: {e}")
    vector_manager_global = None
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
    temperature=0, 
    extra_body={
        "thinking":{
            "type": "disabled"
        }
    }
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
    """Resolve as tools de agendamento do tenant a partir de uma capacidade
    explícita (`scheduling_enabled`), não de um efeito colateral.

    Antes, a ausência de `google_calendar_id` caía em `static_tools` — ou seja,
    todo tenant recebia tools de agendamento por padrão, mesmo quem não tem
    negócio de agendamento nenhum (ex: um tenant institucional puro). Isso é o
    mesmo fail-open que o EDI-43 eliminou na resolução de prompt, só que em
    tools. Agora quem decide é o campo do tenant: sem agendamento habilitado,
    nenhuma tool de agendamento é oferecida ao modelo, ponto.
    """
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    scheduling_enabled = bool(tenant.get("scheduling_enabled", True)) if tenant else True
    google_calendar_id = tenant.get("google_calendar_id") if tenant else None

    if not scheduling_enabled:
        active_tools = []
        backend = "scheduling_disabled"
    elif google_calendar_id:
        active_tools = get_tenant_tools(tenant_id, tenant_service, calendar_service)
        backend = "google_calendar"
    else:
        active_tools = static_tools
        backend = "internal_fallback"

    print(
        f" -> [TOOL CONFIG] tenant_id={tenant_id} backend={backend} "
        f"scheduling_enabled={scheduling_enabled} google_calendar_id={google_calendar_id!r} "
        f"tools={[tool.name for tool in active_tools]}"
    )
    return active_tools
    
# ============================================================================
# PASSO 3: NÓ ROTEADOR COM GUARDRAIL DE CONTEXTO DUAL (routing_agent)
# ============================================================================
def routing_agent(state: AgentState, config: RunnableConfig):
    """
    Classifica a intenção combinando Guardrail de estado (respostas a perguntas anteriores)
    e envio de histórico nativo para o LLM.
    """
    print("\n --- [NÓ: routing_agent] LLM analisando a intenção do usuário... ---")

    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")

    # A classificação de intenção é decidida inteiramente pelo LLM abaixo — foi
    # removido o atalho por palavra-chave que forçava OPERATIONAL sempre que a
    # ÚLTIMA MENSAGEM DA PRÓPRIA IA continha palavras como "horário" ou "serviço",
    # mesmo fora de contexto de agendamento (ex: "informações sobre nossos
    # serviços, planos ou agendamentos" fazia qualquer resposta do cliente cair
    # em operational_node, inclusive perguntas institucionais).
    # Aciona o LLM passando as mensagens nativas
    system_prompt = SystemMessage(content=(
        "You are an orchestrator router for a business booking application.\n"
        "Classify the intent of THE USER'S LAST MESSAGE ONLY. The earlier conversation is "
        "provided solely to resolve pronouns and ellipsis (e.g. 'e o preço disso?'), NEVER to "
        "decide the class. A streak of previous CHITCHAT turns is NOT evidence that the last "
        "message is CHITCHAT — classify each message on its own merits.\n\n"
        "CLASSIFICATION RULES:\n"
        "1. 'OPERATIONAL': The user wants to book, reschedule, cancel, or is answering a question about a booking "
        "(e.g., providing a barber name, time, date, service, or confirmation).\n"
        "2. 'INSTITUTIONAL': Questions about company address, policies, rules, products, services, "
        "features, or pricing/plans.\n"
        "3. 'CHITCHAT': ONLY when the ENTIRE message is small talk (greeting, farewell, "
        "'tudo bem?', thanks) with NO question about the business, products, services, "
        "pricing, or booking attached. If the message mixes small talk with ANY real "
        "question — even briefly, e.g. 'estou bem, obrigado, o que vocês vendem?' — "
        "classify by the real question's intent (INSTITUTIONAL or OPERATIONAL), NEVER CHITCHAT.\n\n"
        "TIE-BREAKER: CHITCHAT is the LAST RESORT. If the message could plausibly be read as a "
        "question about the business, choose INSTITUTIONAL over CHITCHAT.\n\n"
        "EXAMPLES (last user message -> class):\n"
        "'de nada, o que vcs vendem?' -> INSTITUTIONAL\n"
        "'estou bem, obrigado, o q vcs vendem?' -> INSTITUTIONAL\n"
        "'estes sao seus produtos?' -> INSTITUTIONAL\n"
        "'ue achei q eram produtos de marketing' -> INSTITUTIONAL\n"
        "'oi, quanto custa o plano?' -> INSTITUTIONAL\n"
        "'ta bem, quais serviços vcs tem' -> INSTITUTIONAL\n"
        "'ola' -> CHITCHAT\n"
        "'tudo bem?' -> CHITCHAT\n"
        "'obrigado, ate mais' -> CHITCHAT\n"
        "'quero marcar pra amanha as 15h' -> OPERATIONAL\n\n"
        "CRITICAL: Reply with EXACTLY ONE word: 'OPERATIONAL', 'INSTITUTIONAL', or 'CHITCHAT'."
    ))
    
    # 3. Para o roteador, preserva a sequência AI(tool_calls)->ToolMessage e sanitiza.
    # Isso evita o erro 400 quando há tool_calls no histórico persistido.
    historico_com_tools = [
        m for m in state["messages"]
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]
    historico_bruto = trim_messages(
        historico_com_tools,
        strategy="last",
        token_counter=len,
        max_tokens=8,
        start_on="human",
        end_on=("human", "tool"),
        include_system=False,
    )
    historico_sanitizado = sanitize_for_openai_strict_format(historico_bruto)
    mensagens_para_ia = [system_prompt] + historico_sanitizado

    log_llm_prompt("routing_agent", tenant_id, mensagens_para_ia)
    resposta = llm.invoke(mensagens_para_ia)
    decisao = resposta.content.strip().upper()
    
    if "OPERATIONAL" in decisao:
        decisao = "OPERATIONAL"
    elif "INSTITUTIONAL" in decisao:
        decisao = "INSTITUTIONAL"
    else:
        decisao = "CHITCHAT"
    
    print(f"\n --- [NÓ: routing_agent] Roteador definiu a intenção: [{decisao}] ---")
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
    print(f"\n --- [ARESTA CONDICIONAL] Última mensagem: [{ultima_mensagem}] ---")
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

    # 4. Prompt institutional do tenant (vínculo próprio > fallback para o prompt/guardrails
    # do operational_node do tenant, ver FR-004) + RAG + Histórico de Conversa (EDI-42)
    prompt_final = carregar_institutional_prompt(
        tenant_id=tenant_id,
        contexto_formatado=contexto_formatado,
        historico_texto=historico_texto,
        pergunta_usuario=pergunta_usuario,
    )
    # Reforça a regra anti-alucinação por cima do prompt carregado — necessário porque o
    # template (do banco ou local) não necessariamente a inclui, mesmo padrão do operational_node.
    prompt_final = f"{prompt_final}\n\n{GROUNDEDNESS_RULE}"

    log_llm_prompt("institutional_node", tenant_id, prompt_final)
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
    print("\n --- [NÓ: operational_node] Modelo avaliando fluxo de atendimento... ---")
    
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

    # As tools são resolvidas ANTES do prompt para que BOOKING_INTEGRITY_RULE
    # só entre quando o tenant realmente tem agendamento habilitado.
    all_active_tools = get_active_tools(tenant_id)

    tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(7)
    system_prompt_str = carregar_operacional_prompt(
                            tenant_id=tenant_id,
                            tabela_calendario_str=tabela_dias,
                            hora_atual_str=hora_atual_str,
                            data_hoje_iso=data_hoje_iso,
                            contexto_formatado=contexto_formatado
                        )

    # Reforça a regra anti-alucinação por cima do prompt carregado — necessário porque
    # carregar_operacional_prompt() pode devolver um prompt customizado do tenant vindo do
    # banco, que não necessariamente inclui a GROUNDEDNESS RULE presente no fallback local.
    system_prompt_str = f"{system_prompt_str}\n\n{GROUNDEDNESS_RULE}"
    if all_active_tools:
        system_prompt_str = f"{system_prompt_str}\n\n{BOOKING_INTEGRITY_RULE}"

    # Injeta dados de contato já vistos na sessão para evitar perguntas repetidas.
    profile = extract_customer_profile(state["messages"])
    customer_context = build_customer_context_block(profile)
    if customer_context:
        system_prompt_str = f"{system_prompt_str}{customer_context}"

    # 1. Filtramos as decisões do roteador das mensagens
    mensagens_chat = [
        m for m in state["messages"] 
        if not (isinstance(m, AIMessage) and str(m.content).startswith("Routing decision:"))
    ]
   # LINHAS DE ALTERAÇÃO - SUBSTITUIR A TRUNCAGEM MANUAL PELO TRIM_MESSAGES
    # COMENTÁRIO: Substitui o slice manual e o 'if' de shift pelo trim_messages nativo.
    # O 'token_counter=len' conta mensagens (não tokens), e o 'start_on="human"' garante
    # que o histórico nunca comece com ToolMessage órfã, recuando quantas posições forem necessárias.
    historico_bruto = trim_messages(
        mensagens_chat,
        strategy="last",
        token_counter=len,          # Trata cada mensagem como 1 unidade (corta por quantidade)
        max_tokens=50,               # Mantém janela maior para reduzir perda de contexto imediato
        start_on="human",            # Garante que o histórico corte sempre até achar uma mensagem do usuário
        end_on=("human", "tool"),    # Impede encerramento inválido em AIMessage sem resposta
        include_system=False         # O SystemMessage é montado separadamente na linha abaixo
    )
    historico_limitado = sanitize_for_openai_strict_format(historico_bruto)

    # 2. SEGREDO DO LANGGRAPH: Montamos o SystemMessage + TODO O HISTÓRICO REAL (incluindo ToolMessages)
    # REMOVER: mensagens_para_ia = [SystemMessage(content=system_prompt_str)] + mensagens_chat
    mensagens_para_ia = [SystemMessage(content=system_prompt_str)] + historico_limitado

    # 3. Disponibiliza somente as tools do backend configurado para o tenant.
    llm_dynamic = llm.bind_tools(all_active_tools, parallel_tool_calls=False)

    log_llm_prompt("operational_node", tenant_id, mensagens_para_ia)
    resposta_ia = llm_dynamic.invoke(mensagens_para_ia)

    # BLINDAGEM: Se o modelo ignorar a instrução do prompt e ainda assim mandar várias
    # tool calls de uma vez, mantemos apenas a primeira. O ideal é que o PROMPT já
    # oriente o modelo a pedir ao cliente para enviar um agendamento por vez quando
    # detectar múltiplos pedidos na mesma mensagem — isso aqui é só a última linha
    # de defesa, não a solução principal.
    if hasattr(resposta_ia, "tool_calls") and resposta_ia.tool_calls and len(resposta_ia.tool_calls) > 1:
        total_recebido = len(resposta_ia.tool_calls)
        descartadas = resposta_ia.tool_calls[1:]
        print(f" -> 🛡️ [GUARDRAIL] Modelo tentou {total_recebido} tool calls em paralelo apesar "
              f"da instrução do prompt. Mantendo: {resposta_ia.tool_calls[0]['name']}. "
              f"Descartadas: {[tc['name'] for tc in descartadas]}")

        resposta_ia.tool_calls = resposta_ia.tool_calls[:1]

        if "tool_calls" in resposta_ia.additional_kwargs:
            resposta_ia.additional_kwargs["tool_calls"] = resposta_ia.additional_kwargs["tool_calls"][:1]

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

    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", "default_tenant")

    # 1. Carrega o prompt do chitchat_node do tenant (vínculo próprio > padrão do nó >
    # texto fixo local), já com os guardrails aplicáveis embutidos (EDI-42)
    system_prompt_str = carregar_chitchat_prompt(tenant_id)

    # Mesmo padrão do institutional_node: reforça a regra por cima do prompt carregado,
    # porque o template (do banco ou local) não necessariamente a inclui.
    system_prompt_str = f"{system_prompt_str}\n\n{CHITCHAT_NO_KNOWLEDGE_RULE}"

    # 2. Preserva histórico real (incluindo ToolMessages) e sanitiza sequência.
    historico_com_tools = [
        msg for msg in state["messages"]
        if not (isinstance(msg, AIMessage) and str(msg.content).startswith("Routing decision:"))
    ]
    historico_bruto = trim_messages(
        historico_com_tools,
        strategy="last",
        token_counter=len,
        max_tokens=6,
        start_on="human",
        end_on=("human", "tool"),
        include_system=False,
    )
    historico_sanitizado = sanitize_for_openai_strict_format(historico_bruto)

    # 3. MONTA O PROMPT CORRETO COMO SystemMessage (E NÃO AIMessage)
    system_prompt = SystemMessage(content=system_prompt_str)

    # Envia o SystemMessage no topo + histórico sanitizado
    mensagens_para_ia = [system_prompt] + historico_sanitizado
    
    try:
        log_llm_prompt("chitchat_node", tenant_id, mensagens_para_ia)
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
import copy
import re
import unicodedata
from typing import Sequence
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


# ============================================================================
# ALGORITMO DEFINITIVO DE BLINDAGEM DE HISTÓRICO (STRICT SEQUENCE)
# ============================================================================
def sanitize_for_openai_strict_format(messages: list) -> list:
    """
    Garante a ordem estrita exigida pela API: 
    Toda AIMessage com tool_calls DEVE ser seguida imediatamente pelas suas ToolMessages.
    Qualquer interrupção (ex: usuário mandar mensagem no meio) ou ferramenta órfã é expurgada.
    Impede o envio de AIMessages vazias.
    """
    safe_messages = []
    i = 0
    
    while i < len(messages):
        m = messages[i]
        
        # 1. Se a IA chamou uma ferramenta...
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            j = i + 1
            tool_responses = []
            
            # 2. Olha para a frente: captura APENAS as ToolMessages que vieram coladas logo em seguida
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_responses.append(messages[j])
                j += 1
            
            # 3. Verifica quais tool_calls dessa mensagem realmente estão no bloco colado a ela
            found_ids = {tm.tool_call_id for tm in tool_responses}
            valid_tcs = [tc for tc in m.tool_calls if tc["id"] in found_ids]
            
            # 4. Reconstrói a mensagem da IA de forma segura
            if valid_tcs:
                m_copy = copy.deepcopy(m)
                m_copy.tool_calls = valid_tcs
                if hasattr(m_copy, "additional_kwargs") and "tool_calls" in m_copy.additional_kwargs:
                    m_copy.additional_kwargs["tool_calls"] = [
                        tc for tc in m_copy.additional_kwargs["tool_calls"]
                        if tc.get("id") in found_ids
                    ]
                safe_messages.append(m_copy)
                safe_messages.extend(tool_responses)
            else:
                # 5. Se as ferramentas foram cortadas, mantemos a mensagem APENAS se ela tiver texto.
                # Se for vazia, nós a destruímos completamente para evitar o Erro 400.
                if m.content:
                    m_copy = copy.deepcopy(m)
                    m_copy.tool_calls = []
                    if hasattr(m_copy, "additional_kwargs") and "tool_calls" in m_copy.additional_kwargs:
                        del m_copy.additional_kwargs["tool_calls"]
                    safe_messages.append(m_copy)
            
            i = j  # Avança o ponteiro pulando as ToolMessages que já inserimos
            
        elif isinstance(m, ToolMessage):
            # 6. Se acharmos uma ToolMessage solta (sem estar atrelada a uma AIMessage), ela é órfã. Destruir.
            i += 1
            
        elif isinstance(m, AIMessage) and not m.content and not getattr(m, "tool_calls", None):
            # 7. Se for uma AIMessage 100% vazia (sem texto e sem ferramentas), destruir.
            i += 1
            
        else:
            # 8. Mensagens normais (HumanMessage, SystemMessage ou AIMessage só com texto) passam livremente.
            safe_messages.append(m)
            i += 1
            
    return safe_messages



EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}")
NAME_RE = re.compile(r"(?:meu nome(?: completo)?\s*é|nome\s*[:\-]|sou)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s']{2,50})", re.IGNORECASE)


def extract_customer_profile(messages: Sequence[BaseMessage]) -> dict:
    """
    Extrai dados de contato já informados ao longo da sessão.

    Considera EXCLUSIVAMENTE mensagens do cliente (HumanMessage). Nunca lê
    AIMessage/ToolMessage: se a própria assistente disser "meu nome é Aline" ao
    se apresentar, ou repetir um e-mail/telefone em uma resposta, esse texto
    não pode contaminar o perfil do cliente (bug real: sessão chegou a herdar
    "Nome: Aline" a partir da fala da própria IA).
    """
    profile = {"nome": None, "email": None, "telefone": None}

    for msg in reversed(messages):
        if not isinstance(msg, HumanMessage):
            continue

        content = str(getattr(msg, "content", "") or "")
        if not content:
            continue

        if not profile["email"]:
            m_email = EMAIL_RE.search(content)
            if m_email:
                profile["email"] = m_email.group(0)

        if not profile["telefone"]:
            m_phone = PHONE_RE.search(content)
            if m_phone:
                profile["telefone"] = m_phone.group(0)

        if not profile["nome"]:
            m_name = NAME_RE.search(content)
            if m_name:
                profile["nome"] = " ".join(m_name.group(1).split())

        if profile["nome"] and profile["email"] and profile["telefone"]:
            break

    return profile


def build_customer_context_block(profile: dict) -> str:
    dados = []
    if profile.get("nome"):
        dados.append(f"- Nome: {profile['nome']}")
    if profile.get("email"):
        dados.append(f"- Email: {profile['email']}")
    if profile.get("telefone"):
        dados.append(f"- Telefone: {profile['telefone']}")

    if not dados:
        return ""

    return (
        "\n\nKNOWN CUSTOMER CONTEXT (SESSION MEMORY):\n"
        + "\n".join(dados)
        + "\nCRITICAL: Reuse these fields when the user asks to continue booking/rescheduling. "
          "Do not ask again for fields that are already known; at most confirm in one short sentence."
    )


BOOKING_TOOL_NAMES = {"agendar_horario", "confirmar_agendamento"}
AVAILABILITY_TOOL_NAMES = {"consultar_agenda", "consultar_horarios_disponiveis"}
BOOKING_SUCCESS_MARKERS = (
    "agendamento confirmado com sucesso",
    "agendamento realizado com sucesso",
    "agendamento foi confirmado",
    "agendamento foi agendado",
    "foi agendado com sucesso",
    "reserva confirmada",
    "reserva criada",
    "horario reservado",
    "horario agendado",
    "evento criado",
    "convite enviado",
    # Variacoes mais curtas que o modelo usa sem dizer "com sucesso" explicitamente -
    # sem isso, uma confirmacao fabricada (sem chamar a tool) passava pelo guard.
    "agendamento esta confirmado",
    "seu agendamento esta confirmado",
    "agendamento confirmado",
    "esta confirmado",
    "ja esta agendado",
    "ja esta marcado",
)
BOOKING_CONFIRMATION_PROMPTS = (
    "posso confirmar esse agendamento",
    "posso confirmar o agendamento",
    "deseja confirmar esse agendamento",
    "deseja confirmar o agendamento",
    "quer que eu confirme esse agendamento",
    "quer que eu confirme o agendamento",
    "vou confirmar os dados do agendamento",
)
AFFIRMATIVE_MARKERS = (
    "sim",
    "confirmo",
    "pode confirmar",
    "pode agendar",
    "pode marcar",
    "ok",
    "okay",
    "fechado",
    "isso",
    "correto",
)

AVAILABILITY_REQUEST_MARKERS = (
    "tem horario",
    "tem horarios",
    "tem vaga",
    "esta ocupado",
    "está ocupado",
    "esta livre",
    "está livre",
    "disponivel",
    "disponível",
    "disponibilidade",
    "verificar disponibilidade",
    "consultar agenda",
    "consultar horarios",
    "consultar horários",
    "qual horario",
    "qual horário",
)
BOOKING_SELECTION_MARKERS = (
    "pode ser",
    "pode marcar",
    "pode agendar",
    "quero as",
    "quero o",
    "vou querer",
    "prefiro as",
    "prefiro o",
    "marca as",
    "marca pra",
    "agenda as",
    "agenda pra",
    "agendar as",
    "agendar pra",
    "fechar as",
    "fechado as",
)
AVAILABILITY_SUCCESS_MARKERS = (
    "esta ocupado",
    "está ocupado",
    "estao ocupados",
    "estão ocupados",
    "esta livre",
    "está livre",
    "disponivel",
    "disponível",
    "ocupado",
    "livre",
    "horarios ocupados",
    "horários ocupados",
)
# Afirmacoes sobre agendamento ja existente tambem sao fatos de calendario:
# so podem ser ditas apos consulta fresca ao Google, nunca a partir do checkpoint.
EXISTING_APPOINTMENT_MARKERS = (
    "ja tem um agendamento",
    "ja tem agendamento",
    "voce tem um agendamento",
    "tem um agendamento",
    "ja possui um agendamento",
    "possui um agendamento",
    "ja existe um agendamento",
    "existe um agendamento",
)
AVAILABILITY_BLOCK_MARKERS = (
    "nenhum horario foi reservado",
    "nenhum horário foi reservado",
    "nao consegui registrar esse agendamento",
    "não consegui registrar esse agendamento",
)
# Indicadores de que a consulta ao calendario falhou (nao ha dado fresco confiavel).
AVAILABILITY_TOOL_ERROR_MARKERS = (
    "erro:",
    "ocorreu um erro",
    "nao foi possivel",
    "não foi possível",
    "nao possui um google calendar",
    "não possui um google calendar",
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def response_claims_booking_success(content: str) -> bool:
    normalized = normalize_text(content)
    return any(marker in normalized for marker in BOOKING_SUCCESS_MARKERS)


def response_reasks_booking_confirmation(content: str) -> bool:
    normalized = normalize_text(content)
    return any(marker in normalized for marker in BOOKING_CONFIRMATION_PROMPTS)


def is_affirmative_text(content: str) -> bool:
    normalized = normalize_text(content)
    if not normalized:
        return False
    return normalized in AFFIRMATIVE_MARKERS or any(
        normalized.startswith(marker) for marker in AFFIRMATIVE_MARKERS
    )


def has_pending_booking_confirmation(messages: Sequence[BaseMessage]) -> bool:
    last_human = None
    previous_ai = None

    for msg in reversed(messages):
        if last_human is None and getattr(msg, "type", None) == "human":
            last_human = str(getattr(msg, "content", "") or "")
            continue

        if last_human is not None and isinstance(msg, AIMessage):
            previous_ai = str(getattr(msg, "content", "") or "")
            break

    if not last_human or not previous_ai:
        return False

    return is_affirmative_text(last_human) and response_reasks_booking_confirmation(previous_ai)


def latest_user_message(messages: Sequence[BaseMessage]) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            return str(getattr(msg, "content", "") or "")
    return ""


def user_is_asking_for_availability(messages: Sequence[BaseMessage]) -> bool:
    normalized = normalize_text(latest_user_message(messages))
    if any(marker in normalized for marker in BOOKING_SELECTION_MARKERS):
        return False
    return any(marker in normalized for marker in AVAILABILITY_REQUEST_MARKERS)


def user_selected_booking_slot(messages: Sequence[BaseMessage]) -> bool:
    normalized = normalize_text(latest_user_message(messages))
    return any(marker in normalized for marker in BOOKING_SELECTION_MARKERS)


def recent_availability_tool_succeeded(messages: Sequence[BaseMessage]) -> bool:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            break

        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) in AVAILABILITY_TOOL_NAMES:
            normalized = normalize_text(str(getattr(msg, "content", "") or ""))
            if not normalized:
                return False
            # Sucesso = a consulta ao calendario rodou e NAO retornou erro, independentemente
            # do texto. O tool do Google retorna "Eventos encontrados..." ou "Nenhum agendamento...",
            # que sao respostas validas e frescas da fonte de verdade.
            return not any(marker in normalized for marker in AVAILABILITY_TOOL_ERROR_MARKERS)

    return False


def recent_booking_tool_succeeded(messages: Sequence[BaseMessage]) -> bool:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            break

        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) in BOOKING_TOOL_NAMES:
            return response_claims_booking_success(str(getattr(msg, "content", "") or ""))

    return False


def recent_tool_content(messages: Sequence[BaseMessage], tool_names: set[str]) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            break

        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) in tool_names:
            return str(getattr(msg, "content", "") or "")

    return ""


def build_booking_retry_context_block(messages: Sequence[BaseMessage], profile: dict | None = None) -> str:
    latest_user = latest_user_message(messages)
    availability_result = recent_tool_content(messages, AVAILABILITY_TOOL_NAMES)
    booking_result = recent_tool_content(messages, BOOKING_TOOL_NAMES)

    lines = ["BOOKING RETRY CONTEXT (USE THIS TO CALL agendar_horario):"]

    if latest_user:
        lines.append(f"- Latest user message: {latest_user}")

    if availability_result:
        lines.append(f"- Latest availability result: {availability_result}")

    if booking_result:
        lines.append(f"- Latest booking tool result: {booking_result}")

    if profile:
        if profile.get("nome"):
            lines.append(f"- Nome: {profile['nome']}")
        if profile.get("email"):
            lines.append(f"- Email: {profile['email']}")
        if profile.get("telefone"):
            lines.append(f"- Telefone: {profile['telefone']}")

    lines.append(
        "INSTRUCTION: If the selected slot is available and the required booking fields are already present in the chat history, call agendar_horario immediately. "
        "Do not ask the user to confirm again and do not answer only in text."
    )

    return "\n".join(lines)


def should_retry_booking_tool_call(messages: Sequence[BaseMessage], ai_response: AIMessage) -> bool:
    if getattr(ai_response, "tool_calls", None):
        return False

    if recent_booking_tool_succeeded(messages):
        return False

    return (
        has_pending_booking_confirmation(messages)
        or user_selected_booking_slot(messages)
        or response_claims_booking_success(str(getattr(ai_response, "content", "") or ""))
    )


def should_block_unverified_booking_response(messages: Sequence[BaseMessage], ai_response: AIMessage) -> bool:
    if getattr(ai_response, "tool_calls", None):
        return False

    if recent_booking_tool_succeeded(messages):
        return False

    content = str(getattr(ai_response, "content", "") or "")
    return response_claims_booking_success(content) or (
        has_pending_booking_confirmation(messages)
        and response_reasks_booking_confirmation(content)
    )


def should_retry_availability_tool_call(messages: Sequence[BaseMessage], ai_response: AIMessage) -> bool:
    if getattr(ai_response, "tool_calls", None):
        return False

    if recent_availability_tool_succeeded(messages):
        return False

    content = str(getattr(ai_response, "content", "") or "")
    # Dispara sempre que a IA AFIRMA estado de calendario (ocupado/livre/agendamento existente)
    # sem uma consulta fresca ter tido sucesso neste turno, independentemente de como o usuario
    # formulou a mensagem. O Google Calendar e a unica fonte de verdade; historico nao vale.
    return response_claims_availability(content)


def response_claims_availability(content: str) -> bool:
    normalized = normalize_text(content)
    return any(marker in normalized for marker in AVAILABILITY_SUCCESS_MARKERS) or any(
        marker in normalized for marker in EXISTING_APPOINTMENT_MARKERS
    )


def should_block_unverified_availability_response(messages: Sequence[BaseMessage], ai_response: AIMessage) -> bool:
    if getattr(ai_response, "tool_calls", None):
        return False

    if recent_availability_tool_succeeded(messages):
        return False

    content = str(getattr(ai_response, "content", "") or "")
    # Bloqueia qualquer afirmacao de estado de calendario que nao venha de uma consulta
    # fresca ao Google neste turno, mesmo que o usuario tenha pedido para agendar um slot.
    return response_claims_availability(content) or any(
        marker in normalize_text(content) for marker in AVAILABILITY_BLOCK_MARKERS
    )
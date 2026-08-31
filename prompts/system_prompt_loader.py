"""Carregamento dos prompts de sistema (EDI-71) — routing_agent, GROUNDEDNESS_RULE,
CHITCHAT_NO_KNOWLEDGE_RULE e BOOKING_INTEGRITY_RULE.

Diferente de `prompts/load_prompt.py` (prompts POR TENANT, vindos de
`modules/prompt_manager`), este módulo resolve prompts GLOBAIS de
`modules/system_prompts` — não há tenant_id envolvido na busca.

Mesma política de fallback do resto do projeto: falha de INFRAESTRUTURA
(banco indisponível, linha ainda não semeada) cai no texto hardcoded local
abaixo, mantendo o atendimento em pé. Esse fallback é deliberadamente mantido
mesmo após a migração completa (fora de escopo do EDI-71 removê-lo).
"""

import re

from infrastructure.connection import get_db_connection
from modules.system_prompts.system_prompts_repository import SystemPromptsRepository
from modules.observability.interface.logger_factory import get_logger as get_obs_logger

# --- Fallback local hardcoded — cópia congelada do que já vivia em agent_graph.py ---

_FALLBACK_ROUTING_AGENT_TEMPLATE = (
    "You are an orchestrator router for a business booking application.\n"
    "Classify the intent of THE USER'S LAST MESSAGE ONLY. The earlier conversation is "
    "provided solely to resolve pronouns and ellipsis (e.g. 'e o preço disso?'), NEVER to "
    "decide the class. A streak of previous CHITCHAT turns is NOT evidence that the last "
    "message is CHITCHAT — classify each message on its own merits.\n\n"
    "CLASSIFICATION RULES:\n"
    "1. 'OPERATIONAL': The user wants to book, reschedule, cancel, or is answering a question about a booking "
    "(e.g., providing a barber name, time, date, service, or confirmation).\n"
    "2. 'INSTITUTIONAL': Questions about company address, policies, rules, products, services, features, or pricing/plans.\n"
    "3. 'CHITCHAT': ONLY when the ENTIRE message is small talk (greeting, farewell, "
    "'tudo bem?', 'olá tudo bem?', thanks) with NO question about the business, products, services, pricing, or booking attached. If the message mixes small "
    "talk with "
    "question e.g. 'o que vocês vendem?' - "
    "classify by the real question's intent (INSTITUTIONAL or OPERATIONAL) \n\n" "CHITCHAT, WHEN ASKING tudo bem? you respond I am good how may I help you?.\n"
    "4. 'CONTINUATION': If the last message carries NO topic of its own — a conversational "
    "repair signal ('não entendi', 'como assim?', 'hein?', 'oi?', 'quê?'), a bare "
    "acknowledgement ('ok', 'sim', 'isso'), or a fragment only meaningful against the "
    "previous turn — it is NOT CHITCHAT. Classify it the SAME as PREVIOUS TURN INTENT "
    "(given below). This takes priority over rule 3.\n\n"
    "TIE-BREAKER: CHITCHAT is the LAST RESORT. If the message could plausibly be read as a "
    "question about the business, or as a continuation of the previous turn, choose "
    "INSTITUTIONAL/OPERATIONAL over CHITCHAT.\n\n"
    "PREVIOUS TURN INTENT: {previous_turn_intent}\n\n"
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
    "'quero marcar pra amanha as 15h' -> OPERATIONAL\n"
    "'não entendi' (PREVIOUS TURN INTENT: OPERATIONAL) -> CONTINUATION\n"
    "'como assim?' (PREVIOUS TURN INTENT: INSTITUTIONAL) -> CONTINUATION\n\n"
    "CRITICAL: Reply with EXACTLY ONE word: 'OPERATIONAL', 'INSTITUTIONAL', 'CHITCHAT', or "
    "'CONTINUATION'."
)

_FALLBACK_GROUNDEDNESS_RULE = (
    "GROUNDEDNESS RULE (CRITICAL): Use ONLY the information provided in the knowledge base context to answer "
    "questions about the business name, services, prices, professionals, or history. NEVER hallucinate, invent, or assume "
    "a business name, service, or professional that is not explicitly present in that context — including generic examples "
    "like 'barbearia', 'André', or any other placeholder business. If the conversation history conflicts with the knowledge "
    "base context, the knowledge base always wins — it is the current source of truth, the history may be stale.\n\n"
    "SELF-CITATION RULE (CRITICAL): Your own previous messages in this conversation are NEVER evidence that a "
    "tool was called or that an action happened. If you cannot see an actual tool result in the CURRENT context, "
    "the action did not happen — even if an earlier message in the history claimed otherwise.\n"
)

_FALLBACK_CHITCHAT_NO_KNOWLEDGE_RULE = (
    "SCOPE RULE (CRITICAL): You have NO knowledge base available in this turn. You therefore do "
    "NOT know this business's products, services, plans, prices, hours, address, staff, or policies. "
    "NEVER state, list, guess, or infer any of them — not even from your own earlier messages in this "
    "conversation, which may themselves be wrong. If the user asks anything factual about the business, "
    "do not answer it: briefly say you'll check that information and invite them to ask it directly "
    "(e.g. 'Sobre isso deixa eu confirmar certinho — pode me perguntar o que gostaria de saber "
    "dos nossos serviços?'), in the user's language. Only handle greetings, farewells and small talk.\n"
)

_FALLBACK_BOOKING_INTEGRITY_RULE = (
    "BOOKING INTEGRITY RULE (CRITICAL): Never state that a time slot is busy, free, or already "
    "booked, and never confirm that a booking was made, unless a calendar tool call has just "
    "returned that result in this same turn. If the user asks about availability or wants to book, "
    "call the appropriate tool before answering — never answer from memory, from the conversation "
    "history, or from the knowledge base.\n\n"
    "NO NARRATION RULE (CRITICAL): NEVER announce that you are about to check, consult, or verify "
    "something ('vou verificar', 'um momento', 'deixa eu consultar a agenda', 'verificando a "
    "disponibilidade') and then answer as if that check already happened. Either call the tool "
    "silently in this same turn and wait for its real result, or ask the user a question — never "
    "narrate an action you have not actually taken yet.\n\n"
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

# Casa apenas placeholders simples do tipo {nome_da_chave} — mesma técnica de
# `prompts/load_prompt.py`: um placeholder desconhecido (ex.: um exemplo JSON
# colado pelo admin) fica intacto no texto em vez de estourar KeyError.
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _render(template: str, **valores) -> str:
    def _substituir(match):
        chave = match.group(1)
        if chave in valores:
            return str(valores[chave])
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_substituir, template)


def _buscar_current_version(prompt_key: str) -> str:
    """Busca `current_version` no banco. Levanta exceção (sobe para o
    chamador) se o banco estiver indisponível ou o `prompt_key` não existir
    ainda — quem decide o fallback é sempre a função pública abaixo, nunca
    esta."""
    repository = SystemPromptsRepository(get_db_connection)
    prompt = repository.get_by_key(prompt_key)
    if prompt is None:
        raise ValueError(f"system_prompts sem linha para prompt_key={prompt_key!r}")
    return prompt["current_version"]


def _carregar_com_fallback(prompt_key: str, fallback: str) -> str:
    try:
        return _buscar_current_version(prompt_key)
    except Exception as e:
        print(f"[WARN] Falha ao carregar system prompt {prompt_key!r} do banco: {e}. Usando fallback local.")
        get_obs_logger(tenant_id="system", tenant_name="system", agent="system_prompt_loader").error(
            message=f"Failed to load system prompt {prompt_key!r} from DB, using local fallback: {e}",
            method="prompts.system_prompt_loader._carregar_com_fallback",
            line=0,
            thread_id="unknown",
            extra={"error": str(e), "prompt_key": prompt_key},
        )
        return fallback


def carregar_groundedness_rule() -> str:
    return _carregar_com_fallback("groundedness_rule", _FALLBACK_GROUNDEDNESS_RULE)


def carregar_chitchat_no_knowledge_rule() -> str:
    return _carregar_com_fallback("chitchat_no_knowledge_rule", _FALLBACK_CHITCHAT_NO_KNOWLEDGE_RULE)


def carregar_booking_integrity_rule() -> str:
    return _carregar_com_fallback("booking_integrity_rule", _FALLBACK_BOOKING_INTEGRITY_RULE)


def carregar_routing_agent_prompt(previous_turn_intent: str) -> str:
    """Carrega o template do routing_agent (do banco, com fallback local) e
    renderiza o placeholder `{previous_turn_intent}`."""
    template = _carregar_com_fallback("routing_agent", _FALLBACK_ROUTING_AGENT_TEMPLATE)
    return _render(template, previous_turn_intent=previous_turn_intent)

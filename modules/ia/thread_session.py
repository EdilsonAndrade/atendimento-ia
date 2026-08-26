"""Controla a expiração automática de sessões de conversa por inatividade.

Problema que isso resolve: o thread_id do widget/WhatsApp fica salvo no localStorage
(ou é o próprio telefone do cliente), então o mesmo thread_id pode ser reutilizado por
dias/semanas. O LangGraph carrega o histórico completo por thread_id, e datas relativas
("amanhã") mencionadas em turnos antigos podem enviesar o modelo em conversas futuras.
Como não dá para depender do cliente/navegador para "abrir uma conversa nova", a expiração
é decidida aqui no backend: se o cliente ficou muito tempo sem mandar mensagem nesse
thread_id, geramos automaticamente um novo thread_id "de sessão" para o LangGraph,
mantendo o thread_id original (base) apenas como chave de rastreio.
"""
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

import psycopg

from infrastructure.connection import DB_URI

logger = logging.getLogger(__name__)

SESSION_IDLE_MINUTES = float(os.getenv("CHAT_SESSION_IDLE_MINUTES", "360"))


def resolve_active_thread_id(base_thread_id: str, idle_minutes: float = SESSION_IDLE_MINUTES) -> str:
    """Retorna o thread_id real a ser usado pelo LangGraph para esta requisição.

    Enquanto o cliente interagir dentro da janela de `idle_minutes`, o mesmo thread_id de
    sessão é reaproveitado (mantendo contexto/nome/e-mail já informados). Se o gap desde
    a última mensagem ultrapassar `idle_minutes`, uma NOVA sessão é gerada automaticamente
    para esse `base_thread_id`, isolando o histórico e evitando datas relativas antigas.

    A tabela `chat_thread_sessions` é criada pelas migrations em `migrations/` (EDI-37).
    """
    now = datetime.now(timezone.utc)

    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT active_thread_id, last_seen_at FROM chat_thread_sessions WHERE base_thread_id = %s;",
                    (base_thread_id,),
                )
                row = cur.fetchone()

                expired_active_thread_id = None

                if row is None:
                    active_thread_id = f"{base_thread_id}#{uuid.uuid4().hex[:12]}"
                else:
                    active_thread_id, last_seen_at = row
                    elapsed_minutes = (now - last_seen_at).total_seconds() / 60
                    if elapsed_minutes >= idle_minutes:
                        expired_active_thread_id = active_thread_id
                        active_thread_id = f"{base_thread_id}#{uuid.uuid4().hex[:12]}"

                cur.execute(
                    """
                    INSERT INTO chat_thread_sessions (base_thread_id, active_thread_id, last_seen_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (base_thread_id)
                    DO UPDATE SET active_thread_id = EXCLUDED.active_thread_id, last_seen_at = EXCLUDED.last_seen_at;
                    """,
                    (base_thread_id, active_thread_id, now),
                )

        if expired_active_thread_id:
            # Gera resumo + fatos estruturados (Camada 2 de memória, EDI-59) em uma thread
            # separada, para NUNCA atrasar a resposta ao cliente da mensagem atual (Princípio V
            # da constituição — trabalho de LLM não pode bloquear o ciclo request/response).
            # Uma falha aqui é apenas logada; a sessão já foi resolvida normalmente acima.
            threading.Thread(
                target=generate_and_store_session_summary,
                args=(base_thread_id, expired_active_thread_id),
                daemon=True,
            ).start()

        return active_thread_id
    except Exception as e:
        print(f"⚠️ Erro ao resolver sessão de thread para {base_thread_id}: {e}. Usando thread_id base.")
        return base_thread_id


def _get_session_messages(active_thread_id: str) -> list:
    """Lê o histórico de mensagens já persistido pelo PostgresSaver do LangGraph para
    `active_thread_id`, sem precisar recompilar o grafo inteiro — só o checkpoint mais
    recente daquela thread."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
        checkpointer = PostgresSaver(conn)
        tup = checkpointer.get_tuple({"configurable": {"thread_id": active_thread_id}})
        if not tup or not tup.checkpoint:
            return []
        return tup.checkpoint.get("channel_values", {}).get("messages", []) or []


def _extract_tenant_id(base_thread_id: str) -> str:
    """`base_thread_id` é sempre `f"{tenant_id}:{sessao}"` (app/api/v1/endpoints/chat.py,
    modules/webhook/whatsapp.py) — extrai o tenant_id sem depender de um parâmetro novo
    em `resolve_active_thread_id` (que hoje só recebe o thread_id composto)."""
    return base_thread_id.split(":", 1)[0] if base_thread_id else base_thread_id


def _summarize_session(
    messages: list,
    tenant_id: str,
    base_thread_id: str,
    active_thread_id: str,
    oferta_vigente_texto: str | None = None,
    oferta_vigente_validade=None,
) -> dict:
    """Monta o texto da conversa e delega a classificação (resumo + fatos + outcome +
    follow_up_draft, EDI-53) para `ClassifySessionOutcomeUseCase` — uma ÚNICA chamada
    de LLM que substitui a antiga chamada só-de-resumo (ver
    specs/011-conversation-history-followup/research.md §1). Nunca inventa campo que
    não puder ser identificado na conversa (FR-011) — o próprio prompt instrui o
    modelo a usar null nesse caso.

    EDI-61: o texto do 'Atendente' (mensagens ai) é gerado por um LLM e pode alegar uma
    confirmação/cancelamento de agendamento que nunca aconteceu de fato (o "agendamento
    fantasma" do incidente original). Por isso as ToolMessage do histórico — o único
    resultado real de uma ação de calendário — também entram no texto analisado, como
    linhas separadas e explicitamente marcadas como a única fonte confiável sobre o que
    de fato ocorreu, para o campo `resultado`/`outcome='fechado'` nunca ser preenchido
    com base só na palavra do Atendente."""
    linhas_conversa = []
    for m in messages:
        tipo = getattr(m, "type", None)
        conteudo = str(getattr(m, "content", "") or "").strip()
        if not conteudo:
            continue
        if tipo == "human":
            linhas_conversa.append(f"Cliente: {conteudo}")
        elif tipo == "ai":
            linhas_conversa.append(f"Atendente: {conteudo}")
        elif tipo == "tool":
            linhas_conversa.append(f"Resultado real de ferramenta (fonte confiável, não é o que o Atendente disse): {conteudo}")

    conversa_texto = "\n".join(linhas_conversa)
    if not conversa_texto.strip():
        return {"resumo": "", "fatos": {}}

    from modules.follow_up.application.classify_session_outcome import ClassifySessionOutcomeUseCase
    from modules.follow_up.infrastructure.llm_session_outcome_classifier import LlmSessionOutcomeClassifier
    from modules.follow_up.infrastructure.postgres_follow_up_queue_repository import (
        PostgresFollowUpQueueRepository,
    )

    use_case = ClassifySessionOutcomeUseCase(PostgresFollowUpQueueRepository(), LlmSessionOutcomeClassifier())
    resultado = use_case.execute(
        tenant_id, base_thread_id, active_thread_id, conversa_texto,
        oferta_vigente_texto, oferta_vigente_validade,
    )
    if resultado is None:
        return {"resumo": "", "fatos": {}}
    return resultado


def generate_and_store_session_summary(base_thread_id: str, expired_active_thread_id: str) -> None:
    """Gera e persiste o resumo/fatos estruturados de uma sessão que acabou de expirar
    por inatividade. Roda em background (thread daemon disparada por
    `resolve_active_thread_id`) — qualquer falha aqui é só logada, nunca propagada
    (FR-010: não pode atrasar nem bloquear a expiração/nova sessão do cliente)."""
    try:
        messages = _get_session_messages(expired_active_thread_id)
        if not messages:
            return

        tenant_id = _extract_tenant_id(base_thread_id)

        # EDI-53: liga a oferta comercial real do tenant no guardrail do rascunho de
        # follow-up (US3) — falha ao buscar o tenant não deve impedir o resumo/outcome
        # de serem gerados, só faz o draft nascer sem nenhuma oferta citável.
        oferta_vigente_texto = None
        oferta_vigente_validade = None
        try:
            from modules.tenant.tenant_service import TenantService

            tenant = TenantService().get_tenant_by_id(tenant_id)
            if tenant:
                oferta_vigente_texto = tenant.get("oferta_vigente_texto")
                oferta_vigente_validade = tenant.get("oferta_vigente_validade")
        except Exception as exc:
            logger.error(
                "Falha ao buscar oferta_vigente do tenant %s para o rascunho de follow-up: %s",
                tenant_id, exc, exc_info=True,
            )

        resultado = _summarize_session(
            messages, tenant_id, base_thread_id, expired_active_thread_id,
            oferta_vigente_texto, oferta_vigente_validade,
        )
        if not resultado["resumo"] and not resultado["fatos"]:
            return

        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_thread_summaries
                        (base_thread_id, resumo, fatos_estruturados, sessao_thread_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        base_thread_id,
                        resultado["resumo"],
                        json.dumps(resultado["fatos"]),
                        expired_active_thread_id,
                    ),
                )
    except Exception as exc:
        logger.error(
            "Falha ao gerar resumo de sessão para base_thread_id=%s (sessao_expirada=%s): %s",
            base_thread_id,
            expired_active_thread_id,
            exc,
            exc_info=True,
        )


def get_latest_session_summary(base_thread_id: str) -> dict | None:
    """Devolve o resumo/fatos estruturados mais recentes já gerados para este
    `base_thread_id`, ou None se nenhum existir ainda."""
    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT resumo, fatos_estruturados FROM chat_thread_summaries
                    WHERE base_thread_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (base_thread_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                resumo, fatos = row
                return {"resumo": resumo, "fatos": fatos or {}}
    except Exception as e:
        print(f"⚠️ Erro ao consultar resumo de sessão para {base_thread_id}: {e}")
        return None


def build_session_summary_context_block(summary: dict | None) -> str:
    """Formata o resumo/fatos estruturados de uma sessão anterior no mesmo estilo do
    `build_customer_context_block` (util/ai_helpers.py), para injeção no system prompt."""
    if not summary:
        return ""

    resumo = (summary.get("resumo") or "").strip()
    fatos = summary.get("fatos") or {}
    linhas = []
    if resumo:
        linhas.append(f"- Resumo do último atendimento: {resumo}")
    for campo, rotulo in (("nome", "Nome"), ("interesse", "Interesse"), ("objecao", "Objeção"), ("resultado", "Resultado anterior")):
        valor = fatos.get(campo)
        if valor:
            linhas.append(f"- {rotulo}: {valor}")

    if not linhas:
        return ""

    return (
        "\n\nPREVIOUS SESSION SUMMARY (SAME CUSTOMER, EARLIER CONVERSATION):\n"
        + "\n".join(linhas)
        + "\nUse this only as background context; confirm with the customer before relying on it "
          "for anything time-sensitive (e.g. an old booking date)."
    )

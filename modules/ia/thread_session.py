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


def _summarize_session(messages: list) -> dict:
    """Chama o LLM já configurado do projeto para gerar um resumo curto + fatos
    estruturados da sessão. Nunca inventa campo que não puder ser identificado na
    conversa (FR-011) — o próprio prompt instrui o modelo a usar null nesse caso."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from modules.ia.agent_graph import llm

    conversa_texto = "\n".join(
        f"{'Cliente' if getattr(m, 'type', None) == 'human' else 'Atendente'}: {m.content}"
        for m in messages
        if getattr(m, "type", None) in ("human", "ai") and str(getattr(m, "content", "") or "").strip()
    )
    if not conversa_texto.strip():
        return {"resumo": "", "fatos": {}}

    prompt = SystemMessage(content=(
        "Resuma a conversa de atendimento abaixo em até 3 frases curtas (~200 tokens no total). "
        "Depois, extraia em JSON os campos: nome, interesse, objecao, resultado. "
        "Use null para qualquer campo que não puder ser identificado com base real na conversa — "
        "NUNCA invente ou suponha um valor. "
        "Responda ESTRITAMENTE em JSON, no formato: "
        '{"resumo": "...", "fatos": {"nome": null, "interesse": null, "objecao": null, "resultado": null}}'
    ))
    resposta = llm.invoke([prompt, HumanMessage(content=conversa_texto)])
    dados = json.loads(resposta.content)
    return {
        "resumo": str(dados.get("resumo") or ""),
        "fatos": dados.get("fatos") or {},
    }


def generate_and_store_session_summary(base_thread_id: str, expired_active_thread_id: str) -> None:
    """Gera e persiste o resumo/fatos estruturados de uma sessão que acabou de expirar
    por inatividade. Roda em background (thread daemon disparada por
    `resolve_active_thread_id`) — qualquer falha aqui é só logada, nunca propagada
    (FR-010: não pode atrasar nem bloquear a expiração/nova sessão do cliente)."""
    try:
        messages = _get_session_messages(expired_active_thread_id)
        if not messages:
            return

        resultado = _summarize_session(messages)
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

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
import os
import uuid
from datetime import datetime, timezone

import psycopg

from infrastructure.connection import DB_URI

SESSION_IDLE_MINUTES = float(os.getenv("CHAT_SESSION_IDLE_MINUTES", "360"))


def init_thread_sessions_table():
    create_table_query = """
    CREATE TABLE IF NOT EXISTS chat_thread_sessions (
        base_thread_id VARCHAR(255) PRIMARY KEY,
        active_thread_id VARCHAR(255) NOT NULL,
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(create_table_query)
    except Exception as e:
        print(f"⚠️ Erro ao inicializar tabela chat_thread_sessions no Postgres: {e}")


def resolve_active_thread_id(base_thread_id: str, idle_minutes: float = SESSION_IDLE_MINUTES) -> str:
    """Retorna o thread_id real a ser usado pelo LangGraph para esta requisição.

    Enquanto o cliente interagir dentro da janela de `idle_minutes`, o mesmo thread_id de
    sessão é reaproveitado (mantendo contexto/nome/e-mail já informados). Se o gap desde
    a última mensagem ultrapassar `idle_minutes`, uma NOVA sessão é gerada automaticamente
    para esse `base_thread_id`, isolando o histórico e evitando datas relativas antigas.
    """
    init_thread_sessions_table()
    now = datetime.now(timezone.utc)

    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT active_thread_id, last_seen_at FROM chat_thread_sessions WHERE base_thread_id = %s;",
                    (base_thread_id,),
                )
                row = cur.fetchone()

                if row is None:
                    active_thread_id = f"{base_thread_id}#{uuid.uuid4().hex[:12]}"
                else:
                    active_thread_id, last_seen_at = row
                    elapsed_minutes = (now - last_seen_at).total_seconds() / 60
                    if elapsed_minutes >= idle_minutes:
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
        return active_thread_id
    except Exception as e:
        print(f"⚠️ Erro ao resolver sessão de thread para {base_thread_id}: {e}. Usando thread_id base.")
        return base_thread_id

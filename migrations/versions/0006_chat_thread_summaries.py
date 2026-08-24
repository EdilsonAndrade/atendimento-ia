"""chat: adiciona chat_thread_summaries (resumo + fatos estruturados por sessão expirada)

Revision ID: 0006_chat_thread_summaries
Revises: 0005_clean_global_guardrail
Create Date: 2026-08-23

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Hoje, quando uma sessão de conversa expira por inatividade (CHAT_SESSION_IDLE_MINUTES,
modules/ia/thread_session.py), o histórico bruto da sessão continua persistido pelo
PostgresSaver do LangGraph, mas nada resume o que foi conversado nem extrai fatos
estruturados (nome, interesse, objeção, resultado) para uma sessão futura do mesmo
cliente reaproveitar — o cliente "esquece" tudo ao voltar depois de CHAT_SESSION_IDLE_MINUTES
de inatividade (EDI-59).

Esta tabela guarda esse resumo/fatos, gerados em background (thread daemon, sem
bloquear a resposta do cliente) sempre que `resolve_active_thread_id` detecta a
expiração de uma sessão.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_chat_thread_summaries"
down_revision: Union[str, None] = "0005_clean_global_guardrail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.chat_thread_summaries (
            id SERIAL PRIMARY KEY,
            base_thread_id VARCHAR(255) NOT NULL,
            resumo TEXT NOT NULL DEFAULT '',
            fatos_estruturados JSONB NOT NULL DEFAULT '{}'::jsonb,
            sessao_thread_id VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_thread_summaries_base_thread_created
        ON public.chat_thread_summaries (base_thread_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.chat_thread_summaries")

"""conversation_followup: histórico consultável, resumo e outcome por sessão (EDI-53)

Revision ID: 0009_conversation_followup
Revises: 0008_tenant_message_limit
Create Date: 2026-08-26

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Hoje a conversa só é persistida via checkpoint do LangGraph (PostgresSaver) — não é
consultável/filtrável via SQL. `conversation_messages` guarda, em paralelo ao
checkpoint (sem substituí-lo), só as duas mensagens realmente visíveis de cada turno
(a fala do cliente e a última resposta do atendente), populada a partir de
`app/api/v1/endpoints/chat.py` e `modules/webhook/whatsapp.py`.

`follow_up_queue` guarda a classificação de `outcome` + rascunho de follow-up gerados
no fechamento de cada sessão (mesma chamada de LLM que já gera `resumo`/
`fatos_estruturados` em `chat_thread_summaries`, EDI-59/61 — ver
specs/011-conversation-history-followup/research.md §1). `UNIQUE (active_thread_id)`
é o que torna "exatamente 1 registro por sessão fechada" um claim atômico via
`INSERT ... ON CONFLICT DO NOTHING`, em vez de depender de lógica de aplicação para
evitar duplicata em reprocessamento.

`tenants.oferta_vigente_texto`/`oferta_vigente_validade` alimentam o guardrail que
impede o rascunho de follow-up de inventar desconto (mesma classe de guardrail do
c92de57/EDI-61). `tenants.retention_days` é o parâmetro por tenant do job de expurgo
de `conversation_messages` (fora desta migração — script em `workers/`).

NOTA: o Revision ID precisa caber em `alembic_version.version_num`, que é
VARCHAR(32) por padrão do Alembic — mantenha o slug curto (ver CLAUDE.md).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_conversation_followup"
down_revision: Union[str, None] = "0008_tenant_message_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS oferta_vigente_texto TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS oferta_vigente_validade DATE
        """
    )
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS retention_days INTEGER
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.conversation_messages (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            base_thread_id VARCHAR(255) NOT NULL,
            active_thread_id VARCHAR(255) NOT NULL,
            role VARCHAR(10) NOT NULL CHECK (role IN ('human', 'ai')),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_conversation_messages_tenant_base_thread
        ON public.conversation_messages (tenant_id, base_thread_id, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.follow_up_queue (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            base_thread_id VARCHAR(255) NOT NULL,
            active_thread_id VARCHAR(255) NOT NULL,
            outcome VARCHAR(20) NOT NULL CHECK (
                outcome IN ('fechado', 'pensando', 'sem_resposta', 'recusado', 'em_andamento')
            ),
            summary TEXT NOT NULL DEFAULT '',
            draft_message TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pendente' CHECK (
                status IN ('pendente', 'aprovado', 'enviado', 'descartado', 'opt_out')
            ),
            attempts INTEGER NOT NULL DEFAULT 0,
            approved_by VARCHAR(255),
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (active_thread_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_follow_up_queue_tenant_status
        ON public.follow_up_queue (tenant_id, status, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.follow_up_queue")
    op.execute("DROP TABLE IF EXISTS public.conversation_messages")
    op.execute("ALTER TABLE public.tenants DROP COLUMN IF EXISTS retention_days")
    op.execute("ALTER TABLE public.tenants DROP COLUMN IF EXISTS oferta_vigente_validade")
    op.execute("ALTER TABLE public.tenants DROP COLUMN IF EXISTS oferta_vigente_texto")

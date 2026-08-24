"""chat: adiciona chat_token_usage (custo de token por chamada ao LLM, por conversa/tenant/nó)

Revision ID: 0007_chat_token_usage
Revises: 0006_chat_thread_summaries
Create Date: 2026-08-23

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Não existia nenhum rastreio de consumo/custo de token por conversa ou tenant (EDI-60).
Esta tabela guarda um registro por chamada REAL ao LLM (não agregado), usando o
`usage_metadata` nativo do `ChatOpenAI` — cobrindo os 4 nós do agente que chamam o LLM
hoje (routing_agent, institutional_node, chitchat_node, operational_node, este último
podendo gerar 2 registros quando o retry de guardrail com tool_choice="required" ocorre).

`node_type` é um valor de dado (não uma coluna por nó), para permitir cobrir novos nós
do agente no futuro sem exigir alteração de schema. `created_at` viabiliza uma rotina de
purga futura (fora do escopo desta migração).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_chat_token_usage"
down_revision: Union[str, None] = "0006_chat_thread_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.chat_token_usage (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            base_thread_id VARCHAR(255) NOT NULL,
            thread_id VARCHAR(255),
            node_type VARCHAR(50) NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_token_usage_base_thread_id
        ON public.chat_token_usage (base_thread_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_token_usage_tenant_created
        ON public.chat_token_usage (tenant_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.chat_token_usage")

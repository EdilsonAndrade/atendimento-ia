"""tenant_message_limit: adiciona limite mensal de mensagens por tenant (EDI-63)

Revision ID: 0008_tenant_message_limit
Revises: 0007_chat_token_usage
Create Date: 2026-08-25

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Não existia nenhum controle de volume de uso por tenant (EDI-63) — o custo de IA é
100% absorvido pela InterasisAI e um único tenant podia estourar a margem calculada
na precificação sem nenhum enforcement.

`tenants.monthly_message_limit` (NULL = sem limite, comportamento atual preservado)
e `tenants.notification_emails` (e-mails do próprio tenant para os avisos de
50/80/100%/reset) são colunas novas, não uma tabela separada, porque são atributos
1:1 do tenant.

`global_notification_recipients` é global por design (e-mails internos da
InterasisAI que recebem TODOS os alertas de bloqueio de qualquer tenant) — sem FK
para `tenants`.

`tenant_usage_notifications` existe só para o `UNIQUE (tenant_id, year_month,
milestone)` — é o que torna o "enviar um alerta de marco no máximo uma vez por mês"
um claim atômico via `INSERT ... ON CONFLICT DO NOTHING`, em vez de uma condição de
corrida entre requisições concorrentes do mesmo tenant. Ver
specs/010-tenant-message-limit/research.md §3.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_tenant_message_limit"
down_revision: Union[str, None] = "0007_chat_token_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS monthly_message_limit INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS notification_emails TEXT[]
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.global_notification_recipients (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_usage_notifications (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(50) NOT NULL,
            year_month CHAR(7) NOT NULL,
            milestone SMALLINT NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, year_month, milestone)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.tenant_usage_notifications")
    op.execute("DROP TABLE IF EXISTS public.global_notification_recipients")
    op.execute("ALTER TABLE public.tenants DROP COLUMN IF EXISTS notification_emails")
    op.execute("ALTER TABLE public.tenants DROP COLUMN IF EXISTS monthly_message_limit")

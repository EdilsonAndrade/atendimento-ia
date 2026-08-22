"""tenants: adiciona scheduling_enabled (capacidade de agendamento por tenant)

Revision ID: 0003_add_scheduling_enabled_to_tenants
Revises: 0002_backfill_tenant_links
Create Date: 2026-08-22

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
`get_active_tools` (modules/ia/agent_graph.py) decidia se o tenant recebia tools
de agendamento (agendar, consultar, cancelar) unicamente pela presença de
`google_calendar_id`: sem calendário configurado, o tenant caía em
`static_tools` — ou seja, TODO tenant recebia tools de agendamento por padrão,
mesmo um tenant puramente institucional (ex: a própria SimplificandoAI, que usa
o chat só para vender o produto, não para marcar hora). É o mesmo fail-open que
o EDI-43 eliminou na resolução de prompt, agora em tools.

Esta coluna torna a capacidade explícita: sem `scheduling_enabled = TRUE`,
nenhuma tool de agendamento é oferecida ao modelo, independente de
`google_calendar_id`.

BACKFILL
--------
DEFAULT TRUE preenche automaticamente as linhas existentes (decisão do
solicitante: a base é pequena — 2 clientes hoje — e ele mesmo desliga a flag
dos tenants que não devem ter agendamento, como o simplificandoai, depois do
deploy). Novo tenant também nasce com TRUE por padrão no cadastro, editável.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_scheduling_enabled"
down_revision: Union[str, None] = "0003_tenant_prompts_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.tenants
        ADD COLUMN IF NOT EXISTS scheduling_enabled boolean DEFAULT true NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE public.tenants DROP COLUMN IF EXISTS scheduling_enabled"
    )

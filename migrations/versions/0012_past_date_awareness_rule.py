"""system_prompts: adiciona a chave past_date_awareness_rule

Revision ID: 0012_past_date_awareness_rule
Revises: 0011_tenant_kb_items
Create Date: 2026-09-06

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Bug real de produção: o institutional_node aceitava datas já passadas em
pedidos de orçamento/cotação (ex.: usuário pede cotação "para março de 2026"
com o sistema já em setembro/2026) porque esse nó nunca recebia a data de
hoje nem tinha uma regra explícita de validação de data passada.

Em vez de hardcodar esse texto dentro de `prompts/load_prompt.py` (que
misturaria uma regra de sistema, cross-cutting, dentro do módulo de prompts
POR TENANT), esta migração segue o mesmo padrão já estabelecido pela
`0010_system_prompts` para `routing_agent`/`GROUNDEDNESS_RULE`/etc.: uma 5ª
linha em `system_prompts`, editável pelo Painel Administrador, carregada via
`prompts/system_prompt_loader.carregar_past_date_awareness_rule(data_hoje_iso)`.

NOTA: o Revision ID precisa caber em `alembic_version.version_num`
(VARCHAR(32)) — ver CLAUDE.md.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012_past_date_awareness_rule"
down_revision: Union[str, None] = "0011_tenant_kb_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PAST_DATE_AWARENESS_RULE = (
    "PAST DATE AWARENESS RULE (CRITICAL): Today's date is {data_hoje_iso} (YYYY-MM-DD). "
    "If the user mentions any date, month, or year for an event that has already fully "
    "passed relative to today — including a bare month+year with no day (e.g. a past "
    "month of the current year, or any year before the current one) — do NOT treat it "
    "as valid or proceed enthusiastically with a quote/availability check. Inform the "
    "user that date has already passed and ask for a future date before continuing.\n"
)

PROMPT_KEY = "past_date_awareness_rule"
TITULO = "PAST_DATE_AWARENESS_RULE (regra de data já passada, institutional_node)"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        INSERT INTO public.system_prompts (prompt_key, titulo, current_version, last_version)
        VALUES (%(prompt_key)s, %(titulo)s, %(conteudo)s, %(conteudo)s)
        ON CONFLICT (prompt_key) DO NOTHING
        """,
        {"prompt_key": PROMPT_KEY, "titulo": TITULO, "conteudo": PAST_DATE_AWARENESS_RULE},
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM public.system_prompts WHERE prompt_key = '{PROMPT_KEY}'")

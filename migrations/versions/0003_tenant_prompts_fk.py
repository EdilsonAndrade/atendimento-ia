"""fk: tenant_prompts.tenant_id referencia tenants.id (EDI-45)

Revision ID: 0003_tenant_prompts_fk
Revises: 0002_backfill_tenant_links
Create Date: 2026-08-22

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
A baseline (`0001_baseline`) documenta duas inconsistências reproduzidas de
propósito: `tenant_prompts.tenant_id` é `varchar(100)` enquanto `tenants.id` é
`varchar(50)`, e não existe nenhuma FK entre as duas — a referência é só por
convenção. Isso permitia excluir um tenant e deixar suas linhas de
`tenant_prompts` órfãs, silenciosamente (EDI-45).

Esta migração corrige as duas coisas de uma vez: reduz o tipo da coluna para
`varchar(50)` (compatível com `tenants.id`) e adiciona
`FOREIGN KEY ... ON DELETE CASCADE`, para que excluir um tenant sempre limpe
seus vínculos de prompt automaticamente, sem depender de nenhum código de
aplicação lembrar de fazer isso.

LIMPEZA NECESSÁRIA ANTES DA FK
------------------------------
Um banco que já rodou sem a FK pode ter linhas órfãs (tenant_id que não existe
mais em `tenants`) — restos exatamente do defeito que este ticket corrige.
Adicionar a FK sem limpar essas linhas faria a migração falhar. Por isso o
upgrade apaga essas linhas órfãs antes de alterar o tipo/adicionar a
constraint, e registra quantas removeu.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_tenant_prompts_fk"
down_revision: Union[str, None] = "0002_backfill_tenant_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    orfaos = conn.exec_driver_sql(
        """
        DELETE FROM tenant_prompts
        WHERE tenant_id NOT IN (SELECT id FROM tenants)
        """
    )
    if orfaos.rowcount:
        print(f"[EDI-45] {orfaos.rowcount} vínculo(s) órfão(s) de tenant_prompts removido(s) antes da FK.")

    conn.exec_driver_sql(
        "ALTER TABLE tenant_prompts ALTER COLUMN tenant_id TYPE VARCHAR(50)"
    )
    conn.exec_driver_sql(
        """
        ALTER TABLE tenant_prompts
        ADD CONSTRAINT fk_tenant_prompts_tenant_id
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        "ALTER TABLE tenant_prompts DROP CONSTRAINT fk_tenant_prompts_tenant_id"
    )
    conn.exec_driver_sql(
        "ALTER TABLE tenant_prompts ALTER COLUMN tenant_id TYPE VARCHAR(100)"
    )

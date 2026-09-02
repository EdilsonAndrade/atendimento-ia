"""tenant_kb_items: itens individuais na base de conhecimento (EDI-39)

Revision ID: 0011_tenant_kb_items
Revises: 0010_system_prompts
Create Date: 2026-09-01

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
Até aqui, `tenant_knowledge_base` guardava um único bloco de texto por
tenant (`content`), sem rastrear arquivos individuais. O EDI-39 exige upload
de N arquivos (PDF/XLS/CSV) e textos, cada um editável/excluível/substituível
de forma independente numa grid — o que exige uma linha por item, não um
blob único.

Esta migração cria `tenant_knowledge_base_items` e faz backfill: cada linha
hoje existente em `tenant_knowledge_base` vira 1 item (`source_type='texto'`,
`filename=NULL`). Como `PostgresKnowledgeBaseRepository` passa a operar
inteiramente sobre a tabela nova (ver módulo `modules/knowledge_base`), a
tabela antiga fica sem nenhum código que a use e é removida aqui, para não
deixar schema morto.

NOTA: o Revision ID precisa caber em `alembic_version.version_num`
(VARCHAR(32)) — ver CLAUDE.md.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0011_tenant_kb_items"
down_revision: Union[str, None] = "0010_system_prompts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_knowledge_base_items (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
            tenant_id text NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            source_type text NOT NULL CHECK (source_type IN ('file', 'texto')),
            filename text NULL,
            content text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_kb_items_tenant_id
            ON public.tenant_knowledge_base_items (tenant_id)
        """
    )

    # Backfill: 1 item de texto por tenant que já tinha base de conhecimento.
    # A tabela antiga nunca teve FK para `tenants` — linhas órfãs (tenant_id sem
    # cadastro correspondente) já podiam existir e são ignoradas aqui, já que a
    # nova tabela exige a FK (Constituição, Princípio I: isolamento por tenant real).
    result = conn.exec_driver_sql(
        """
        INSERT INTO public.tenant_knowledge_base_items
            (tenant_id, source_type, filename, content, created_at, updated_at)
        SELECT tkb.tenant_id, 'texto', NULL, tkb.content, tkb.updated_at, tkb.updated_at
        FROM public.tenant_knowledge_base tkb
        WHERE EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = tkb.tenant_id)
        """
    )
    skipped = conn.exec_driver_sql(
        """
        SELECT count(*) FROM public.tenant_knowledge_base tkb
        WHERE NOT EXISTS (SELECT 1 FROM public.tenants t WHERE t.id = tkb.tenant_id)
        """
    ).scalar()
    if skipped:
        print(
            f"[0011_tenant_kb_items] Aviso: {skipped} linha(s) de tenant_knowledge_base "
            "com tenant_id órfão (sem tenant correspondente) foram descartadas no backfill."
        )

    conn.exec_driver_sql("DROP TABLE IF EXISTS public.tenant_knowledge_base")


def downgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_knowledge_base (
            tenant_id text NOT NULL PRIMARY KEY,
            content text NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL
        )
        """
    )

    # Backfill inverso: 1 linha por tenant, concatenando os itens em ordem de criação.
    conn.exec_driver_sql(
        """
        INSERT INTO public.tenant_knowledge_base (tenant_id, content, updated_at)
        SELECT tenant_id,
               string_agg(content, E'\\n\\n' ORDER BY created_at),
               max(updated_at)
        FROM public.tenant_knowledge_base_items
        GROUP BY tenant_id
        ON CONFLICT (tenant_id) DO UPDATE
            SET content = EXCLUDED.content, updated_at = EXCLUDED.updated_at
        """
    )

    conn.exec_driver_sql("DROP TABLE IF EXISTS public.tenant_knowledge_base_items")

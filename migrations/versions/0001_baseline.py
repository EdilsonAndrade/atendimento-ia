"""baseline: espelho fiel do schema de producao (EDI-37)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-21

Esta migração é a fotografia da estrutura que JÁ existe em produção, gerada a partir
do `pg_dump --schema-only` de 2026-08-21 (PostgreSQL 17.5).

COMO ELA É APLICADA
-------------------
- **Banco vazio** (desenvolvedor novo, outra cloud, teste): roda de verdade e cria tudo.
- **Produção**: NUNCA é executada. É apenas registrada com `alembic stamp 0001_baseline`,
  que grava a linha em `alembic_version` sem tocar em nenhum objeto ou dado.

CONSEQUÊNCIA IMPORTANTE
-----------------------
Como em produção ela é apenas registrada, **qualquer objeto descrito aqui que não exista
de fato lá jamais será criado**. Por isso esta migração não corrige nada — ela reproduz
até as inconsistências reais do banco (ver notas abaixo). Correções de schema vão em
migrações 0002+, que rodam de verdade em todos os ambientes.

INCONSISTÊNCIAS REPRODUZIDAS DE PROPÓSITO (cada uma virou ticket próprio)
------------------------------------------------------------------------
- `agendamentos.created_at` / `deleted_at` são `timestamp` SEM fuso, enquanto todas as
  outras tabelas usam `timestamptz`. Trocar mudaria a semântica dos registros existentes.
- `whatsapp_instances.id` usa `gen_random_uuid()`; as demais usam `uuid_generate_v4()`.
- `tenant_prompts.tenant_id` é `varchar(100)` enquanto `tenants.id` é `varchar(50)`.
- Não existem FKs de `tenant_id` — `agendamentos`, `tenant_prompts` e `whatsapp_instances`
  referenciam `tenants` apenas por convenção.
- `tenants` não tem gatilho de `updated_at` (as outras três tabelas têm), então o campo
  nunca é atualizado.

O DDL é escrito como SQL literal via `op.execute()` em vez da API declarativa do Alembic
porque o critério aqui é fidelidade byte a byte: gatilhos, índice único parcial, array com
default literal e a mistura deliberada de tipos de timestamp são exatamente o tipo de
construção em que uma camada de tradução introduz divergência silenciosa.
"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Trava do downgrade: reverter a baseline apaga as 9 tabelas COM TODOS OS DADOS.
# Só é liberado com um ato deliberado, para uso em banco descartável.
_DOWNGRADE_GUARD_ENV = "ALEMBIC_ALLOW_BASELINE_DOWNGRADE"


def upgrade() -> None:
    # --- extensões ------------------------------------------------------------
    # uuid-ossp é obrigatória: os DEFAULT uuid_generate_v4() dependem dela e nenhuma
    # biblioteca do projeto a cria. (A extensão `vector` fica de fora: quem a cria é
    # o langchain-postgres, dono das tabelas langchain_pg_*.)
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public')

    # --- função de apoio ------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.update_timestamp_column() RETURNS trigger
            LANGUAGE plpgsql
            AS $$
        BEGIN
           NEW.updated_at = NOW();
           RETURN NEW;
        END;
        $$;
        """
    )

    # --- tabelas --------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tenants (
            id character varying(50) NOT NULL,
            name character varying(255) NOT NULL,
            google_calendar_id character varying(255),
            active boolean DEFAULT true,
            created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            allowed_domains text[] DEFAULT '{}'::text[]
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.prompts (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            titulo character varying(150) NOT NULL,
            conteudo text NOT NULL,
            is_default boolean DEFAULT false,
            created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            node_type text DEFAULT 'operational'::text NOT NULL,
            CONSTRAINT prompts_node_type_check CHECK ((node_type = ANY (ARRAY['operational'::text, 'institutional'::text, 'chitchat'::text])))
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.guardrails (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            titulo character varying(150) NOT NULL,
            conteudo text NOT NULL,
            is_global boolean DEFAULT false,
            created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.prompt_guardrails (
            prompt_id uuid NOT NULL,
            guardrail_id uuid NOT NULL,
            created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_prompts (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id character varying(100) NOT NULL,
            prompt_id uuid NOT NULL,
            is_active boolean DEFAULT true,
            custom_content_override text,
            created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.whatsapp_instances (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            tenant_id character varying(50) NOT NULL,
            instance_name character varying(100) NOT NULL,
            phone_number character varying(20),
            active boolean DEFAULT true,
            created_at timestamp with time zone DEFAULT now(),
            updated_at timestamp with time zone DEFAULT now()
        )
        """
    )

    # ATENÇÃO: created_at/deleted_at SEM fuso horário — divergência real de produção.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.agendamentos (
            id integer NOT NULL,
            tenant_id character varying(50) NOT NULL,
            cliente_nome character varying(100) NOT NULL,
            cliente_email character varying(100),
            servico character varying(100) NOT NULL,
            profissional character varying(100) NOT NULL,
            email_profissional character varying(100),
            data_agendamento date NOT NULL,
            horario time without time zone NOT NULL,
            status character varying(20) DEFAULT 'CONFIRMADO'::character varying,
            google_event_id character varying(255),
            created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
            deleted_at timestamp without time zone
        )
        """
    )

    op.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS public.agendamentos_id_seq
            AS integer
            START WITH 1
            INCREMENT BY 1
            NO MINVALUE
            NO MAXVALUE
            CACHE 1
        """
    )
    op.execute(
        "ALTER SEQUENCE public.agendamentos_id_seq OWNED BY public.agendamentos.id"
    )
    op.execute(
        "ALTER TABLE ONLY public.agendamentos "
        "ALTER COLUMN id SET DEFAULT nextval('public.agendamentos_id_seq'::regclass)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.chat_thread_sessions (
            base_thread_id character varying(255) NOT NULL,
            active_thread_id character varying(255) NOT NULL,
            last_seen_at timestamp with time zone DEFAULT now() NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_knowledge_base (
            tenant_id text NOT NULL,
            content text NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL
        )
        """
    )

    # --- chaves primárias, restrições e FKs (idempotente via information_schema) --------
    op.execute("""
    DO $$
    BEGIN
        -- Chaves primárias (verifica na information_schema antes de adicionar)
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='tenants' AND constraint_name='tenants_pkey') THEN
            ALTER TABLE ONLY public.tenants ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='prompts' AND constraint_name='prompts_pkey') THEN
            ALTER TABLE ONLY public.prompts ADD CONSTRAINT prompts_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='guardrails' AND constraint_name='guardrails_pkey') THEN
            ALTER TABLE ONLY public.guardrails ADD CONSTRAINT guardrails_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='prompt_guardrails' AND constraint_name='prompt_guardrails_pkey') THEN
            ALTER TABLE ONLY public.prompt_guardrails ADD CONSTRAINT prompt_guardrails_pkey PRIMARY KEY (prompt_id, guardrail_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='tenant_prompts' AND constraint_name='tenant_prompts_pkey') THEN
            ALTER TABLE ONLY public.tenant_prompts ADD CONSTRAINT tenant_prompts_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='whatsapp_instances' AND constraint_name='whatsapp_instances_pkey') THEN
            ALTER TABLE ONLY public.whatsapp_instances ADD CONSTRAINT whatsapp_instances_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='agendamentos' AND constraint_name='agendamentos_pkey') THEN
            ALTER TABLE ONLY public.agendamentos ADD CONSTRAINT agendamentos_pkey PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='chat_thread_sessions' AND constraint_name='chat_thread_sessions_pkey') THEN
            ALTER TABLE ONLY public.chat_thread_sessions ADD CONSTRAINT chat_thread_sessions_pkey PRIMARY KEY (base_thread_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='tenant_knowledge_base' AND constraint_name='tenant_knowledge_base_pkey') THEN
            ALTER TABLE ONLY public.tenant_knowledge_base ADD CONSTRAINT tenant_knowledge_base_pkey PRIMARY KEY (tenant_id);
        END IF;

        -- Restrições de unicidade
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='tenant_prompts' AND constraint_name='unique_active_tenant_prompt') THEN
            ALTER TABLE ONLY public.tenant_prompts ADD CONSTRAINT unique_active_tenant_prompt UNIQUE (tenant_id, prompt_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='whatsapp_instances' AND constraint_name='whatsapp_instances_instance_name_key') THEN
            ALTER TABLE ONLY public.whatsapp_instances ADD CONSTRAINT whatsapp_instances_instance_name_key UNIQUE (instance_name);
        END IF;

        -- Chaves estrangeiras
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='prompt_guardrails' AND constraint_name='prompt_guardrails_prompt_id_fkey') THEN
            ALTER TABLE ONLY public.prompt_guardrails ADD CONSTRAINT prompt_guardrails_prompt_id_fkey FOREIGN KEY (prompt_id) REFERENCES public.prompts(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='prompt_guardrails' AND constraint_name='prompt_guardrails_guardrail_id_fkey') THEN
            ALTER TABLE ONLY public.prompt_guardrails ADD CONSTRAINT prompt_guardrails_guardrail_id_fkey FOREIGN KEY (guardrail_id) REFERENCES public.guardrails(id) ON DELETE CASCADE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name='tenant_prompts' AND constraint_name='tenant_prompts_prompt_id_fkey') THEN
            ALTER TABLE ONLY public.tenant_prompts ADD CONSTRAINT tenant_prompts_prompt_id_fkey FOREIGN KEY (prompt_id) REFERENCES public.prompts(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """)

    # --- índices --------------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_guardrails_is_global ON public.guardrails USING btree (is_global)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompts_is_default ON public.prompts USING btree (is_default)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_prompts_lookup "
        "ON public.tenant_prompts USING btree (tenant_id, is_active)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_whatsapp_instances_name "
        "ON public.whatsapp_instances USING btree (instance_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_whatsapp_instances_tenant "
        "ON public.whatsapp_instances USING btree (tenant_id)"
    )
    # Garante no máximo UM prompt padrão por node_type (EDI-42).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS prompts_one_default_per_node "
        "ON public.prompts USING btree (node_type) WHERE (is_default = true)"
    )

    # --- gatilhos de updated_at ----------------------------------------------
    # tenants NÃO tem gatilho equivalente em produção — reproduzido como está.
    op.execute("DROP TRIGGER IF EXISTS update_prompts_modtime ON public.prompts")
    op.execute(
        "CREATE TRIGGER update_prompts_modtime BEFORE UPDATE ON public.prompts "
        "FOR EACH ROW EXECUTE FUNCTION public.update_timestamp_column()"
    )
    op.execute("DROP TRIGGER IF EXISTS update_guardrails_modtime ON public.guardrails")
    op.execute(
        "CREATE TRIGGER update_guardrails_modtime BEFORE UPDATE ON public.guardrails "
        "FOR EACH ROW EXECUTE FUNCTION public.update_timestamp_column()"
    )
    op.execute("DROP TRIGGER IF EXISTS update_tenant_prompts_modtime ON public.tenant_prompts")
    op.execute(
        "CREATE TRIGGER update_tenant_prompts_modtime BEFORE UPDATE ON public.tenant_prompts "
        "FOR EACH ROW EXECUTE FUNCTION public.update_timestamp_column()"
    )



def downgrade() -> None:
    """Reverte a baseline — DESTRUTIVO, travado por padrão.

    Reverter esta migração significa apagar as 9 tabelas do projeto com todos os
    dados de clientes. Em produção isso seria uma perda total, e o EDI-37 é explícito:
    as tabelas foram criadas à mão e não podem ser apagadas.

    Para usar em banco descartável:
        ALEMBIC_ALLOW_BASELINE_DOWNGRADE=1 alembic downgrade base
    """
    if os.getenv(_DOWNGRADE_GUARD_ENV) != "1":
        raise RuntimeError(
            "Downgrade da baseline BLOQUEADO: ele apaga as 9 tabelas do projeto com "
            "todos os dados. Se este banco é descartável e você tem certeza, rode de "
            f"novo com {_DOWNGRADE_GUARD_ENV}=1."
        )

    # Ordem inversa: FKs caem junto com as tabelas via CASCADE.
    for tabela in (
        "tenant_knowledge_base",
        "chat_thread_sessions",
        "agendamentos",
        "whatsapp_instances",
        "tenant_prompts",
        "prompt_guardrails",
        "guardrails",
        "prompts",
        "tenants",
    ):
        op.execute(f"DROP TABLE IF EXISTS public.{tabela} CASCADE")

    op.execute("DROP SEQUENCE IF EXISTS public.agendamentos_id_seq CASCADE")
    op.execute("DROP FUNCTION IF EXISTS public.update_timestamp_column() CASCADE")
    # A extensão uuid-ossp NÃO é removida: outros objetos do banco podem depender dela.

# Phase 1 — Data Model: baseline do schema (EDI-37)

**Feature**: `specs/004-alembic-migrations/`
**Fonte**: dump de estrutura do banco de **produção** (PostgreSQL 15.18, Debian), coletado em 2026-08-21 do contêiner do banco.
**Verificado**: a baseline aplicada num `postgres:15` limpo produz exatamente esta estrutura — diferença zero contra o dump de produção (exceto a extensão `vector`, excluída de propósito).
**Regra mestra**: a `0001` é um **espelho fiel** de produção. Nada é acrescentado, removido ou corrigido em relação ao dump (FR-003).

---

## 1. Entidade de controle do próprio versionamento

### `alembic_version`

Criada e mantida pelo Alembic, não pela `0001`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `version_num` | `varchar(32)` PK | Identificador da migração atualmente aplicada |

- Em **banco vazio**: criada durante `alembic upgrade head`, passando a conter `0001_baseline`.
- Em **produção**: criada por `alembic stamp 0001_baseline`, que grava a linha **sem executar nenhum DDL** (FR-005).

---

## 2. Objetos de apoio (dentro do controle)

### Extensão `uuid-ossp`

`CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` — obrigatória: os defaults `uuid_generate_v4()` de `prompts`, `guardrails` e `tenant_prompts` dependem dela. Nenhuma biblioteca do projeto a cria.

### Função `update_timestamp_column()`

Gatilho `BEFORE UPDATE` que define `NEW.updated_at = NOW()`.

```sql
CREATE OR REPLACE FUNCTION public.update_timestamp_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$;
```

### Gatilhos

| Gatilho | Tabela |
|---|---|
| `update_prompts_modtime` | `prompts` |
| `update_guardrails_modtime` | `guardrails` |
| `update_tenant_prompts_modtime` | `tenant_prompts` |

> `tenants` **não** tem gatilho equivalente em produção — logo `tenants.updated_at` nunca é atualizado. Reproduzido como está; a correção é *Out of Scope* (ticket próprio).

---

## 3. Tabelas do projeto (9, dentro do controle)

Ordem de criação respeitando dependências: `tenants` → `prompts`, `guardrails` → `prompt_guardrails`, `tenant_prompts` → demais.

### `tenants` — clientes da plataforma

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `varchar(50)` | **PK** |
| `name` | `varchar(255)` | NOT NULL |
| `google_calendar_id` | `varchar(255)` | |
| `active` | `boolean` | DEFAULT `true` |
| `created_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `allowed_domains` | `text[]` | DEFAULT `'{}'::text[]` |

*Sem gatilho de `updated_at`. `active` existe mas não é lida pelo código (Out of Scope).*

### `prompts` — prompts da IA por tipo de nó

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `uuid` | **PK**, DEFAULT `uuid_generate_v4()` |
| `titulo` | `varchar(150)` | NOT NULL |
| `conteudo` | `text` | NOT NULL |
| `is_default` | `boolean` | DEFAULT `false` |
| `created_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `node_type` | `text` | NOT NULL, DEFAULT `'operational'` |

- **CHECK** `prompts_node_type_check`: `node_type IN ('operational','institutional','chitchat')`
- **INDEX** `idx_prompts_is_default` em `(is_default)`
- **UNIQUE INDEX parcial** `prompts_one_default_per_node` em `(node_type) WHERE is_default = true` — garante no máximo um prompt padrão por tipo de nó
- **TRIGGER** `update_prompts_modtime`

### `guardrails` — regras de segurança da IA

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `uuid` | **PK**, DEFAULT `uuid_generate_v4()` |
| `titulo` | `varchar(150)` | NOT NULL |
| `conteudo` | `text` | NOT NULL |
| `is_global` | `boolean` | DEFAULT `false` |
| `created_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |

- **INDEX** `idx_guardrails_is_global` em `(is_global)`
- **TRIGGER** `update_guardrails_modtime`

### `prompt_guardrails` — associação N:N prompt ↔ guardrail

| Coluna | Tipo | Restrições |
|---|---|---|
| `prompt_id` | `uuid` | **PK (composta)**, FK → `prompts(id)` ON DELETE CASCADE |
| `guardrail_id` | `uuid` | **PK (composta)**, FK → `guardrails(id)` ON DELETE CASCADE |
| `created_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |

### `tenant_prompts` — vínculo tenant ↔ prompt

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `uuid` | **PK**, DEFAULT `uuid_generate_v4()` |
| `tenant_id` | `varchar(100)` | NOT NULL — *sem FK para `tenants`* |
| `prompt_id` | `uuid` | NOT NULL, FK → `prompts(id)` ON DELETE CASCADE |
| `is_active` | `boolean` | DEFAULT `true` |
| `custom_content_override` | `text` | |
| `created_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | DEFAULT `CURRENT_TIMESTAMP` |

- **UNIQUE** `unique_active_tenant_prompt` em `(tenant_id, prompt_id)`
- **INDEX** `idx_tenant_prompts_lookup` em `(tenant_id, is_active)`
- **TRIGGER** `update_tenant_prompts_modtime`
- Nota: `tenant_id` é `varchar(100)` aqui e `varchar(50)` em `tenants.id` — divergência real de produção, reproduzida como está.

### `whatsapp_instances` — canais de WhatsApp por tenant

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `uuid` | **PK**, DEFAULT `gen_random_uuid()` |
| `tenant_id` | `varchar(50)` | NOT NULL — *sem FK* |
| `instance_name` | `varchar(100)` | NOT NULL, **UNIQUE** (`whatsapp_instances_instance_name_key`) |
| `phone_number` | `varchar(20)` | |
| `active` | `boolean` | DEFAULT `true` |
| `created_at` | `timestamptz` | DEFAULT `now()` |
| `updated_at` | `timestamptz` | DEFAULT `now()` |

- **INDEX** `idx_whatsapp_instances_name` em `(instance_name)`, **INDEX** `idx_whatsapp_instances_tenant` em `(tenant_id)`
- Nota: usa `gen_random_uuid()` enquanto as demais usam `uuid_generate_v4()` — reproduzido como está (Out of Scope).

### `agendamentos` — compromissos marcados

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `integer` | **PK**, `nextval('agendamentos_id_seq')` |
| `tenant_id` | `varchar(50)` | NOT NULL — *sem FK* |
| `cliente_nome` | `varchar(100)` | NOT NULL |
| `cliente_email` | `varchar(100)` | |
| `servico` | `varchar(100)` | NOT NULL |
| `profissional` | `varchar(100)` | NOT NULL |
| `email_profissional` | `varchar(100)` | |
| `data_agendamento` | `date` | NOT NULL |
| `horario` | `time without time zone` | NOT NULL |
| `status` | `varchar(20)` | DEFAULT `'CONFIRMADO'` |
| `google_event_id` | `varchar(255)` | |
| `created_at` | **`timestamp without time zone`** | DEFAULT `CURRENT_TIMESTAMP` |
| `deleted_at` | **`timestamp without time zone`** | |

- Sequência `agendamentos_id_seq` (`AS integer`, `START WITH 1`, `INCREMENT BY 1`, `CACHE 1`), `OWNED BY agendamentos.id`
- **Atenção**: única tabela com timestamps **sem** fuso horário. Preservar exatamente — trocar por `timestamptz` mudaria a semântica dos registros existentes.

### `chat_thread_sessions` — expiração de conversa por inatividade

| Coluna | Tipo | Restrições |
|---|---|---|
| `base_thread_id` | `varchar(255)` | **PK** |
| `active_thread_id` | `varchar(255)` | NOT NULL |
| `last_seen_at` | `timestamptz` | NOT NULL, DEFAULT `now()` |

### `tenant_knowledge_base` — base de conhecimento textual por tenant

| Coluna | Tipo | Restrições |
|---|---|---|
| `tenant_id` | `text` | **PK** |
| `content` | `text` | NOT NULL |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` |

---

## 4. Fora do controle do Alembic

Excluídas via `include_object` no `env.py` (FR-011, FR-012). Criadas e evoluídas pelas próprias bibliotecas.

| Objeto | Dona |
|---|---|
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | `langgraph-checkpoint-postgres` |
| `langchain_pg_collection`, `langchain_pg_embedding` (+ índice `ix_cmetadata_gin`, FK própria) | `langchain-postgres` |
| extensão `vector` | `langchain-postgres` |

---

## 5. Correspondência com o DDL hoje em runtime

Conferido em 2026-08-21 — as 3 tabelas criadas pela aplicação coincidem **100%** com produção, o que torna o `stamp` seguro:

| Tabela | Origem do DDL hoje | Confere com produção |
|---|---|---|
| `agendamentos` | `modules/agendamento/booking_tools.py::init_booking_table()` | ✅ |
| `chat_thread_sessions` | `modules/ia/thread_session.py::init_thread_sessions_table()` | ✅ |
| `tenant_knowledge_base` | `modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py::_ensure_table()` | ✅ |
| `prompts.node_type` + CHECK + índice parcial | `modules/prompt_manager/prompt_manager_repository.py::ensure_node_type_schema()` | ✅ |

Todas essas rotinas são removidas por FR-013 depois que a baseline entra em vigor.

---

## 6. Consequência da estratégia de `stamp`

Como em produção a `0001` é apenas **registrada** e nunca executada, **qualquer objeto descrito na baseline que não exista de fato em produção jamais será criado lá**. É por isso que FR-003 exige fidelidade absoluta: a baseline não é lugar para corrigir nada. Correções de estrutura (as listadas em *Out of Scope*) precisam vir em migrações `0002+`, que rodam de verdade em todos os ambientes.

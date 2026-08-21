---

description: "Task list — Migrations versionadas do schema PostgreSQL (EDI-37)"
---

# Tasks: Migrations versionadas do schema PostgreSQL (EDI-37)

**Input**: Design documents de `/specs/004-alembic-migrations/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/migration-cli.md](./contracts/migration-cli.md), [quickstart.md](./quickstart.md)

**Tests**: incluídos — a estratégia de teste em dois níveis está definida em [research.md R9](./research.md) e é exigida pelo Princípio VI da constituição.

**Organization**: tarefas agrupadas por história de usuário, para permitir implementação e validação independentes.

## Format: `[ID] [P?] [Story] Descrição`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: história a que a tarefa pertence (US1, US2, US3, US4)
- Todo caminho de arquivo é explícito

## Path Conventions

Estrutura atual do repositório (API FastAPI backend-only): `app/`, `modules/`, `infrastructure/`, `tests/` na raiz. Artefatos novos desta feature: `alembic.ini`, `docker-entrypoint.sh` e o pacote `migrations/`, todos na raiz.

---

## ⚠️ Ordem obrigatória entre fases

A **Fase 6 (US4)** só pode ser mesclada depois de a **Fase 4 (US2)** estar aplicada no banco de produção. Se o DDL em runtime sumir do código enquanto produção ainda não estiver sob controle das migrations, um banco novo levantado nesse intervalo ficaria sem tabelas.

## ✅ Estado atual: PRODUÇÃO MARCADA — deploy liberado

**2026-08-21**: T017 (conferência) e T018 (`stamp`) concluídas no banco `interasisai`. `alembic_version = 0001_baseline`. A trava que impedia o deploy foi removida.

O motivo dela, para registro: com o `ENTRYPOINT` novo, o primeiro deploy roda `alembic upgrade head`. Num banco de produção não marcado, isso tentaria criar tabelas já existentes → `relation "tenants" already exists` → o contêiner morreria e a API não subiria. Com o `stamp` aplicado, o `upgrade` encontra o banco em dia e não executa nada.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: colocar a dependência e a configuração do Alembic no lugar

- [X] T001 Adicionar `alembic>=1.13` na seção "Banco de Dados & Async" de `requirements.txt`, logo abaixo de `psycopg-pool`, com comentário explicando que o SQLAlchemy já presente é usado apenas pelo Alembic (as consultas seguem em psycopg)
- [X] T002 Instalar a dependência no ambiente local — comando para o usuário rodar: `pip install "alembic>=1.13"`
- [X] T003 [P] Criar `alembic.ini` na raiz do repositório com: `script_location = migrations`, `sqlalchemy.url =` **vazio** (nenhuma credencial versionada — ver [research.md R8](./research.md)), `file_template = %%(rev)s_%%(slug)s` para revisões sequenciais legíveis ([research.md R10](./research.md)), e seção de logging padrão

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: o `env.py` é pré-requisito de qualquer migração — nenhuma história avança sem ele

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar

- [X] T004 [P] Criar `migrations/script.py.mako` (template padrão do Alembic para novas revisões, com `revision`, `down_revision`, `upgrade()` e `downgrade()`)
- [X] T005 Criar `migrations/env.py` implementando:
  - função `_build_database_url()` que lê `POSTGRES_DATABASE_URI` via `load_dotenv()`, levanta erro explícito se ausente (**sem** fallback com credencial, ao contrário de `infrastructure/connection.py:7`) e normaliza o esquema `postgresql://` / `postgres://` para **`postgresql+psycopg://`** — ver [research.md R2](./research.md), sem isso o deploy quebra em produção
  - `target_metadata = None` e `include_object()` excluindo `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `langchain_pg_collection`, `langchain_pg_embedding` ([research.md R4](./research.md))
  - `run_migrations_online()` executando `SELECT pg_advisory_xact_lock(<chave fixa>)` antes de `context.run_migrations()` ([research.md R6](./research.md))
  - `run_migrations_offline()` no padrão do Alembic
- [X] T006 [P] Criar `migrations/versions/.gitkeep` para versionar o diretório vazio

**Checkpoint**: base pronta — as histórias podem começar

---

## Phase 3: User Story 1 - Recriar o banco inteiro a partir do repositório (Priority: P1) 🎯 MVP

**Goal**: um banco PostgreSQL vazio vira um ambiente funcional com um único comando, com estrutura idêntica à de produção.

**Independent Test**: criar um banco vazio, rodar `alembic upgrade head` e comparar a estrutura resultante com o dump de produção — devem coincidir nas 9 tabelas e nos objetos de apoio.

### Tests for User Story 1 ⚠️

> Escrever primeiro; devem falhar antes da implementação

- [X] T007 [P] [US1] Criar `tests/unit/test_alembic_env_url.py` cobrindo `_build_database_url()`: `postgresql://…` → `postgresql+psycopg://…`; `postgres://…` → `postgresql+psycopg://…`; URL que já traz driver explícito é preservada intacta; ausência de `POSTGRES_DATABASE_URI` levanta erro
- [X] T008 [P] [US1] Criar `tests/unit/test_alembic_revisions.py` que carrega o `ScriptDirectory` do Alembic e verifica: existe exatamente **uma** revisão com `down_revision is None`, não há `revision` duplicado e a cadeia resolve até `head` sem ramificação
- [X] T009 [P] [US1] Criar `tests/integration/test_migrations_baseline.py` (exige PostgreSQL) cobrindo: `upgrade head` em banco vazio cria as 9 tabelas, a extensão `uuid-ossp`, a função `update_timestamp_column()`, os 3 gatilhos, o índice único parcial `prompts_one_default_per_node` e a restrição `prompts_node_type_check`; rodar `upgrade head` de novo é inofensivo; um `UPDATE` em `prompts` altera `updated_at` automaticamente

### Implementation for User Story 1

- [X] T010 [US1] Criar `migrations/versions/0001_baseline.py` com `revision = "0001_baseline"`, `down_revision = None` e o `upgrade()` iniciando por: `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` e a função `update_timestamp_column()` — DDL literal via `op.execute()` ([research.md R3](./research.md)), conforme [data-model.md §2](./data-model.md)
- [X] T011 [US1] Em `migrations/versions/0001_baseline.py`, acrescentar ao `upgrade()` as 9 tabelas na ordem `tenants` → `prompts` → `guardrails` → `prompt_guardrails` → `tenant_prompts` → `whatsapp_instances` → `agendamentos` (+ sequência `agendamentos_id_seq` e `OWNED BY`) → `chat_thread_sessions` → `tenant_knowledge_base`, copiando tipos e defaults **exatamente** como em [data-model.md §3](./data-model.md) — atenção a `agendamentos.created_at`/`deleted_at` que são `timestamp without time zone`, a `tenants.allowed_domains text[] DEFAULT '{}'::text[]` e a `whatsapp_instances.id` que usa `gen_random_uuid()` (e não `uuid_generate_v4()`)
- [X] T012 [US1] Em `migrations/versions/0001_baseline.py`, acrescentar ao `upgrade()` chaves primárias, `UNIQUE` (`unique_active_tenant_prompt`, `whatsapp_instances_instance_name_key`), os 8 índices — incluindo o parcial `prompts_one_default_per_node ... WHERE is_default = true` —, a `CHECK prompts_node_type_check`, as 3 chaves estrangeiras com `ON DELETE CASCADE` e os 3 gatilhos `update_*_modtime`
- [X] T013 [US1] Em `migrations/versions/0001_baseline.py`, implementar `downgrade()` levantando `RuntimeError` com mensagem explicativa quando `ALEMBIC_ALLOW_BASELINE_DOWNGRADE` não for `"1"`, e executando os `DROP` em ordem inversa quando for ([research.md R5](./research.md) — evita apagar produção inteira por engano)
- [X] T014 [US1] Conferir a baseline contra a fonte: aplicar em banco vazio, gerar `pg_dump --schema-only` e comparar objeto a objeto com `specs/004-alembic-migrations/data-model.md`; corrigir qualquer divergência **na migração**, nunca no data-model

**Checkpoint**: US1 completa — o banco é reprodutível do zero. Comandos de validação para o usuário:

```bash
pytest tests/unit/test_alembic_env_url.py tests/unit/test_alembic_revisions.py -v
pytest tests/integration/test_migrations_baseline.py -v
```

---

## Phase 4: User Story 2 - Adotar o versionamento sem tocar nos dados de produção (Priority: P1)

**Goal**: colocar o banco de produção sob controle das migrations sem alterar nenhuma estrutura ou linha.

**Independent Test**: num clone do banco de produção, marcar a baseline e verificar que o histórico passa a existir, nada foi alterado e um `upgrade head` subsequente não faz nada.

**⚠️ Estas são tarefas operacionais** — executadas pelo usuário contra bancos reais, não alterações de código.

- [~] T015 [US2] **PULADA** (decisão do usuário — adoção feita direto em produção com backup completo de 72 MB validado antes). Ensaiar em clone: restaurar um backup de produção num banco descartável e rodar a sequência do [quickstart.md Cenário 1](./quickstart.md) — `alembic current` (vazio) → `alembic stamp 0001_baseline` → `alembic current` (imprime `0001_baseline`) → `alembic upgrade head` (não faz nada, sai com sucesso)
- [~] T016 [US2] **PULADA** junto com T015 — a verificação de não-destrutividade foi feita direto em produção pela saída do psql (`CREATE TABLE` + `INSERT 0 1`, nenhum comando sobre as 9 tabelas). No mesmo clone, comparar a estrutura **antes e depois** do `stamp` com `pg_dump --schema-only --no-owner --no-privileges` e confirmar diferença **zero**; rodar também a consulta de contagem das 9 tabelas do quickstart e confirmar contagens idênticas
- [X] T017 [US2] Conferir produção contra a baseline **antes** de qualquer comando: `pg_dump --schema-only --no-owner --no-privileges "$POSTGRES_DATABASE_URI"` e comparar com [data-model.md](./data-model.md). Havendo divergência, **parar** e corrigir a baseline antes de prosseguir — **feito em 2026-08-21**: dump coletado do contêiner do banco (PostgreSQL 15.18) e comparado com a baseline: **diferença zero** nos 9 objetos do projeto e nos objetos de apoio (única exceção: extensão `vector`, excluída de propósito). Baseline também aplicada num `postgres:15` limpo, reproduzindo a estrutura de produção. **Achado**: produção roda PG 15.18, não 17.5 como registrado no levantamento inicial (aquele dump vinha do ambiente de desenvolvimento) — as duas estruturas são idênticas, e nenhum recurso da baseline exige versão acima da 15. Documentos corrigidos
- [X] T018 [US2] **CONCLUÍDA em 2026-08-21**: banco `interasisai` (contêiner `simplificandoai-db`, pgvector/pgvector:pg15). Backup de 72 MB gerado e validado antes. `stamp` aplicado via SQL equivalente (o `alembic` ainda não estava na imagem — ver quickstart Caminho A): saída `CREATE TABLE` + `INSERT 0 1`, sem nenhum comando sobre as 9 tabelas. Varredura confirmou `alembic_version = 0001_baseline` em exatamente um banco, sem órfãos. Executar em produção, após backup (`pg_dump "$POSTGRES_DATABASE_URI" > backup-pre-alembic-$(date +%F).dump`): `alembic stamp 0001_baseline`, seguido de `alembic current` e `alembic upgrade head` para verificação

**Checkpoint**: produção sob controle das migrations, com zero alteração de dados. **A partir daqui a Fase 6 fica liberada.**

---

## Phase 5: User Story 3 - Migrações aplicadas automaticamente a cada deploy (Priority: P2)

**Goal**: migrações pendentes são aplicadas antes de a aplicação atender requisições, sem intervenção manual.

**Independent Test**: subir o contêiner apontando para um banco em branco e confirmar, pelos logs, que as migrações rodam antes de a aplicação aceitar requisições.

- [X] T019 [US3] Criar `docker-entrypoint.sh` na raiz com `#!/bin/sh`, `set -e`, log de início, `alembic upgrade head` e `exec "$@"` — o `set -e` garante que uma migração falhada impeça a aplicação de subir (FR-009, [contracts/migration-cli.md §2](./contracts/migration-cli.md))
- [X] T020 [US3] Alterar `Dockerfile`: copiar `docker-entrypoint.sh`, incluí-lo no mesmo `sed -i -e 's/\r$//'` e `chmod +x` já aplicado a `start.sh` (linha 36 — evita erro de CRLF vindo do Windows) e declarar `ENTRYPOINT ["/app/docker-entrypoint.sh"]` mantendo o `CMD ["/app/start.sh"]` existente
- [ ] T021 [US3] Validar localmente com `docker compose -f docker-compose-local.yml up --build chatatendimento-api` apontando para um banco em branco, confirmando nos logs que o `upgrade` roda **antes** do uvicorn — e que o `command:` do Compose (que substitui o `CMD`) não impede a migração
- [X] T022 [US3] **CONCLUÍDA em 2026-08-21** — validado acidentalmente durante o T021: com o `.env` local apontando para `localhost:5432` (inalcançável de dentro do contêiner), o log mostrou `[entrypoint] Aplicando migrations pendentes...` seguido de `psycopg.OperationalError: connection failed` e `chatatendimento-api exited with code 1`. **O uvicorn nunca subiu** — FR-009 comprovado. Validar o caminho de falha: apontar para um banco inacessível e confirmar que o contêiner sai com código diferente de zero, com o erro visível em `docker logs`, sem servir requisições

**Checkpoint**: deploy aplica migrações sozinho e falha de forma segura

---

## Phase 6: User Story 4 - Aplicação deixa de alterar a estrutura do banco (Priority: P3)

**Goal**: nenhuma requisição de usuário dispara criação ou alteração de tabela; migrations viram a única fonte de verdade.

**Independent Test**: exercitar prompts, sessões de conversa, base de conhecimento e agendamentos com um usuário de banco **sem permissão de DDL** — tudo deve funcionar.

**⚠️ Bloqueada pela Fase 4 estar aplicada em produção** (ver aviso no topo).

### Tests for User Story 4 ⚠️

- [X] T023 [P] [US4] Criar `tests/unit/test_no_runtime_ddl.py`: varre os arquivos `.py` de `app/`, `modules/`, `infrastructure/`, `prompts/`, `protocols/` e `util/` e falha se encontrar `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX` ou `DROP TABLE`; `migrations/`, `tests/` e `specs/` ficam de fora. Deve **falhar** antes das remoções abaixo ([research.md R9](./research.md))

### Implementation for User Story 4

- [X] T024 [P] [US4] Em `modules/prompt_manager/prompt_manager_repository.py`, remover o método `ensure_node_type_schema()` (linhas 11-44) e suas 8 chamadas (linhas 69, 94, 126, 151, 181, 206, 258, 326); manter `seed_missing_node_prompts()` intacto — é *seed* de dado, não DDL
- [X] T025 [P] [US4] Em `modules/ia/thread_session.py`, remover `init_thread_sessions_table()` (linhas 23-36) e sua chamada em `resolve_active_thread_id()` (linha 47), ajustando o docstring do módulo que hoje afirma não haver framework de migração
- [X] T026 [P] [US4] Em `modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py`, remover a constante `_TABLE_DDL` (linhas 8-14), o método `_ensure_table()` (linhas 29-32) e sua chamada no `__init__` (linha 27), atualizando o docstring da classe (linhas 18-23) que cita a ausência de migrations
- [X] T027 [P] [US4] Em `modules/agendamento/booking_tools.py`, remover `init_booking_table()` (linhas 23-50) e sua chamada em `real_time_available()` (linha 59)
- [X] T028 [US4] Em `modules/agendamento/agenda_tool.py`, remover o import de `init_booking_table` (linha 8) e sua chamada (linha 43) — depende de T027
- [ ] T029 [US4] Validar sem permissão de DDL: criar um usuário PostgreSQL restrito (`REVOKE CREATE ON SCHEMA public`), apontar a aplicação para ele e exercitar prompts, guardrails, sessões de conversa, base de conhecimento e agendamentos, confirmando que nada falha por permissão (SC-004)

**Checkpoint**: todas as histórias completas; migrations são a única fonte de verdade do schema

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T030 [P] Atualizar o comentário de `infrastructure/connection.py` deixando claro que a estrutura do banco é gerenciada por `migrations/` e que o fallback de URL na linha 7 vale apenas para desenvolvimento
- [X] T031 [P] Verificar se `.gitignore` e `.dockerignore` (se existir) não excluem `migrations/` nem `alembic.ini` — a migração precisa entrar na imagem para o entrypoint funcionar
- [X] T032 Rodar a suíte completa e confirmar que 100% dos testes que passavam antes continuam passando (SC-007) — comando para o usuário: `pytest tests/ -v`
- [X] T033 Executar a validação do [quickstart.md](./quickstart.md) de ponta a ponta: Cenário 2 (banco novo do zero) e Cenário 3 (criar uma migração de teste, aplicar, reverter e descartar) — **feito**: baseline aplicada em banco temporário e comparada com o dump de produção (diferença zero); revisão de teste gerada, conferida e descartada; trava do `downgrade` validada nos dois caminhos (bloqueado por padrão com as 10 tabelas intactas; liberado com `ALEMBIC_ALLOW_BASELINE_DOWNGRADE=1`). Achado: `file_template` sozinho não gera numeração sequencial — é preciso `--rev-id`, agora documentado
- [X] T034 **CONCLUÍDA em 2026-08-21** — comentário publicado no EDI-37 com o resultado da adoção, o achado da versão do PostgreSQL e o estado das 4 histórias. Comentar no EDI-37 o resultado da adoção em produção: data do `stamp`, contagens antes/depois e os achados que viraram tickets próprios (FKs de `tenant_id`, gatilho faltante em `tenants`, padronização de UUID, `tenants.active`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sem dependências
- **Foundational (Fase 2)**: depende da Fase 1 — **bloqueia todas as histórias**
- **US1 (Fase 3)**: depende da Fase 2
- **US2 (Fase 4)**: depende da **US1 completa** — não há o que marcar sem a baseline pronta e conferida
- **US3 (Fase 5)**: depende da Fase 2; pode ser desenvolvida em paralelo à US2, mas só deve ir a produção **depois** da US2 aplicada (senão o primeiro deploy tentaria `upgrade` num banco não marcado e falharia com `relation already exists`)
- **US4 (Fase 6)**: depende da **US2 aplicada em produção** — restrição operacional, não apenas de código
- **Polish (Fase 7)**: depois das histórias desejadas

### Diferença em relação ao padrão

As histórias desta feature **não** são mutuamente independentes como no caso comum: formam uma cadeia (baseline → adoção → automação → limpeza). Isso é inerente ao domínio — não dá para remover o DDL de runtime antes de existir algo que o substitua. Cada fase permanece, ainda assim, validável isoladamente pelos seus próprios critérios.

### Parallel Opportunities

- T003 (`alembic.ini`) roda em paralelo a T001/T002
- T004 e T006 em paralelo dentro da Fase 2
- T007, T008 e T009 (os três arquivos de teste da US1) em paralelo
- T024 a T027 em paralelo — quatro arquivos distintos; T028 depende de T027
- T030 e T031 em paralelo

---

## Parallel Example: User Story 1

```bash
# Os três arquivos de teste da US1, juntos:
Task: "Criar tests/unit/test_alembic_env_url.py"
Task: "Criar tests/unit/test_alembic_revisions.py"
Task: "Criar tests/integration/test_migrations_baseline.py"
```

## Parallel Example: User Story 4

```bash
# As quatro remoções de DDL em runtime, juntas:
Task: "Remover ensure_node_type_schema() em modules/prompt_manager/prompt_manager_repository.py"
Task: "Remover init_thread_sessions_table() em modules/ia/thread_session.py"
Task: "Remover _ensure_table() em modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py"
Task: "Remover init_booking_table() em modules/agendamento/booking_tools.py"
```

---

## Implementation Strategy

### MVP (US1 apenas)

1. Fase 1: Setup
2. Fase 2: Foundational (bloqueia tudo)
3. Fase 3: US1
4. **PARAR e VALIDAR**: banco vazio → `alembic upgrade head` → estrutura idêntica a produção
5. Neste ponto o projeto já é instalável do zero — valor entregue mesmo que nada mais avance

### Entrega incremental

1. Setup + Foundational → base pronta
2. + US1 → banco reprodutível (**MVP**)
3. + US2 → produção sob controle, com zero risco
4. + US3 → deploy automatiza as migrações
5. + US4 → schema com fonte de verdade única

### Estratégia com múltiplos desenvolvedores

O paralelismo entre histórias é limitado pela cadeia descrita acima. O que dá para paralelizar de verdade: enquanto um desenvolvedor escreve a baseline (T010–T014), outro pode adiantar a US3 (T019–T020) e o teste-guarda da US4 (T023), que não dependem do conteúdo da migração.

---

## Comandos de teste (para o usuário executar)

```bash
# Unitários — mesmo conjunto que o CI de deploy roda
pytest tests/unit -v

# Integração — exigem PostgreSQL acessível
pytest tests/integration -v

# Suíte completa
pytest tests/ -v
```

---

## Notes

- Tarefas `[P]` = arquivos diferentes, sem dependência entre si
- A regra de ouro da `0001`: **espelho fiel de produção**. Nada de corrigir schema ali — como em produção ela é apenas registrada (`stamp`) e nunca executada, qualquer correção escrita nela jamais chegaria lá. Correções vão em migrações `0002+`
- Nunca usar `alembic revision --autogenerate` neste projeto (sem modelos SQLAlchemy, proporia remover todas as tabelas)
- Commit após cada tarefa ou grupo lógico

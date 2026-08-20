---

description: "Task list template for feature implementation"
---

# Tasks: Guardrails Independentes por Nó (Operational, Institutional, Chitchat)

**Input**: Design documents from `/specs/003-guardrails-por-no/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Ticket**: EDI-42

**Tests**: Incluídas — Princípio VI da constituição exige testes unitários e de integração para todo código novo; não são opcionais aqui, mesmo `prompt_manager` sendo um módulo legado (a Legacy Migration Policy só dispensa a re-camadização do Princípio III, não o Princípio VI).

**Auth**: Endpoints de `/prompt-manager/*` continuam sem autenticação — estado pré-existente do módulo, já registrado na feature 001. Nenhuma mudança de postura de segurança nesta feature.

**Organization**: Tarefas agrupadas por user story (spec.md), para implementação e teste independentes de cada uma.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência entre si)
- **[Story]**: US1/US2/US3, conforme spec.md
- Caminhos de arquivo exatos em cada descrição

## Path Conventions

Projeto único (backend FastAPI) — caminhos a partir da raiz do repositório, conforme `plan.md`.

---

## Phase 1: Setup

**Purpose**: Confirmar baseline antes de alterar código

- [X] T001 Rodar a suíte de testes atual (`pytest`) e confirmar que está verde antes de iniciar — nenhuma alteração de código nesta tarefa

**Checkpoint**: baseline confirmada.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestrutura genérica de `node_type` — bloqueia as três user stories, pois nenhuma delas funciona sem a coluna existir e sem as funções de resolução saberem filtrar por nó

**⚠️ CRITICAL**: Nenhuma user story pode começar antes desta fase, pois todas dependem da coluna `node_type` existir no banco

- [X] T002 Adicionar `ensure_node_type_schema()` em `modules/prompt_manager/prompt_manager_repository.py`: DDL idempotente (`ALTER TABLE prompts ADD COLUMN IF NOT EXISTS node_type TEXT NOT NULL DEFAULT 'operational'`, `CHECK` restringindo aos 3 valores, índice único parcial `is_default` por `node_type` — ver `data-model.md`); chamada no `__init__` do repositório, mesmo padrão idempotente de `init_thread_sessions_table()` em `modules/ia/thread_session.py`

### Tests for Foundational ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T003 [P] Teste: `get_active_prompt_by_tenant`/`get_default_prompt`/`get_all_prompts`/`create_prompt` filtram e persistem `node_type` corretamente — `tests/integration/test_prompt_manager_node_type.py` (ajustado de `tests/unit/` para `tests/integration/` durante a implementação: essas funções sempre tocam Postgres real, mesma convenção de `test_prompt_manager_sync.py`, não fakes)
- [X] T004 [P] Teste de integração: vincular um tenant a um prompt de um `node_type` NÃO desativa o vínculo ativo de outro `node_type` do mesmo tenant — estendido `tests/integration/test_prompt_manager_sync.py` (também corrigido um teste pré-existente que assumia "no máximo 1 vínculo ativo por tenant" globalmente — a invariante correta agora é por `node_type`)
- [X] T005 [P] Teste de integração: `POST`/`PUT /prompt-manager/prompts` aceita e persiste `node_type` (default `"operational"` quando omitido); `422` para valor fora dos 3 aceitos — `tests/integration/test_prompt_manager_node_type_api.py`
- [X] T006 [P] Teste de integração: `GET /prompt-manager/tenant/{tenant_id}?node_type=` retorna o prompt/guardrails do nó pedido — estendido `tests/integration/test_tenant_prompt_overview_api.py`

### Implementation for Foundational

- [X] T007 Atualizar `create_prompt`, `update_prompt` e `get_all_prompts` em `modules/prompt_manager/prompt_manager_repository.py` para aceitar/retornar `node_type` (depende de T002; faz T003 avançar)
- [X] T008 Atualizar `get_active_prompt_by_tenant(tenant_id, node_type="operational")` e `get_default_prompt(node_type="operational")` em `modules/prompt_manager/prompt_manager_repository.py` para filtrar por `node_type` (depende de T002; faz T003 passar)
- [X] T009 Reescrever `sync_tenant_prompt` em `modules/prompt_manager/prompt_manager_repository.py` para descobrir o `node_type` do `prompt_id` recebido e escopar a desativação de vínculos antigos apenas a esse `node_type` (via `JOIN` em `prompts`, ver `research.md` R2) (depende de T002; faz T004 passar)
- [X] T010 [P] Adicionar `node_type: Literal["operational","institutional","chitchat"] = "operational"` em `PromptCreateSchema` e `node_type: str` em `TenantPromptOverviewResponse`, em `app/schemas/prompt_manager.py`
- [X] T011 Atualizar `create_prompt_with_relations`/`update_prompt_with_relations` em `modules/prompt_manager/prompt_manager_service.py` para repassar `node_type` (depende de T007, T010)
- [X] T012 Atualizar `POST`/`PUT`/`GET /prompt-manager/prompts` em `app/api/v1/endpoints/prompt_manager.py`: aceitar `node_type` no corpo e um query param opcional `node_type` no `GET` para filtrar (depende de T011; faz T005 passar)
- [X] T013 Atualizar `GET /prompt-manager/tenant/{tenant_id}` em `app/api/v1/endpoints/prompt_manager.py` para aceitar `?node_type=` (default `"operational"`, preserva o contrato atual) (depende de T008, T011; faz T006 passar)

**Checkpoint**: coluna `node_type` existe, é filtrável e não há mais desativação cruzada de vínculos entre nós — US1 e US2 podem começar.

---

## Phase 3: User Story 1 - Associar guardrails ao chitchat_node (Priority: P1) 🎯 MVP

**Goal**: Administrador consegue vincular guardrails exclusivos ao `chitchat_node` de um tenant, sem afetar `operational_node`/`institutional_node`; tenants sem nada configurado continuam com o comportamento atual (fallback local), sem erro.

**Independent Test**: Vincular um guardrail a um prompt `node_type="chitchat"` de um tenant, confirmar via `GET /prompt-manager/tenant/{id}?node_type=chitchat` que ele aparece isolado dos guardrails do `operational_node`, e confirmar que uma conversa casual real aplica a regra.

### Tests for User Story 1 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T014 [P] [US1] Teste unitário de `carregar_chitchat_prompt(tenant_id)` em `tests/unit/test_load_prompt_chitchat.py` — usa o vínculo próprio do tenant quando existe; sem vínculo nem prompt padrão, cai no texto fixo local atual (idêntico ao comportamento hoje)
- [X] T015 [P] [US1] Teste de integração cobrindo os Acceptance Scenarios da US1 em `tests/integration/test_chitchat_node_guardrails.py`: guardrail vinculado ao `chitchat_node` de um tenant não aparece na resolução do `operational_node` do mesmo tenant; tenant sem nenhum guardrail de chitchat configurado responde normalmente (fallback), sem erro

### Implementation for User Story 1

- [X] T016 [US1] Adicionar `carregar_chitchat_prompt(tenant_id)` em `prompts/load_prompt.py`, espelhando `carregar_operacional_prompt`: nível 1 = vínculo ativo `node_type="chitchat"` do tenant (conteúdo + guardrails vinculados a esse prompt + globais); nível 2 = prompt `is_default=TRUE, node_type="chitchat"` se existir; nível 3 = texto fixo hoje embutido em `chitchat_node`/`guardrails.md` (depende de T008; faz T014 passar)
- [X] T017 [US1] Atualizar `chitchat_node` em `modules/ia/agent_graph.py` para chamar `carregar_chitchat_prompt(tenant_id)` no lugar da leitura direta de `guardrails.md`, preservando o `try/except` com fallback de segurança já existente (depende de T016; faz T015 passar)

**Checkpoint**: US1 completa e testável de forma independente — MVP entregável.

---

## Phase 4: User Story 2 - Associar guardrails ao institutional_node de forma independente (Priority: P2)

**Goal**: Administrador consegue vincular guardrails exclusivos ao `institutional_node` de um tenant, independentes dos do `operational_node`/`chitchat_node`; quando não houver vínculo institucional próprio, o sistema continua aplicando os guardrails do `operational_node` do tenant (comportamento idêntico ao atual).

**Independent Test**: Vincular um guardrail a um prompt `node_type="institutional"` de um tenant que já tem guardrails no `operational_node`; confirmar via `GET /prompt-manager/tenant/{id}?node_type=institutional` que apenas o guardrail institucional aparece; remover o vínculo e confirmar que a resposta volta a refletir os guardrails do `operational_node`.

### Tests for User Story 2 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T018 [P] [US2] Teste unitário de `carregar_institutional_prompt(...)` em `tests/unit/test_load_prompt_institutional.py` — com vínculo institucional próprio, usa seu conteúdo e seus guardrails; sem vínculo institucional, usa o template local (`institutional_prompt.md`) com os guardrails resolvidos pela cadeia do `operational_node` do tenant — idêntico ao comportamento atual
- [X] T019 [P] [US2] Teste de integração cobrindo os Acceptance Scenarios da US2 em `tests/integration/test_institutional_node_guardrails.py`: guardrail vinculado ao `institutional_node` não aparece em `operational_node`/`chitchat_node`; tenant sem vínculo institucional aplica os guardrails do `operational_node`, igual a hoje

### Implementation for User Story 2

- [X] T020 [P] [US2] Extrair o texto de instrução hoje hardcoded em `institutional_node` (`modules/ia/agent_graph.py`) para um novo arquivo `prompts/institutional_prompt.md`, com as tags `{guardrails}`, `{contexto_formatado}`, `{historico_texto}`, `{pergunta_usuario}` — mesma convenção de `prompts/operactional_prompt.md`
- [X] T021 [US2] Adicionar `carregar_institutional_prompt(tenant_id, contexto_formatado, historico_texto, pergunta_usuario)` em `prompts/load_prompt.py`: nível 1 = vínculo ativo `node_type="institutional"` do tenant (conteúdo + guardrails vinculados a esse prompt + globais); nível 2 = template local `institutional_prompt.md` + guardrails resolvidos pela cadeia atual do `operational_node` do tenant (reaproveita `carregar_guardrails`) (depende de T008, T020; faz T018 passar)
- [X] T022 [US2] Atualizar `institutional_node` em `modules/ia/agent_graph.py` para montar o `prompt_final` a partir de `carregar_institutional_prompt(...)` no lugar do f-string hoje embutido (depende de T021; faz T019 passar)

**Checkpoint**: US1 e US2 completas e independentes entre si.

---

## Phase 5: User Story 3 - Continuidade de atendimento durante a transição (Priority: P3)

**Goal**: Tenants já configurados antes desta feature não sofrem nenhuma regressão, e ganham um ponto de partida editável: um prompt `institutional` próprio (cópia do `operational` vigente) e um prompt `chitchat` padrão único (cópia do texto fixo atual), criados automaticamente e de forma idempotente.

**Independent Test**: Rodar o seed contra um tenant já existente antes da feature; confirmar que `operational_node`, `institutional_node` e `chitchat_node` continuam respondendo com os mesmos guardrails de antes, e que agora existe um prompt `institutional` editável para esse tenant e um prompt `chitchat` padrão no sistema.

### Tests for User Story 3 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T023 [P] [US3] Teste de integração do seed idempotente em `tests/integration/test_prompt_manager_seed.py`: cria 1 prompt `is_default=TRUE, node_type="chitchat"` se nenhum existir (não duplica ao rodar de novo); para cada tenant com vínculo `operational` ativo e sem vínculo `institutional` ativo, cria uma cópia do prompt (conteúdo + `prompt_guardrails`) e o vínculo `institutional` correspondente (não duplica ao rodar de novo)
- [X] T024 [P] [US3] Teste de integração de regressão em `tests/integration/test_prompt_manager_seed.py`: para um tenant configurado como estava antes desta feature (só vínculo `operational`), confirmar que a resolução de `institutional_node` e `chitchat_node` retorna exatamente os mesmos guardrails que retornava antes do seed rodar (User Story 3, Acceptance Scenario 1)

### Implementation for User Story 3

- [X] T025 [US3] Adicionar `seed_missing_node_prompts()` em `modules/prompt_manager/prompt_manager_repository.py`: cria o prompt padrão único de `chitchat` (texto atual como conteúdo) se não existir nenhum `is_default=TRUE, node_type="chitchat"`; para cada tenant com vínculo `operational` ativo sem vínculo `institutional` ativo, copia prompt + `prompt_guardrails` e cria o vínculo `institutional` (depende de T007, T009, T020; faz T023 e T024 passarem)
- [X] T026 [US3] Chamar `seed_missing_node_prompts()` logo após `ensure_node_type_schema()`, no mesmo ponto de inicialização idempotente do repositório (depende de T002, T025)

**Checkpoint**: as três user stories completas, sem regressão para tenants pré-existentes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Garantias que atravessam todas as stories

- [X] T027 [P] Executar a validação manual de `quickstart.md` de ponta a ponta contra uma instância local (Postgres real)
- [X] T028 [P] Revisar tags/summaries do OpenAPI (Swagger) dos endpoints alterados em `app/api/v1/endpoints/prompt_manager.py`
- [X] T029 Rodar a suíte completa de testes (`pytest`) e confirmar que está 100% verde, incluindo os testes novos desta feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente
- **Foundational (Phase 2)**: depende do Setup — BLOQUEIA as três user stories (nenhuma resolve prompt por nó sem a coluna `node_type` e sem `sync_tenant_prompt` isolado por nó)
- **User Stories (Phase 3-5)**: todas dependem apenas do Foundational
  - US1 (Phase 3): sem dependência de US2/US3
  - US2 (Phase 4): sem dependência de código de US1 (arquivos próprios); pode rodar em paralelo com US1 se houver mais de um dev
  - US3 (Phase 5): reaproveita `institutional_prompt.md` criado na US2 (T020) para o conteúdo do seed — não é totalmente independente em código, mas é independentemente testável depois que a US2 estiver pronta
- **Polish (Phase 6)**: depende de US1, US2 e US3 estarem prontas

### Parallel Opportunities

- Todos os testes `[P]` de uma mesma fase podem ser escritos em paralelo entre si (arquivos diferentes)
- T003-T006 (testes do Foundational) são paralelos entre si
- Depois do Foundational pronto: US1 (Phase 3) e US2 (Phase 4) podem ser desenvolvidas em paralelo por devs diferentes — não compartilham arquivos de implementação
- US3 (Phase 5) só pode começar depois que a US2 terminar (depende de `institutional_prompt.md`, criado em T020)

---

## Parallel Example: Foundational

```bash
# Testes do Foundational em paralelo:
Task: "Teste unitário de filtro por node_type em tests/unit/test_prompt_manager_node_type.py"
Task: "Teste de integração de isolamento de sync_tenant_prompt em tests/integration/test_prompt_manager_sync.py"
Task: "Teste de integração de node_type em POST/PUT /prompts em tests/integration/test_prompt_manager_node_type_api.py"
Task: "Teste de integração de GET /tenant/{id}?node_type= em tests/integration/test_tenant_prompt_overview_api.py"
```

## Parallel Example: User Story 1 + User Story 2 (times diferentes)

```bash
# Dev A - US1:
Task: "carregar_chitchat_prompt em prompts/load_prompt.py"
Task: "chitchat_node em modules/ia/agent_graph.py"

# Dev B - US2 (em paralelo):
Task: "prompts/institutional_prompt.md"
Task: "carregar_institutional_prompt em prompts/load_prompt.py"
Task: "institutional_node em modules/ia/agent_graph.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Phase 1 (Setup) + Phase 2 (Foundational) — CRÍTICO, bloqueia tudo
2. Completar Phase 3 (US1 - chitchat)
3. **PARAR e VALIDAR**: confirmar via `quickstart.md` que guardrails de chitchat são exclusivos e que tenants sem configuração continuam funcionando
4. Esse é o MVP entregável ao time de frontend para começar a construir a tela

### Entrega Incremental

1. Setup + Foundational → coluna `node_type` disponível, API genérica pronta
2. US1 → validar independentemente → MVP (guardrails de chitchat)
3. US2 → validar independentemente → guardrails de institutional independentes, com fallback correto
4. US3 → validar independentemente → zero regressão para tenants existentes + prompts editáveis seedados
5. Phase 6 → quickstart validado de ponta a ponta, OpenAPI revisado, suíte completa verde

---

## Implementation Notes (post-execution)

- Todas as 29 tarefas foram implementadas; suíte completa: 91 testes passando (60 pré-existentes + 31 novos desta feature), mesmas 2 falhas + 2 erros pré-existentes e não relacionados (`modules/vetorizacao/test_gerenciador_vetores.py`, `modules/webhook/test_whatsapp.py`, `protocols/test_file_data_reader.py`) já presentes na baseline (T001), não tocados por esta feature.
- Ajustes feitos durante a implementação em relação ao desenho original do `research.md`:
  - `ensure_node_type_schema()` **não** roda no `__init__` do repositório (como o research.md sugeria) — rodar ali quebrava o isolamento dos testes unitários que substituem `.repository` por um fake logo após instanciar o `PromptManagerService`. Passou a rodar no início de cada método que efetivamente toca `node_type`, mesmo padrão de `init_thread_sessions_table()`.
  - A sintaxe `ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS` do `data-model.md` não existe no PostgreSQL; substituída por um bloco `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint ...)` idempotente.
  - `get_all_prompts(node_type=None)` precisou de cast explícito (`%(node_type)s::text`) — o psycopg3 não infere o tipo de um parâmetro `NULL` usado só em comparação (`AmbiguousParameter`).
  - Um teste pré-existente (`test_prompt_manager_sync.py::test_returns_only_active_when_multiple_exist`) assumia "no máximo 1 vínculo ativo por tenant" globalmente; corrigido para escopar a checagem ao `node_type='operational'`, já que a invariante correta agora é por nó (FR-009).
  - `seed_missing_node_prompts()` recebe o texto padrão do chitchat como parâmetro (não lê arquivos diretamente) para manter o repositório sem depender de `prompts/` — quem monta esse texto é o chamador (`app/main.py`, no startup).
- T027 (`quickstart.md`) foi executado de ponta a ponta contra o Postgres local real (tenant `1234`), não só simulado, e pegou um efeito real do próprio processo de teste: um `DELETE` de limpeza usado entre execuções de teste havia removido o prompt padrão de chitchat (`is_default=TRUE, node_type='chitchat'`) que o seed de outra rodada tinha criado, fazendo `GET /prompt-manager/tenant/1234?node_type=chitchat` retornar `500` (nenhum default configurado). Recriado rodando o seed novamente (equivalente ao que o `startup` da aplicação faz) — não é um bug de código, mas confirma que o seed de boot (T026) é o que mantém esse caminho saudável em produção.
- Estado do banco local restaurado ao final: nenhum prompt/guardrail de teste (`%EDI42%`/`%EDI-42%`) deixado para trás, exceto o prompt padrão legítimo de chitchat (`Chitchat - Padrão`, `is_default=TRUE`) e a cópia institucional legítima do tenant `1234` (`Interasis AI - Com GREETING`) — ambos resultado esperado do seed rodando contra dados reais, não artefato de teste.

## Notes

- `[P]` = arquivos diferentes, sem dependência entre as tarefas
- Cada user story deve ser completável e testável de forma independente, mesmo quando reaproveita um arquivo criado por outra story (US3 reaproveita `institutional_prompt.md` da US2)
- Escrever os testes antes da implementação e confirmar que falham, por exigência do Princípio VI da constituição do projeto
- `prompt_manager` é módulo legado (Legacy Migration Policy) — toda extensão feita aqui reaproveita os métodos públicos já existentes do repositório/serviço, sem SQL novo fora de `PromptManagerRepository` e sem lógica de negócio nova direto no endpoint
- Nenhuma tabela nova é criada — apenas uma coluna (`node_type`) em `prompts`, via DDL idempotente no mesmo padrão já usado no repositório

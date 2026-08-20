---

description: "Task list template for feature implementation"
---

# Tasks: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

**Input**: Design documents from `/specs/001-admin-tenant-management/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluídas — a Constitução do projeto (Princípio VI) exige testes unitários e de integração para todo código novo; não são opcionais aqui.

**Auth**: Nenhum endpoint desta feature tem autenticação — decisão explícita do usuário, documentada em `plan.md` (Constitution Check / Complexity Tracking) e `research.md` #1. Login/JWT de admin fica para uma feature futura; por isso não há mais uma fase "Foundational" de auth aqui.

**Organization**: Tarefas agrupadas por user story (spec.md), para implementação e teste independentes de cada uma.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência entre si)
- **[Story]**: US1/US2/US3/US4, conforme spec.md
- Caminhos de arquivo exatos em cada descrição

## Path Conventions

Projeto único (backend FastAPI) — caminhos a partir da raiz do repositório, conforme `plan.md`.

---

## Phase 1: Setup

**Purpose**: Criar o esqueleto de diretórios que as fases seguintes vão preencher

- [X] T001 Criar esqueleto de diretórios e `__init__.py` para `modules/knowledge_base/` (`domain/`, `application/`, `infrastructure/`), `tests/unit/`, `tests/unit/knowledge_base/` e `tests/integration/`, conforme a estrutura definida em `plan.md`

**Checkpoint**: nenhuma fase bloqueante adicional — as user stories abaixo já podem começar.

---

## Phase 2: User Story 1 - Buscar tenant e visualizar prompts e guardrails vinculados (Priority: P1) 🎯 MVP

**Goal**: Admin busca um tenant por nome/id e vê o prompt (custom ou padrão) e os guardrails vinculados, sem nunca cair em erro de sistema.

**Independent Test**: `GET /api/v1/tenants?q=...` retorna o tenant certo; `GET /api/v1/prompt-manager/tenant/{id}` retorna o prompt vinculado quando existir, ou o prompt padrão + guardrails globais com `is_default_prompt: true` quando não houver vínculo.

### Tests for User Story 1 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T002 [P] [US1] Teste unitário de `TenantRepository.search_tenants` / `TenantService.search_tenants` em `tests/unit/test_tenant_search.py` — casamento parcial e case-insensitive por `id`/`name`, respeita `limit`
- [X] T003 [P] [US1] Teste unitário do fallback de prompt padrão em `PromptManagerService` em `tests/unit/test_prompt_manager_fallback.py` — com vínculo ativo retorna o prompt custom; sem vínculo retorna o prompt `is_default=TRUE` + guardrails `is_global=TRUE`; sem nenhum prompt padrão configurado levanta erro (não retorna vazio silenciosamente)
- [X] T004 [P] [US1] Teste de integração de `GET /api/v1/tenants?q=` em `tests/integration/test_tenant_search_api.py` — `200` com resultados, `200` com lista vazia quando não há match, `422` quando `q` vazio
- [X] T005 [P] [US1] Teste de integração de `GET /api/v1/prompt-manager/tenant/{id}` em `tests/integration/test_tenant_prompt_overview_api.py` — `404` tenant inexistente, caso com vínculo custom, caso de fallback (`is_default_prompt: true`)

### Implementation for User Story 1

- [X] T006 [US1] Adicionar `search_tenants(term, limit)` em `modules/tenant/tenant_repository.py` (SQL `ILIKE` sobre `id`/`name`)
- [X] T007 [US1] Adicionar `search_tenants(term)` em `modules/tenant/tenant_service.py` (depende de T006)
- [X] T008 [US1] Adicionar endpoint `GET /tenants?q=` em `app/api/v1/endpoints/tenant.py` (depende de T007)
- [X] T009 [P] [US1] Validar `q` como string obrigatória (`min_length=1`) e `limit` (default 20, máx 100) no schema/query params de busca em `app/schemas/tenant.py`
- [X] T010 [US1] Adicionar `get_default_prompt()` e `get_global_guardrails()` em `modules/prompt_manager/prompt_manager_repository.py`
- [X] T011 [US1] Atualizar `PromptManagerService` em `modules/prompt_manager/prompt_manager_service.py` com o fallback para prompt padrão + guardrails globais quando não houver vínculo ativo (depende de T010)
- [X] T012 [US1] Atualizar `GET /prompt-manager/tenant/{tenant_id}` em `app/api/v1/endpoints/prompt_manager.py`: verificar existência do tenant via `TenantService` (`404` se não existir), then chamar o fallback do serviço, incluindo `is_default_prompt` na resposta (depende de T011, T007)
- [X] T013 [P] [US1] Adicionar `TenantPromptOverviewResponse` (com `is_default_prompt: bool`) em `app/schemas/prompt_manager.py`

**Checkpoint**: US1 completa e testável de forma independente — MVP entregável.

---

## Phase 3: User Story 2 - Editar a base de conhecimento de um tenant (Priority: P2)

**Goal**: Admin visualiza o conteúdo atual da base de conhecimento de um tenant e o substitui, com revetorização automática em background (sem acumular vetores antigos).

**Independent Test**: `PUT /api/v1/tenants/{id}/knowledge-base` grava o novo conteúdo; `GET` imediatamente após reflete o novo texto; os vetores antigos são removidos antes dos novos serem inseridos (não coexistem).

### Tests for User Story 2 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T014 [P] [US2] Teste unitário da validação de `KnowledgeBaseDocument` (conteúdo vazio levanta erro de domínio) em `tests/unit/knowledge_base/test_knowledge_base_document.py`
- [X] T015 [P] [US2] Teste unitário dos use cases `GetTenantKnowledgeBase`/`UpsertTenantKnowledgeBase` com ports fake em memória, em `tests/unit/knowledge_base/test_upsert_tenant_knowledge_base.py` — upsert persiste via `KnowledgeBaseRepositoryPort`; conteúdo vazio é rejeitado antes de tocar qualquer port
- [X] T016 [P] [US2] Teste de integração `GET`/`PUT` de `/api/v1/tenants/{id}/knowledge-base` em `tests/integration/test_tenant_knowledge_base_api.py` — `GET` retorna `content: null` antes de criar; `PUT` cria; `PUT` de novo substitui (via fake `VectorStorePort`, confirma delete-então-reindex, não append); `422` conteúdo vazio; `404` tenant inexistente

### Implementation for User Story 2

- [X] T017 [P] [US2] Entidade de domínio `KnowledgeBaseDocument` (valida conteúdo não vazio) em `modules/knowledge_base/domain/knowledge_base_document.py`
- [X] T018 [P] [US2] Ports `KnowledgeBaseRepositoryPort` e `VectorStorePort` (Protocols) em `modules/knowledge_base/application/ports.py`
- [X] T019 [US2] Use cases `GetTenantKnowledgeBase`, `UpsertTenantKnowledgeBase`, `ReindexTenantKnowledgeBase` em `modules/knowledge_base/application/use_cases.py` (depende de T017, T018)
- [X] T020 [US2] `PostgresKnowledgeBaseRepository` (cria `tenant_knowledge_base` via `CREATE TABLE IF NOT EXISTS`, implementa get/upsert) em `modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py` (depende de T018)
- [X] T021 [US2] Adicionar `deletar_por_tenant(tenant_id)` em `modules/vetorizacao/gerenciador_vetores.py` (`DELETE FROM langchain_pg_embedding ... WHERE cmetadata->>'tenant_id' = %s`, escopado à collection `interasis_knowledge`)
- [X] T022 [US2] `PgVectorKnowledgeBaseAdapter` implementando `VectorStorePort` (reindex = `deletar_por_tenant` + `criar_banco_com_textos`) em `modules/knowledge_base/infrastructure/pgvector_knowledge_base_adapter.py` (depende de T018, T021)
- [X] T023 [P] [US2] Schemas `KnowledgeBaseResponse` e `KnowledgeBaseUpsertRequest` (`content` com `min_length=1`) em `app/schemas/knowledge_base.py`
- [X] T024 [US2] Endpoints `GET` e `PUT` de `/tenants/{tenant_id}/knowledge-base` em `app/api/v1/endpoints/knowledge_base.py`: `404` se tenant não existe, `PUT` agenda a revetorização via `BackgroundTasks` (depende de T019, T020, T022, T023, T007)
- [X] T025 [US2] Registrar o router de `knowledge_base` em `app/api/v1/router.py` e incluí-lo em `app/main.py` (depende de T024)

**Checkpoint**: US2 completa e testável de forma independente (o `PUT` já cobre também a base do US4).

---

## Phase 4: User Story 3 - Excluir a base de conhecimento de um tenant (Priority: P3)

**Goal**: Admin remove definitivamente a base de conhecimento de um tenant (texto + vetores).

**Independent Test**: `DELETE /api/v1/tenants/{id}/knowledge-base` remove o conteúdo; `GET` seguinte retorna `content: null`; chamar `DELETE` quando já não há base retorna `404`, sem afetar outros tenants.

### Tests for User Story 3 ⚠️ (escrever ANTES da implementação, e confirmar que falham)

- [X] T026 [P] [US3] Teste unitário do use case `DeleteTenantKnowledgeBase` em `tests/unit/knowledge_base/test_delete_tenant_knowledge_base.py` — remove via `KnowledgeBaseRepositoryPort` e aciona `VectorStorePort`; deletar quando não existe sinaliza "não encontrado"
- [X] T027 [P] [US3] Teste de integração `DELETE /api/v1/tenants/{id}/knowledge-base` (estender `tests/integration/test_tenant_knowledge_base_api.py`) — `200` remove e `GET` seguinte retorna `content: null`; `404` quando não há base para excluir; `404` tenant inexistente

### Implementation for User Story 3

- [X] T028 [US3] Adicionar `delete()` ao repositório (`PostgresKnowledgeBaseRepository`) e o use case `DeleteTenantKnowledgeBase` em `modules/knowledge_base/application/use_cases.py` (depende de T019, T020)
- [X] T029 [US3] Endpoint `DELETE /tenants/{tenant_id}/knowledge-base` em `app/api/v1/endpoints/knowledge_base.py`: `404` tenant inexistente, `404` quando não há base cadastrada, agenda remoção dos vetores em background (depende de T028, T024)

**Checkpoint**: US3 completa e testável de forma independente.

---

## Phase 5: User Story 4 - Cadastrar nova base de conhecimento para um tenant (Priority: P3)

**Goal**: Admin cadastra a base de conhecimento de um tenant que ainda não possui uma.

**Independent Test**: `PUT /api/v1/tenants/{id}/knowledge-base` para um tenant sem base prévia cria o conteúdo; `GET` seguinte reflete o novo conteúdo.

> Não há código de produção novo aqui: o `PUT` implementado na US2 já é um upsert (cria quando não existe, substitui quando existe). Esta fase garante cobertura de teste dedicada para o cenário de criação, validando a US4 de forma independente.

### Tests for User Story 4 ⚠️

- [X] T030 [US4] Teste de integração: `PUT` em `/api/v1/tenants/{id}/knowledge-base` para um tenant sem base prévia cria o conteúdo (`200`, `GET` seguinte reflete) — adicionar caso em `tests/integration/test_tenant_knowledge_base_api.py` (depende de T024 já implementado na US2)

**Checkpoint**: Todas as 4 user stories funcionam de forma independente.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Garantias que atravessam todas as stories

- [X] T031 [P] Teste de integração de isolamento multi-tenant: em `tests/integration/test_tenant_knowledge_base_api.py`, provar que `PUT`/`DELETE` na base de conhecimento do tenant A não afeta o `GET` do tenant B (Princípio I da constituição)
- [X] T032 [P] Executar a validação manual de `quickstart.md` de ponta a ponta contra uma instância local
- [X] T033 [P] Revisar tags/summaries do OpenAPI (Swagger) dos endpoints novos/alterados em `app/api/v1/endpoints/tenant.py`, `prompt_manager.py` e `knowledge_base.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente
- **User Stories (Phase 2-5)**: todas dependem apenas do Setup (não há mais fase Foundational — auth ficou para uma feature futura)
  - US1 (Phase 2): sem dependência de outras stories
  - US2 (Phase 3): sem dependência de US1 (endpoints e módulo próprios); pode rodar em paralelo com US1 se houver mais de um dev
  - US3 (Phase 4): depende do módulo `knowledge_base` criado na US2 (T017-T023) — não é independente em código, mas é independentemente testável depois que a US2 estiver pronta
  - US4 (Phase 5): depende do endpoint `PUT` criado na US2 (T024) — sem código novo, só teste
- **Polish (Phase 6)**: depende de US1, US2 e US3 estarem prontas (T031 precisa do `PUT`/`DELETE` funcionando para dois tenants)

### Parallel Opportunities

- Todos os testes `[P]` de uma mesma story podem ser escritos em paralelo entre si (arquivos diferentes)
- T017 e T018 (domínio e ports da US2) são `[P]` entre si; T019 em diante depende deles
- Depois do Setup (Phase 1) pronto: US1 (Phase 2) e US2 (Phase 3) podem ser desenvolvidas em paralelo por devs diferentes, já que não compartilham arquivos
- US3 e US4 só podem começar depois que a US2 terminar (dependem do módulo/endpoint que ela cria)

---

## Parallel Example: User Story 1

```bash
# Testes da US1 em paralelo:
Task: "Teste unitário de busca de tenant em tests/unit/test_tenant_search.py"
Task: "Teste unitário do fallback de prompt padrão em tests/unit/test_prompt_manager_fallback.py"
Task: "Teste de integração de busca de tenant em tests/integration/test_tenant_search_api.py"
Task: "Teste de integração do overview de prompt/guardrail em tests/integration/test_tenant_prompt_overview_api.py"
```

## Parallel Example: User Story 2

```bash
# Domínio e ports da US2 em paralelo (antes dos use cases):
Task: "Entidade KnowledgeBaseDocument em modules/knowledge_base/domain/knowledge_base_document.py"
Task: "Ports KnowledgeBaseRepositoryPort/VectorStorePort em modules/knowledge_base/application/ports.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Phase 1 (Setup)
2. Completar Phase 2 (US1)
3. **PARAR e VALIDAR**: testar a busca de tenant + overview de prompt/guardrail de forma independente
4. Esse é o MVP entregável ao frontend para a parte de busca/visualização

### Entrega Incremental

1. Setup → base pronta
2. US1 → validar independentemente → MVP (busca + visualização de prompt/guardrail)
3. US2 → validar independentemente → base de conhecimento visível e editável
4. US3 → validar independentemente → exclusão de base de conhecimento
5. US4 → validar independentemente (sem código novo) → cadastro de base de conhecimento nova coberto
6. Phase 6 → isolamento multi-tenant confirmado, quickstart validado, documentação da API revisada

---

## Implementation Notes (post-execution)

- Todas as 33 tarefas foram implementadas e todos os 41 testes automatizados (17 pré-existentes + 24 novos) passam.
- T032 (`quickstart.md`) foi executado de ponta a ponta contra o Postgres local real (tenants `1234` e `petshop`), não só simulado — e pegou dois bugs reais que os testes com fakes não cobriam:
  1. `GET /api/v1/tenants?q=` redirecionava (307) por causa do trailing slash do FastAPI; corrigido registrando a rota como `@router.get("")` em vez de `@router.get("/")`.
  2. `GET /api/v1/prompt-manager/tenant/{id}` quebrava com `ResponseValidationError` porque `prompt_id` e os `id` dos guardrails vêm do Postgres como `uuid.UUID`, não `str`; corrigido convertendo explicitamente para string em `PromptManagerService.get_tenant_prompt_details`.
- Estado do banco local restaurado ao original ao final do smoke test (nenhuma base de conhecimento de teste deixada para trás em `1234` ou `petshop`).

## Notes

- `[P]` = arquivos diferentes, sem dependência entre as tarefas
- Cada user story deve ser completável e testável de forma independente, mesmo quando reaproveita código de uma story anterior (US3/US4 sobre a base da US2)
- Escrever os testes antes da implementação e confirmar que falham, por exigência do Princípio VI da constituição do projeto
- **Sem autenticação nesta lista de tarefas** — decisão explícita do usuário (ver `plan.md` Constitution Check / Complexity Tracking). `POST/PUT/DELETE /tenants/{id}`, todo o CRUD de `/prompt-manager/*` e agora também os endpoints novos desta feature continuam sem credencial alguma. Quando a feature de autenticação de admin (tabela de credenciais, hashing, login, JWT nos moldes de `/chat/init`) for construída, todos os endpoints tocados aqui devem ganhar `Depends(get_current_admin)` no mesmo passo.

# Tasks: Exclusão segura de tenant com desvínculo/exclusão em cascata de prompts e guardrails

**Input**: Design documents from `specs/006-tenant-delete-cascade/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluídos e obrigatórios — Princípio VI da constituição (Test-First Discipline) exige unit + integration tests para todo novo caso de uso/serviço, mesmo em módulo legado.

**Organization**: Tarefas agrupadas por user story (spec.md). US1/US2/US3 evoluem a MESMA função de decisão (`_compute_delete_plan`) em `modules/tenant/tenant_service.py`, então não são paralelizáveis entre si (mesmo arquivo, uma constrói sobre a outra) — mas cada uma entrega e testa um comportamento observável completo antes da próxima.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: US1, US2, US3, US4 (mapeiam para spec.md)

## Phase 1: Setup (Shared Infrastructure)

- [~] T001 **Revisto**: a convenção real do repo (`test_prompt_delete_guard_api.py`, `test_guardrail_delete_guard_api.py`) duplica pequenos fixtures `tenant_factory`/`_criar_tenant` por arquivo de teste, em vez de compartilhar via `conftest.py`. Seguido esse padrão existente em vez de introduzir uma abstração nova — fixture local escrito diretamente em `tests/integration/test_tenant_delete_cascade_api.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma user story pode começar antes desta fase.

- [X] T002 Criar migration `migrations/versions/0003_tenant_prompts_fk.py` (`Revises: 0002_backfill_tenant_links`): alterar `tenant_prompts.tenant_id` para `varchar(50)` e adicionar `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
- [X] T003 [P] Adicionar `get_prompts_linked_to_tenant_active(tenant_id)` em `modules/prompt_manager/prompt_manager_repository.py` (retorna prompts com vínculo ATIVO ao tenant, um por `node_type`)
- [X] T004 [P] Adicionar `get_guardrail_links_for_prompt(prompt_id)` em `modules/prompt_manager/prompt_manager_repository.py` (join direto via `prompt_guardrails`, incluindo a flag `is_global` de cada guardrail — sem misturar o `OR is_global=TRUE` de `get_guardrails_by_prompt`)
- [X] T005 Adicionar suporte a conexão externa em `modules/tenant/tenant_repository.py` (`TenantRepository`), para participar da mesma transação/conexão compartilhada da orquestração (research.md §3/§4)
- [X] T006 Implementar `_compute_delete_plan(tenant_id, conn)` em `modules/tenant/tenant_service.py`: função pura de decisão (sem escrita) que devolve `{prompts_to_delete, prompts_to_unlink_only, guardrails_to_delete, guardrails_to_unlink_only}` combinando T003, T004, `get_tenants_blocking_prompt` e `get_prompts_blocking_guardrail` já existentes (depende de T003, T004)

**Checkpoint**: fundação pronta — schema com FK, métodos de leitura e função de decisão disponíveis.

---

## Phase 3: User Story 1 - Excluir tenant com prompt e guardrail exclusivos (Priority: P1) 🎯 MVP

**Goal**: ao excluir um tenant cujo prompt e guardrail não são usados por mais ninguém, ambos são removidos de fato junto com o tenant.

**Independent Test**: criar tenant com prompt e guardrail exclusivos, excluir, confirmar que os três (tenant, prompt, guardrail) deixaram de existir.

### Tests for User Story 1 ⚠️

- [X] T007 [P] [US1] Unit test: `_compute_delete_plan` classifica prompt+guardrail exclusivos em `prompts_to_delete`/`guardrails_to_delete` em `tests/unit/test_tenant_delete_cascade.py`
- [X] T008 [P] [US1] Integration test: `DELETE /api/v1/tenants/{id}` remove tenant, prompt exclusivo e guardrail exclusivo em `tests/integration/test_tenant_delete_cascade_api.py`

### Implementation for User Story 1

- [X] T009 [US1] Implementar `delete_tenant_cascade(tenant_id)` em `modules/tenant/tenant_service.py`: abre 1 conexão, inicia `conn.transaction()`, chama `_compute_delete_plan`, exclui `guardrails_to_delete` e `prompts_to_delete` (reaproveitando `PromptManagerRepository.delete_guardrail`/`delete_prompt` via a factory de conexão compartilhada), depois exclui o tenant; devolve `None` se o tenant não existir (depende de T005, T006)
- [X] T010 [US1] Substituir a chamada em `DELETE /tenants/{tenant_id}` (`app/api/v1/endpoints/tenant.py`) de `tenant_service.delete_tenant` para `tenant_service.delete_tenant_cascade` (depende de T009)

**Checkpoint**: US1 completo e testável — tenants com vínculos exclusivos são limpos corretamente; endpoint já está no ar.

---

## Phase 4: User Story 2 - Excluir tenant com prompt compartilhado (Priority: P1)

**Goal**: excluir um tenant cujo prompt também serve outro(s) tenant(s) preserva o prompt, removendo só o vínculo deste tenant.

**Independent Test**: vincular o mesmo prompt a dois tenants, excluir um deles, confirmar que o prompt continua íntegro e ainda vinculado ao outro tenant.

### Tests for User Story 2 ⚠️

- [X] T011 [P] [US2] Unit test: `_compute_delete_plan` classifica um prompt com outro tenant ativo em `prompts_to_unlink_only` (nunca em `prompts_to_delete`) em `tests/unit/test_tenant_delete_cascade.py`
- [X] T012 [P] [US2] Integration test: excluir um de dois tenants que compartilham um prompt preserva o prompt e o vínculo do tenant remanescente em `tests/integration/test_tenant_delete_cascade_api.py`

### Implementation for User Story 2

- [X] T013 [US2] Ajustar `delete_tenant_cascade` para NÃO excluir prompts classificados em `prompts_to_unlink_only` — a própria linha de `tenant_prompts` deste tenant desaparece sozinha via a FK de T002 ao excluir o tenant (`modules/tenant/tenant_service.py`, depende de T009)

**Checkpoint**: US1 + US2 completos — prompts compartilhados nunca são perdidos.

---

## Phase 5: User Story 3 - Excluir tenant com guardrail global ou compartilhado (Priority: P1)

**Goal**: um guardrail marcado `is_global` ou vinculado a prompt de outro tenant é preservado, mesmo que o prompt do tenant excluído seja apagado.

**Independent Test**: marcar um guardrail como global (ou vinculá-lo a um prompt de outro tenant), excluir um tenant cujo prompt exclusivo usa esse guardrail, confirmar que o guardrail continua existindo.

### Tests for User Story 3 ⚠️

- [X] T014 [P] [US3] Unit test: guardrail `is_global=TRUE` vinculado a um prompt exclusivo (que será excluído) fica em `guardrails_to_unlink_only`, nunca em `guardrails_to_delete`, em `tests/unit/test_tenant_delete_cascade.py`
- [X] T015 [P] [US3] Unit test: guardrail vinculado a prompts de dois tenants diferentes (nenhum global) fica em `guardrails_to_unlink_only` em `tests/unit/test_tenant_delete_cascade.py`
- [X] T016 [P] [US3] Integration test: excluir um tenant cujo prompt exclusivo tem um guardrail global preserva o guardrail em `tests/integration/test_tenant_delete_cascade_api.py`

### Implementation for User Story 3

- [X] T017 [US3] Ajustar `_compute_delete_plan` para checar `is_global` e `get_prompts_blocking_guardrail` (excluindo o próprio prompt sendo avaliado) ANTES de classificar um guardrail em `guardrails_to_delete` (`modules/tenant/tenant_service.py`, depende de T006, T009)

**Checkpoint**: US1 + US2 + US3 completos — `DELETE /tenants/{id}` já cobre os 3 cenários da spec por completo.

---

## Phase 6: User Story 4 - Consultar o impacto antes de confirmar a exclusão (Priority: P2)

**Goal**: expor a mesma lógica de decisão em modo somente-leitura, para uma interface administrativa mostrar o impacto antes de confirmar.

**Independent Test**: consultar o impacto de um tenant com combinação mista (prompt exclusivo + guardrail global), confirmar que a resposta bate com o resultado real de uma exclusão em seguida.

### Tests for User Story 4 ⚠️

- [X] T018 [P] [US4] Integration test: `GET /api/v1/tenants/{id}/delete-impact` devolve exatamente a mesma classificação que o `DELETE` subsequente produz, para um tenant com prompt exclusivo + guardrail global, em `tests/integration/test_tenant_delete_cascade_api.py`

### Implementation for User Story 4

- [X] T019 [P] [US4] Adicionar schemas `TenantDeleteImpactResponse`, `PromptImpactItem`, `GuardrailImpactItem` em `app/schemas/tenant.py`
- [X] T020 [US4] Implementar `get_delete_impact(tenant_id)` em `modules/tenant/tenant_service.py`, reaproveitando `_compute_delete_plan` em modo somente-leitura (conexão própria, sem transação de escrita) (depende de T006, T019)
- [X] T021 [US4] Adicionar `GET /tenants/{tenant_id}/delete-impact` em `app/api/v1/endpoints/tenant.py` (depende de T020)

**Checkpoint**: feature completa — exclusão em cascata + pré-visualização de impacto, ambos funcionais.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [P] Integration test: `DELETE` e `GET delete-impact` devolvem `404` para tenant inexistente, sem nenhum efeito colateral, em `tests/integration/test_tenant_delete_cascade_api.py`
- [X] T023 [P] Unit test: uma falha simulada no meio da orquestração (ex.: exception forçada entre a exclusão do guardrail e a do prompt) não deixa nenhuma alteração parcial persistida (rollback da transação) em `tests/unit/test_tenant_delete_cascade.py`
- [ ] T024 Executar os 4 cenários de `quickstart.md` manualmente contra a API local para validação end-to-end
- [X] T025 Revisar o diff contra a Constituição (Princípio III — Legacy Migration Policy — e Princípio VI — cobertura de testes) antes de abrir o PR — revisado: `TenantRepository`/`TenantService` reaproveitam métodos públicos de `PromptManagerRepository` (nenhum SQL novo fora dos repositórios), e todo código novo tem teste unitário (fake) + integração (banco real + contrato HTTP)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup — BLOQUEIA todas as user stories
- **US1 (Phase 3)**: depende só do Foundational — é o MVP
- **US2 (Phase 4)**: depende de US1 (mesma função `_compute_delete_plan`/`delete_tenant_cascade` sendo estendida, T013 depende de T009)
- **US3 (Phase 5)**: depende de US1 (T017 depende de T009); independente de US2
- **US4 (Phase 6)**: depende só do Foundational (T006); pode ser feita em paralelo com US2/US3 por outro desenvolvedor, já que toca arquivos distintos até T020 tocar `tenant_service.py`
- **Polish (Phase 7)**: depende de US1+US2+US3 (T023) e de todas as stories desejadas estarem prontas (T024)

### Observação sobre paralelismo

Ao contrário do padrão usual de user stories 100% independentes, US1/US2/US3 aqui **compartilham o mesmo arquivo e a mesma função de decisão** (`_compute_delete_plan` / `delete_tenant_cascade` em `modules/tenant/tenant_service.py`) porque um único tenant pode, na vida real, disparar os três ramos simultaneamente (um prompt exclusivo E um prompt compartilhado, por exemplo). Por isso a implementação de US2 e US3 (T013, T017) não é `[P]` entre si nem com US1 — são extensões sequenciais da mesma lógica. US4, por tocar principalmente arquivos novos (`app/schemas/tenant.py`, endpoint novo), pode avançar em paralelo.

### Parallel Opportunities

- T003 e T004 (métodos novos em `prompt_manager_repository.py`) — arquivos/métodos independentes
- Testes marcados `[P]` dentro de cada fase (arquivos de teste diferentes ou casos independentes no mesmo arquivo)
- T019 (schemas) pode avançar em paralelo com o restante de US2/US3

---

## Parallel Example: Foundational

```bash
Task: "Adicionar get_prompts_linked_to_tenant_active(tenant_id) em modules/prompt_manager/prompt_manager_repository.py"
Task: "Adicionar get_guardrail_links_for_prompt(prompt_id) em modules/prompt_manager/prompt_manager_repository.py"
```

## Parallel Example: User Story 1

```bash
Task: "Unit test _compute_delete_plan (exclusivo) em tests/unit/test_tenant_delete_cascade.py"
Task: "Integration test DELETE cascata (exclusivo) em tests/integration/test_tenant_delete_cascade_api.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup → Foundational (T001–T006)
2. User Story 1 (T007–T010) — **MVP**: tenants com vínculos exclusivos já são limpos corretamente
3. Validar: rodar `pytest tests/unit -k tenant_delete_cascade` e `pytest tests/integration -k tenant_delete`

### Incremental Delivery

1. Foundational pronta
2. US1 → valida cenário exclusivo → já pode ser demonstrado
3. US2 → valida preservação de prompt compartilhado
4. US3 → valida preservação de guardrail global/compartilhado (`DELETE /tenants/{id}` agora cobre a spec inteira)
5. US4 → adiciona a pré-visualização de impacto para o consumidor (EDI-46)
6. Polish → casos de erro, atomicidade, validação manual, revisão de conformidade

---

## Notes

- Testes são obrigatórios nesta feature (Princípio VI), não opcionais — escreva-os ANTES da implementação de cada tarefa e confirme que falham primeiro.
- `_compute_delete_plan` é o único lugar onde a regra de decisão vive — tanto `delete_tenant_cascade` (escrita) quanto `get_delete_impact` (leitura) chamam essa mesma função, garantindo que o preview nunca divirja do resultado real (SC-002).
- Commit após cada tarefa ou grupo lógico de tarefas.

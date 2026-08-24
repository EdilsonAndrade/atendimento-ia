# Tasks: Rastreamento de custo de token por conversa e tenant

**Input**: Design documents from `specs/008-token-cost-tracking/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Incluídos e obrigatórios — Princípio VI da constituição, sem grace period (módulo novo).

**Organization**: US1 é o núcleo (captura + persistência); US2 é sobre os campos que viabilizam agregação/purga, já nascem junto de US1 no mesmo registro — por isso a implementação de US2 é, na prática, validação de que os campos de US1 sustentam as duas acceptance scenarios.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Criar estrutura de diretórios `modules/token_usage/{domain,application,infrastructure}/` com `__init__.py` em cada nível

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma user story pode começar antes desta fase.

- [X] T002 Criar migration `migrations/versions/0007_chat_token_usage.py` (`Revises: 0006_chat_thread_summaries`): `CREATE TABLE chat_token_usage` conforme `data-model.md` + índices `(base_thread_id)` e `(tenant_id, created_at)`
- [X] T003 [P] Implementar `TokenUsageRecord` (dataclass) e `calculate_cost_usd(input_tokens, output_tokens, price_per_1k_input, price_per_1k_output) -> Decimal` em `modules/token_usage/domain/token_usage_record.py` — sem import de framework
- [X] T004 [P] Definir `Protocol TokenUsageRepository` (método `save(record: TokenUsageRecord) -> None`) em `modules/token_usage/application/ports.py`

**Checkpoint**: schema e Domain layer prontos.

---

## Phase 3: User Story 1 - Cada chamada ao LLM tem seu custo registrado automaticamente (Priority: P1) 🎯 MVP

**Goal**: toda chamada real ao LLM feita pelo agente gera um registro de custo com tenant, conversa e nó corretos, sem afetar a resposta ao cliente em caso de falha.

**Independent Test**: enviar mensagem que aciona roteador + operacional, confirmar 2+ registros com `node_type` distintos e dados corretos.

### Tests for User Story 1 ⚠️

- [X] T005 [P] [US1] Unit test: `calculate_cost_usd` calcula corretamente para valores conhecidos (incluindo zero tokens) em `tests/unit/test_token_usage_domain.py`
- [X] T006 [P] [US1] Unit test: `RecordTokenUsageUseCase.execute(...)` monta um `TokenUsageRecord` correto a partir de uma resposta com `usage_metadata` e chama `repository.save` (repositório fake) em `tests/unit/test_record_token_usage_use_case.py`
- [X] T007 [P] [US1] Unit test: `RecordTokenUsageUseCase.execute(...)` com resposta SEM `usage_metadata` (ou incompleto) não lança exceção e não chama `repository.save` (ou chama com zeros — decidir na implementação) em `tests/unit/test_record_token_usage_use_case.py`
- [X] T008 [P] [US1] Unit test: uma falha do `repository.save` (fake que lança exceção) não propaga para fora de `RecordTokenUsageUseCase.execute(...)` (FR-006) em `tests/unit/test_record_token_usage_use_case.py`

### Implementation for User Story 1

- [X] T009 [US1] Implementar `RecordTokenUsageUseCase` em `modules/token_usage/application/record_token_usage.py`: recebe a `AIMessage` de resposta + `tenant_id`/`base_thread_id`/`thread_id`/`node_type`, extrai `usage_metadata`, calcula custo (preço via env vars `LLM_PRICE_PER_1K_INPUT_TOKENS_USD`/`LLM_PRICE_PER_1K_OUTPUT_TOKENS_USD`), monta `TokenUsageRecord`, chama `repository.save` protegido por try/except (depende de T003, T004)
- [X] T010 [US1] Implementar `PostgresTokenUsageRepository` em `modules/token_usage/infrastructure/postgres_token_usage_repository.py`, implementando `TokenUsageRepository` (depende de T002, T004)
- [X] T011 [US1] Adicionar helper `record_llm_usage(response, tenant_id, base_thread_id, thread_id, node_type)` em `modules/ia/agent_graph.py`, instanciando `RecordTokenUsageUseCase(PostgresTokenUsageRepository())` uma vez no nível do módulo e delegando a chamada (depende de T009, T010)
- [X] T012 [US1] Chamar `record_llm_usage(...)` logo após `resposta = llm.invoke(mensagens_para_ia)` em `routing_agent` (`node_type="routing_agent"`) (depende de T011)
- [X] T013 [P] [US1] Chamar `record_llm_usage(...)` logo após `resposta_ia = llm.invoke(prompt_final)` em `institutional_node` (`node_type="institutional_node"`) (depende de T011)
- [X] T014 [P] [US1] Chamar `record_llm_usage(...)` logo após `resposta_ia = llm.invoke(mensagens_para_ia)` em `chitchat_node` (`node_type="chitchat_node"`) (depende de T011)
- [X] T015 [US1] Chamar `record_llm_usage(...)` logo após as DUAS chamadas em `operational_node` (`llm_dynamic.invoke` e o retry `llm_forcado.invoke`), ambas com `node_type="operational_node"` (depende de T011)
- [ ] T016 [US1] Integration test: `PostgresTokenUsageRepository.save` persiste corretamente contra um Postgres real e o registro é lido de volta com os mesmos valores em `tests/integration/test_postgres_token_usage_repository.py` (depende de T010)
- [ ] T017 [US1] Integration test: enviar uma mensagem através do grafo real (ou invocar diretamente `routing_agent`/`operational_node` com um `tenant_id`/`base_thread_id` de teste) e confirmar que `chat_token_usage` recebe registros com `node_type` correspondentes em `tests/integration/test_agent_graph_records_token_usage.py` (depende de T012–T015)

**Checkpoint**: US1 completo — MVP funcional, todo o rastreamento de custo operando.

---

## Phase 4: User Story 2 - Custos ficam agrupáveis por conversa/tenant, prontos para purga futura (Priority: P2)

**Goal**: confirmar que os campos persistidos em US1 sustentam agregação por conversa/tenant e purga futura por `created_at`.

**Independent Test**: gerar registros de duas conversas/tenants diferentes, somar por `base_thread_id` e por `tenant_id`, confirmar `created_at` preenchido em todos.

### Tests for User Story 2 ⚠️

- [ ] T018 [P] [US2] Integration test: soma de `estimated_cost_usd` agrupada por `base_thread_id` bate com a soma manual dos registros inseridos; idem agrupado por `tenant_id`, em `tests/integration/test_postgres_token_usage_repository.py` (depende de T010, T016)
- [ ] T019 [P] [US2] Unit/integration test: todo `TokenUsageRecord` persistido tem `created_at` não nulo (verificar `DEFAULT NOW()` da migration ou preenchimento explícito no repositório)

**Checkpoint**: US2 completo — feature inteira entregue.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T020 [P] Documentar `LLM_PRICE_PER_1K_INPUT_TOKENS_USD`/`LLM_PRICE_PER_1K_OUTPUT_TOKENS_USD` no `.env` local (placeholder) com nota de que o valor real depende do plano contratado
- [X] T021 Revisar o diff contra a Constituição (Princípio III — Clean Architecture completa por ser módulo novo, Princípio V — sem bloqueio de latência, Princípio VI — cobertura de testes) antes de abrir o PR
- [ ] T022 Rodar a suíte de testes localmente e enviar 2–3 mensagens reais pela API local, confirmando registros em `chat_token_usage` via consulta SQL manual

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup — BLOQUEIA US1
- **US1 (Phase 3)**: depende do Foundational — é o MVP
- **US2 (Phase 4)**: depende de US1 (mesmos registros, só valida agregação/retenção sobre eles)
- **Polish (Phase 5)**: depende de US1 + US2

### Parallel Opportunities

- T003 e T004 (Foundational) — arquivos independentes
- T005–T008 (testes de US1) são `[P]` entre si
- T013 e T014 (institutional/chitchat) são `[P]` entre si — arquivos/pontos diferentes dentro do mesmo `agent_graph.py`, mas funções distintas sem conflito de linha

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup → Foundational (T001–T004)
2. User Story 1 (T005–T017) — **MVP**: rastreamento de custo funcionando em todos os 4 nós
3. Validar: `pytest tests/unit -k token_usage` e `pytest tests/integration -k token_usage`

### Incremental Delivery

1. Foundational pronta
2. US1 → captura e persistência completas → já entrega o valor central do ticket
3. US2 → validação de que os dados sustentam agregação e purga futura
4. Polish → documentação de preço, revisão de conformidade, validação manual

---

## Notes

- Testes são obrigatórios nesta feature (Princípio VI, sem grace period) — escreva-os ANTES da implementação de cada tarefa e confirme que falham primeiro.
- `RecordTokenUsageUseCase` é o único lugar onde a regra de "nunca afetar a resposta ao cliente" (FR-006) vive — todo ponto de chamada em `agent_graph.py` só invoca esse caso de uso, nunca a Infrastructure diretamente.
- Commit após cada tarefa ou grupo lógico de tarefas.

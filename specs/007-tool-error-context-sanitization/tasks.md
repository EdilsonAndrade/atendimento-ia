# Tasks: Sanitização do contexto de conversa enviado ao LLM

**Input**: Design documents from `specs/007-tool-error-context-sanitization/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Incluídos e obrigatórios — Princípio VI da constituição (Test-First Discipline) exige unit + integration tests para todo código novo, mesmo em módulo legado.

**Organization**: Tarefas agrupadas por user story (spec.md). US1 é o MVP (causa raiz do bug relatado); US2/US3 são independentes entre si e de US1; US4 depende da migration da fase Foundational e é a mais isolada (arquivo/tabela próprios).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: US1, US2, US3, US4 (mapeiam para spec.md)

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Confirmar convenção de teste do repo (sem `conftest.py` compartilhado até então — ver EDI-45) e criar `tests/unit/` e `tests/integration/` se ainda não existirem no diretório de trabalho atual

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: nenhuma user story pode começar antes desta fase.

- [X] T002 Criar decorator `safe_tool_result(fallback: str)` em `util/tool_error_handling.py`: captura `Exception`, loga (`logging.getLogger(__name__).error`) mensagem original + tipo da exceção + `tenant_id`/thread id quando presentes nos kwargs da chamada decorada, devolve `fallback` no lugar de propagar
- [X] T003 [P] Criar migration `migrations/versions/0006_chat_thread_summaries.py` (`Revises: 0005_clean_global_guardrail`): `CREATE TABLE chat_thread_summaries` conforme `data-model.md` (colunas `id`, `base_thread_id`, `resumo`, `fatos_estruturados jsonb`, `sessao_thread_id`, `created_at`) + índice `(base_thread_id, created_at DESC)`

**Checkpoint**: decorator de sanitização e schema de resumo disponíveis.

---

## Phase 3: User Story 1 - Cliente não recebe nem contamina a conversa com erro técnico interno (Priority: P1) 🎯 MVP

**Goal**: exceção técnica de qualquer tool do agendamento nunca mais chega crua ao LLM/cliente; erro completo vai para o log.

**Independent Test**: forçar falha em uma tool (ex.: monkeypatch levantando exceção), confirmar `ToolMessage` genérica, log completo, e resposta coerente à pergunta seguinte do cliente.

### Tests for User Story 1 ⚠️

- [X] T004 [P] [US1] Unit test: `safe_tool_result` captura exceção, loga com tenant_id, devolve fallback (sem propagar) em `tests/unit/test_tool_error_handling.py`

### Implementation for User Story 1

- [X] T005 [US1] Aplicar `@safe_tool_result` (com fallback específico) em `confirmar_agendamento`/`create_google_calendar_event`/`save_local_booking` em `modules/agendamento/booking_tools.py` (depende de T002)
- [X] T006 [P] [US1] Aplicar `@safe_tool_result` em `consultar_horarios_disponiveis` em `modules/agendamento/agenda_tool.py` (depende de T002)
- [X] T007 [P] [US1] Aplicar `@safe_tool_result` em `cancelar_agendamento` em `modules/agendamento/delete_agenda_tool.py` (depende de T002)
- [X] T008 [P] [US1] Aplicar `@safe_tool_result` em `consulta_agendamento` em `modules/agendamento/consulta_agenda_tool.py` (depende de T002)
- [X] T009 [P] [US1] Aplicar `@safe_tool_result` nas 3 tools em `modules/agendamento/tools/google_calendario/` (`agenda_tool.py`, `consulta_agenda_tool.py`, `delete_agenda_tool.py`) (depende de T002)
- [X] T010 [US1] Integration test: monkeypatch forçando exceção em uma tool durante uma conversa via `TestClient`, confirmar resposta ao cliente sem texto de exceção e próxima pergunta respondida normalmente, em `tests/integration/test_chat_tool_failure_sanitized.py` (depende de T005–T009)

**Checkpoint**: US1 completo — causa raiz do bug relatado corrigida; pode ser entregue isoladamente.

---

## Phase 4: User Story 2 - Conversas mais longas mantêm contexto relevante (Priority: P2)

**Goal**: janela de histórico enviada ao LLM passa de 50 para 95 mensagens, sem alterar o comportamento de corte seguro existente.

**Independent Test**: simular histórico com >50 e <=95 mensagens, confirmar que todas entram no prompt; com >95, confirmar corte nas últimas 95.

### Tests for User Story 2 ⚠️

- [X] T011 [P] [US2] Unit test: `trim_messages` com 95 mensagens preserva todas; com mais de 95, corta mantendo `start_on="human"`, em `tests/unit/test_agent_graph_trim_window.py`

### Implementation for User Story 2

- [X] T012 [US2] Alterar `max_tokens=50` para `max_tokens=95` em `trim_messages` (`modules/ia/agent_graph.py`, linha ~539)

**Checkpoint**: US2 completo — independente de US1/US3/US4.

---

## Phase 5: User Story 3 - Tipagem de retorno consistente nas tools (Priority: P2)

**Goal**: toda função `@tool` do agente de agendamento declara `-> str` explicitamente.

**Independent Test**: inspeção/checagem de tipos confirma `-> str` em todas as funções `@tool`.

### Implementation for User Story 3

- [X] T013 [P] [US3] Adicionar `-> str` em `confirmar_agendamento` (`booking_tools.py`) e `consultar_horarios_disponiveis` (`agenda_tool.py`)
- [X] T014 [P] [US3] Adicionar `-> str` em `cancelar_agendamento` (`delete_agenda_tool.py`) e `consulta_agendamento` (`consulta_agenda_tool.py`)
- [X] T015 [P] [US3] Adicionar `-> str` nas funções `build_consulta_tool`/`build_delete_tool` (`tools/google_calendario/`) e nas tools internas que retornam sem anotação

**Checkpoint**: US3 completo — nenhuma mudança de comportamento, só tipagem.

---

## Phase 6: User Story 4 - Resumo e fatos estruturados da sessão (Priority: P3)

**Goal**: sessão expirada por inatividade gera resumo + fatos estruturados em background, disponíveis para a próxima sessão do mesmo `base_thread_id`.

**Independent Test**: encerrar sessão com nome/interesse identificáveis, confirmar resumo/fatos gravados e disponíveis; sessão sem informação relevante não gera fatos inventados.

### Tests for User Story 4 ⚠️

- [X] T016 [P] [US4] Unit test: geração de fatos estruturados não inventa campos ausentes (FR-011) em `tests/unit/test_thread_session_summary.py`
- [X] T017 [P] [US4] Unit test: falha simulada na geração do resumo não impede a expiração/nova sessão (FR-010) em `tests/unit/test_thread_session_summary.py`

### Implementation for User Story 4

- [X] T018 [US4] Implementar `generate_and_store_session_summary(base_thread_id, expired_active_thread_id)` em `modules/ia/thread_session.py`: lê o histórico da sessão expirada via checkpointer, chama o LLM (chamada leve) para resumo + fatos estruturados, persiste em `chat_thread_summaries` (depende de T003)
- [X] T019 [US4] Ajustar `resolve_active_thread_id` para devolver também o `active_thread_id` anterior quando detectar expiração, sem alterar sua assinatura de uso atual (retorno compatível) (depende de T018)
- [X] T020 [US4] No endpoint de chat (`app/api/v1/endpoints/chat.py`), aceitar `BackgroundTasks` e agendar `generate_and_store_session_summary` quando `resolve_active_thread_id` sinalizar expiração (depende de T019)
- [X] T021 [US4] Implementar `get_latest_session_summary(base_thread_id)` em `modules/ia/thread_session.py` e injetar no `system_prompt` do `operational_node` (`modules/ia/agent_graph.py`), no mesmo padrão de `build_customer_context_block` (depende de T018)

**Checkpoint**: US4 completo — feature inteira entregue.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [P] Revisar o diff contra a Constituição (Princípio III — Legacy Migration Policy, Princípio V — async, Princípio VI — cobertura de testes) antes de abrir o PR
- [ ] T023 Rodar a suíte de testes localmente e validar manualmente um cenário de falha forçada + expiração de sessão contra a API local

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup — BLOQUEIA US1 e US4 (US2/US3 não dependem do decorator nem da migration)
- **US1 (Phase 3)**: depende do Foundational (T002) — é o MVP
- **US2 (Phase 4)**: independente de US1/US3/US4 — pode avançar em paralelo
- **US3 (Phase 5)**: independente de US1/US2/US4 — pode avançar em paralelo
- **US4 (Phase 6)**: depende do Foundational (T003, migration) — independente de US1/US2/US3
- **Polish (Phase 7)**: depende de todas as stories desejadas estarem prontas

### Parallel Opportunities

- T002 e T003 (Foundational) — arquivos/tabelas independentes
- US2 e US3 podem ser feitas em paralelo com US1/US4 por outro desenvolvedor (arquivos praticamente sem sobreposição, exceto T012 tocar `agent_graph.py`, também tocado por T021 — coordenar ordem de merge nesse arquivo)
- T005–T009 (US1) são `[P]` entre si — arquivos de tool diferentes
- T013–T015 (US3) são `[P]` entre si — arquivos diferentes

---

## Parallel Example: User Story 1

```bash
Task: "Aplicar @safe_tool_result em modules/agendamento/agenda_tool.py"
Task: "Aplicar @safe_tool_result em modules/agendamento/delete_agenda_tool.py"
Task: "Aplicar @safe_tool_result em modules/agendamento/consulta_agenda_tool.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup → Foundational (T001–T003)
2. User Story 1 (T004–T010) — **MVP**: causa raiz do bug corrigida
3. Validar: `pytest tests/unit -k tool_error_handling` e `pytest tests/integration -k tool_failure_sanitized`

### Incremental Delivery

1. Foundational pronta
2. US1 → corrige a causa raiz → já pode ser demonstrado/entregue
3. US2 → janela maior, sem risco (mudança de constante)
4. US3 → tipagem, sem risco (sem mudança de comportamento)
5. US4 → Camada 2 de memória, entrega mais complexa, isolada em arquivo/tabela próprios
6. Polish → revisão de conformidade e validação manual

---

## Notes

- Testes são obrigatórios nesta feature (Princípio VI) — escreva-os ANTES da implementação de cada tarefa e confirme que falham primeiro.
- `safe_tool_result` é o único lugar onde a regra de sanitização vive — qualquer tool nova do agendamento deve usá-lo por padrão a partir de agora.
- Commit após cada tarefa ou grupo lógico de tarefas.

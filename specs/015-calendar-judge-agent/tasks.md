# Tasks: calendar_judge_agent — verificar agendamento real antes de confirmar ao cliente

**Input**: Design documents from `/specs/015-calendar-judge-agent/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Incluídos, seguindo o mesmo padrão já usado em `modules/ia/test_agent_graph.py` para os guardrails do EDI-61 (mock de `llm`/`calendar_service`/`tenant_service`, sem infraestrutura de teste nova).

**Organization**: Tarefas agrupadas pelas 3 User Stories do spec.md (P1, P2, P3), cada uma independentemente implementável e testável.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes ou trechos independentes do mesmo arquivo, sem dependência de tarefa incompleta)
- **[Story]**: US1, US2 ou US3 (mapeiam para as User Stories do spec.md)

## Path Conventions

Projeto único (backend), sem `src/`/`frontend/` — segue a estrutura real já existente (ver plan.md > Project Structure). Toda a mudança fica em `modules/ia/agent_graph.py` e `modules/ia/test_agent_graph.py`.

---

## Phase 1: Setup

- [ ] T001 Rodar a suíte de testes existente como baseline (`pytest modules/ia/test_agent_graph.py -v`) e confirmar que todos passam antes de iniciar as mudanças — **pendente pelo usuário**: ambiente local não tem `langchain_core`/dependências instaladas fora do container (regra do projeto: agente não sobe container/roda testes sozinho); comando abaixo em Phase 6

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Núcleo do `calendar_judge_agent` compartilhado pelas 3 User Stories — nenhuma story pode ser testada isoladamente sem isso.

**⚠️ CRITICAL**: Nenhuma User Story pode começar até esta fase terminar.

- [X] T002 Corrigir `BOOKING_CONFIRMATION_CLAIM_PATTERN` em `modules/ia/agent_graph.py` para cobrir a frase real do incidente EDI-72 ("agendamento **foi** confirmado") e variações comuns ("confirmado/reservado com sucesso"), sem quebrar os casos já cobertos hoje (Decisão 1 do research.md) — inclui também padrões de cancelamento/reagendamento ("cancelamento confirmado", "foi cancelado com sucesso", "reagendamento confirmado", "foi reagendado"), necessários porque US2 estende a cobertura a esses dois fluxos
- [X] T003 [P] Adicionar campos `judge_redirect_count: int` **e `judge_verdict: str`** ao `TypedDict AgentState` em `modules/ia/agent_graph.py` — desvio do plano original: `judge_verdict` foi necessário porque o roteamento condicional do LangGraph só pode decidir o próximo nó a partir de um valor gravado no `state` pelo nó anterior (um router não recomputa/chama a API do Calendar de novo); `_post_judge_router` lê esse campo em vez de re-executar a verificação
- [X] T004 Implementar `_extrair_periodo_alegado(texto_resposta, tabela_calendario_str, qual="principal"|"antigo"|"novo")` em `modules/ia/agent_graph.py`: LLM call curto (`temperature=0`, saída estruturada via `_PeriodoAlegado`/`with_structured_output`) que resolve o período ISO alegado no texto suspeito usando a tabela `CALENDAR REFERENCE` já calculada por `get_tabela_dias` (Decisão 2 do research.md); parâmetro `qual` permite extrair separadamente o horário antigo/novo de um reagendamento (reaproveitado por T013); retorna `(None, None)` em caso de falha de extração
- [X] T005 Implementar `_verificar_acao_calendario(tenant_id, customer_phone, start_time, end_time, action_type, thread_id="unknown")` em `modules/ia/agent_graph.py`: reaproveita o mesmo backend de `calendar_service.list_events` usado por `consultar_agenda` (query=telefone) e interpreta presença/ausência do evento conforme `action_type` ("create" → presente = confirmado; "cancel" → ausente = confirmado); retorna `"confirmed"`/`"not_confirmed"`/`"extraction_failed"` — desvio: usa `tenant_service`/`calendar_service` globais do módulo (mesmo padrão já usado pelas tools em `modules/agendamento/tools/google_calendario/`) em vez de recebê-los como parâmetro
- [X] T006 Implementar o nó `calendar_judge_agent(state, config)` em `modules/ia/agent_graph.py`: reaproveita `_tipo_acao_alegada` (novo helper, T002) para decidir `action_type`, obtém telefone via `extract_customer_profile`, obtém período via T004 (duas chamadas no caso de reagendamento — antigo/novo), chama T005, loga com tag `[CALENDAR_JUDGE]` (tenant_id, thread_id, action_type, resultado, redirect_count) via `get_logger`, e devolve `judge_verdict` (`"confirmed"`/`"redirect"`/`"blocked"`) + `judge_redirect_count` atualizado; ao bloquear (limite atingido), substitui a resposta pelo fallback "Desculpa, tive um problema..."
- [X] T007 Registrado `calendar_judge_agent` no grafo (`builder.add_node(...)`) e trocado, em `modules/ia/agent_graph.py`: (a) a saída de `operational_node` passa por `_operational_output_router` (substitui o `tools_condition` puro: quando não há tool_calls pendentes E o padrão de confirmação sem lastro dispara, vai para `calendar_judge_agent` em vez de END direto — o retry `tool_choice="required"` interno de `operational_node` continua intacto como primeira linha de defesa), e (b) `_make_pre_end_guardrail_router` (institutional_node/chitchat_node, EDI-61) agora redireciona para `"calendar_judge_agent"` em vez de `"operational_node"` direto; `_post_judge_router` decide entre `operational_node` (redirect) e END (confirmed/blocked) lendo `judge_verdict` (depende de T002-T006). **Correção de rastreabilidade** (levantada pelo usuário em revisão): `_operational_output_router` inicialmente não logava nada ao disparar o juiz — só `_make_pre_end_guardrail_router` (institutional/chitchat) tinha o log `[CALENDAR_GUARDRAIL_REDIRECT]` herdado do EDI-61. Adicionado o mesmo log (tag, tenant_id, thread_id, motivo, trecho) em `_operational_output_router` para que o disparo do juiz fique grepável com uma única tag independente de qual nó chamou; coberto por `OperationalOutputRouterTest.test_logs_calendar_guardrail_redirect_when_routing_to_judge`. O log do **resultado** (incluindo `resultado=confirmed`) já existia desde o T006, dentro do próprio `calendar_judge_agent`.

**Checkpoint**: Núcleo do juiz pronto e ligado ao grafo — as User Stories a seguir só adicionam cobertura de teste e o caso de reagendamento.

---

## Phase 3: User Story 1 - Cliente nunca recebe confirmação de criação que não existe (Priority: P1) 🎯 MVP

**Goal**: Uma resposta de confirmação de **criação** de agendamento sem `tool_calls` no turno só chega ao cliente depois do `calendar_judge_agent` verificar, contra o Google Calendar real, que o evento existe para aquele tenant + telefone + período.

**Independent Test**: Forçar uma resposta de confirmação de criação sem `tool_calls` (mock) e verificar que o juiz consulta `calendar_service.list_events` e decide corretamente entre liberar ou redirecionar, inclusive quando o evento encontrado pertence a outro cliente do mesmo tenant.

### Tests for User Story 1

- [X] T008 [P] [US1] Teste unitário: resposta de confirmação de **criação** sem `tool_calls`, evento **não encontrado** na consulta → juiz redireciona (`judge_verdict="redirect"`), em `modules/ia/test_agent_graph.py` (`CalendarJudgeAgentTest.test_redirects_when_event_not_found`)
- [X] T009 [P] [US1] Teste unitário: mesma situação, evento **encontrado** (tenant + telefone + período batendo) → `judge_verdict="confirmed"`, em `modules/ia/test_agent_graph.py` (`test_confirms_when_event_found_for_same_phone`)
- [X] T010 [P] [US1] Teste unitário: evento encontrado pertence a **outro telefone** no mesmo tenant/período (Cliente A vs Cliente B) → juiz não aceita como prova, `judge_verdict="redirect"` (isolamento entre clientes — spec.md User Story 1, cenário 3), em `modules/ia/test_agent_graph.py` (`test_does_not_accept_another_customers_event_as_proof`)
- [X] T011 [P] [US1] Teste unitário: `BOOKING_CONFIRMATION_CLAIM_PATTERN` corrigido (T002) captura a frase real do incidente "Seu agendamento foi confirmado com sucesso!", em `modules/ia/test_agent_graph.py` (`RespostaSemLastroDeToolTest.test_confirmation_claim_matches_real_incident_phrasing`)

**Checkpoint**: User Story 1 completa e testável isoladamente — MVP que fecha o incidente relatado no EDI-72.

---

## Phase 4: User Story 2 - Verificação cobre cancelamento e reagendamento (Priority: P2)

**Goal**: Confirmações de **cancelamento** e **reagendamento** sem `tool_calls` também passam pelo juiz, com a condição de verificação correta para cada caso.

**Independent Test**: Forçar respostas de "cancelamento confirmado" e "reagendamento confirmado" sem `tool_calls` e verificar que o juiz consulta a condição certa (ausência do evento cancelado; ausência do antigo + presença do novo no reagendamento) antes de liberar ou redirecionar.

### Implementation for User Story 2

- [X] T012 [US2] Confirmado `_verificar_acao_calendario` (T005) para `action_type="cancel"` — já veio genérico do T005, sem ajuste adicional necessário; coberto por `VerificarAcaoCalendarioTest.test_cancel_confirmed_when_event_absent`/`test_cancel_not_confirmed_when_event_still_present`
- [X] T013 [US2] Implementado o caso `action_type="reschedule"` diretamente em `calendar_judge_agent` (não em `_verificar_acao_calendario`): chama `_extrair_periodo_alegado(..., qual="antigo")` e `qual="novo"`, depois `_verificar_acao_calendario(..., "cancel")` para o antigo e `(..., "create")` para o novo — só `"confirmed"` se ambos confirmarem, em `modules/ia/agent_graph.py`

### Tests for User Story 2

- [X] T014 [P] [US2] Teste unitário: resposta de "cancelamento confirmado" sem `tool_calls`, evento **ainda existe** na agenda → `judge_verdict="redirect"`, em `modules/ia/test_agent_graph.py` (`test_cancel_redirects_when_event_still_present`)
- [X] T015 [P] [US2] Teste unitário: resposta de "reagendamento confirmado" sem `tool_calls`, horário antigo ainda existe → `judge_verdict="redirect"`; e caso positivo (antigo ausente + novo presente) → `judge_verdict="confirmed"`, em `modules/ia/test_agent_graph.py` (`test_reschedule_redirects_when_old_still_present`, `test_reschedule_confirms_when_old_absent_and_new_present`)

**Checkpoint**: User Story 2 completa — os 3 fluxos de calendário (criar/cancelar/reagendar) cobertos.

---

## Phase 5: User Story 3 - Perguntas sem relação com agenda não sofrem atraso (Priority: P3)

**Goal**: O `calendar_judge_agent` só é acionado quando há suspeita real de confirmação de agenda sem lastro; conversas institucionais/chitchat continuam no mesmo patamar de latência de hoje. Também cobre o limite de retentativas (anti-loop).

**Independent Test**: Enviar uma pergunta institucional pura e confirmar que nenhuma chamada extra a `calendar_service` ocorre; forçar dois redirecionamentos seguidos no mesmo turno e confirmar que o segundo cai no fallback em vez de loopar.

### Tests for User Story 3

- [X] T016 [P] [US3] Teste unitário: pergunta institucional/operacional sem padrão de confirmação não aciona `calendar_judge_agent` (`_operational_output_router`/`_institutional_output_router` retornam `"end"`), em `modules/ia/test_agent_graph.py` (`OperationalOutputRouterTest.test_routes_to_end_when_no_pending_tool_calls_and_no_confirmation_pattern`; já coberto para institutional/chitchat por `PreEndGuardrailRouterTest.test_ends_when_response_has_no_confirmation_pattern`, que também confere `get_active_tools` não chamado — curto-circuito preservado)
- [X] T017 [US3] Teste unitário: `judge_redirect_count` já no limite (`JUDGE_MAX_REDIRECTS`) faz `calendar_judge_agent` devolver `judge_verdict="blocked"` com a mensagem de fallback "Desculpa, tive um problema para verificar isso agora..." em vez de redirecionar de novo, em `modules/ia/test_agent_graph.py` (`CalendarJudgeAgentTest.test_blocks_with_fallback_after_max_redirects`)

**Checkpoint**: Todas as 3 User Stories completas e testáveis isoladamente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T018 Rodar os 4 cenários de `specs/015-calendar-judge-agent/quickstart.md` manualmente contra o ambiente local — **pendente pelo usuário**: requer Postgres + credenciais reais do Google Calendar rodando (regra do projeto: agente não sobe container/testa o site sozinho); passo a passo documentado no quickstart.md
- [ ] T019 [P] Rodar a suíte de testes completa e confirmar 100% passando — **comando a ser executado pelo usuário** (regra do projeto: sempre passar o comando de teste para o usuário rodar; ambiente local desta sessão não tem `langchain_core` instalado fora do container):
  ```bash
  pytest modules/ia/test_agent_graph.py -v
  ```

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente
- **Foundational (Phase 2)**: depende do Setup; **bloqueia** as 3 User Stories (é o núcleo do nó `calendar_judge_agent`)
- **User Stories (Phase 3-5)**: todas dependem só do Foundational; US1 é o MVP, US2 estende para cancelar/reagendar, US3 valida que não há regressão de latência/loop — podem ser feitas em paralelo ou na ordem P1 → P2 → P3
- **Polish (Phase 6)**: depende de pelo menos US1 estar pronta

### Dentro de cada Fase

- **Foundational**: T002 bloqueia T006 (o nó precisa do regex corrigido); T003 é paralelo; T004 bloqueia T005 (verificação de reagendamento/casos sem tool_call depende da extração); T005 bloqueia T006; T006 bloqueia T007
- **US1**: T008-T011 são testes paralelos entre si (mesmo arquivo, casos diferentes — aplicar com cuidado para não gerar conflito de merge)
- **US2**: T012 e T013 podem ser paralelos (ajustes independentes dentro da mesma função genérica); T014/T015 dependem da implementação correspondente
- **US3**: T016 é independente; T017 depende de T003 (contador) e T007 (wiring) já prontos, que são do Foundational

### Parallel Opportunities

- T003 pode rodar em paralelo com T002 (T002 mexe no regex, T003 no `TypedDict` — trechos diferentes do mesmo arquivo)
- T008-T011 (US1), T014-T015 (US2) e T016 (US3) são todos testes no mesmo arquivo `test_agent_graph.py` — paralelos entre si em termos lógicos, mas exigem merge cuidadoso no mesmo arquivo

---

## Implementation Strategy

### MVP First (User Story 1 apenas)

1. Completar Phase 1: Setup (T001)
2. Completar Phase 2: Foundational (T002-T007) — bloqueante
3. Completar Phase 3: User Story 1 (T008-T011)
4. **PARAR e VALIDAR**: rodar os testes da US1 e o Cenário 1/2/3 do quickstart.md
5. Esse ponto já resolve o incidente relatado no EDI-72 para criação de agendamento

### Incremental Delivery

1. Setup → Foundational (bloqueante, núcleo do juiz) → pronto para as User Stories
2. US1 → testar isoladamente → MVP que corrige o bug relatado
3. US2 → testar isoladamente → cobre cancelamento e reagendamento
4. US3 → testar isoladamente → confirma ausência de regressão de latência e o anti-loop
5. Cada story agrega valor sem quebrar as anteriores

---

## Notes

- [P] = arquivos diferentes ou trechos independentes do mesmo arquivo, sem dependência lógica
- [Story] mapeia cada tarefa à User Story correspondente do spec.md, para rastreabilidade
- Persistência local do agendamento (tabela própria de auditoria) permanece fora de escopo desta entrega, conforme spec.md > Assumptions — o quickstart.md documenta esse passo como opcional/condicional
- Ao final de cada User Story, considerar um commit próprio (mensagem referenciando EDI-72) antes de seguir para a próxima

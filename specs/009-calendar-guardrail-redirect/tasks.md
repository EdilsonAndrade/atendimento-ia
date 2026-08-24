# Tasks: Impedir confirmação de agendamento sem ação real no calendário

**Input**: Design documents from `/specs/009-calendar-guardrail-redirect/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Incluídos. A Constitution (Principle VI) exige cobertura de teste equivalente ao padrão já usado no repositório para mudanças de guardrail de agente de IA; os testes seguem o estilo já existente em `modules/ia/test_agent_graph.py` e `modules/agendamento/test_agente_atendimento.py` (sem subir infraestrutura de teste nova).

**Organization**: Tarefas agrupadas pelas 3 User Stories do spec.md (P1, P2, P3), cada uma independentemente implementável e testável.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1, US2 ou US3 (mapeiam para as User Stories do spec.md)
- Caminhos de arquivo exatos incluídos em cada descrição

## Path Conventions

Projeto único (backend), sem `src/`/`frontend/` — segue a estrutura real já existente em `modules/` (ver plan.md > Project Structure).

---

## Phase 1: Setup

**Purpose**: Confirmar baseline antes de qualquer alteração

- [X] T001 Rodar a suíte de testes existente como baseline (`pytest modules/ia/test_agent_graph.py modules/ia/test_ia_assistante_rag.py modules/agendamento/test_agente_atendimento.py -v`) e confirmar que todos passam antes de iniciar as mudanças

---

## Phase 2: Foundational

**Purpose**: Prerequisitos bloqueantes compartilhados por todas as User Stories

Nenhuma tarefa foundational é necessária nesta feature: US1 (`modules/ia/agent_graph.py` — nós e roteamento), US2 (`modules/ia/thread_session.py` — resumidor) e US3 (`modules/agendamento/tools/google_calendario/*.py` — logs das tools) tocam arquivos disjuntos e não têm dependência umas das outras. As três podem começar em paralelo assim que o Setup terminar.

**Checkpoint**: Nenhum bloqueio — seguir direto para as User Stories.

---

## Phase 3: User Story 1 - Cliente nunca recebe confirmação de agenda que não existe (Priority: P1) 🎯 MVP

**Goal**: Quando `institutional_node`/`chitchat_node` gerarem uma resposta com cara de confirmação/consulta de agenda sem nenhuma tool call real no turno, o grafo executa a ação real via `operational_node` antes de responder ao cliente, em vez de deixar passar o texto alucinado para `END`.

**Independent Test**: Forçar uma resposta de `institutional_node`/`chitchat_node` que bate no padrão de confirmação sem tool (mock/teste unitário) e verificar que o roteamento condicional escolhe `operational_node`, não `END`; e que uma resposta institucional/chitchat normal continua indo para `END` sem alteração.

### Implementation for User Story 1

- [X] T002 [US1] Generalizar `_resposta_sem_lastro_de_tool` (ou extrair um helper equivalente) em `modules/ia/agent_graph.py` para poder ser chamada também a partir de `institutional_node`/`chitchat_node`, reutilizando `BOOKING_CONFIRMATION_CLAIM_PATTERN`/`TOOL_CALL_MARKUP_LEAK_PATTERN` sem duplicar a lógica
- [X] T003 [P] [US1] Corrigir a instrução final de saída do prompt do `routing_agent` (~linha 340 de `modules/ia/agent_graph.py`) para incluir explicitamente `'CONTINUATION'` como saída válida, e mapear essa saída programaticamente para `intencao_anterior` (já calculada em `_intencao_anterior_nao_chitchat`) antes de decidir a aresta condicional de roteamento
- [X] T004 [US1] Em `institutional_node` (`modules/ia/agent_graph.py`), após `llm.invoke(...)`, aplicar o helper do T002 sobre a resposta gerada; se disparar, emitir log com tag `[CALENDAR_GUARDRAIL_REDIRECT]` (tenant_id, nó de origem = "institutional_node", thread_id, trecho da resposta interceptada)
- [X] T005 [US1] Em `chitchat_node` (`modules/ia/agent_graph.py`), após `llm.invoke(...)`, aplicar o mesmo helper do T002 e o mesmo padrão de log `[CALENDAR_GUARDRAIL_REDIRECT]` (nó de origem = "chitchat_node")
- [X] T006 [US1] Criar a(s) função(ões) de roteamento condicional em `modules/ia/agent_graph.py` que leem o sinal produzido pelo T004/T005 e decidem entre `operational_node` e `END`
- [X] T007 [US1] Substituir `builder.add_edge("institutional_node", END)` e `builder.add_edge("chitchat_node", END)` por `builder.add_conditional_edges(...)` usando as funções do T006, em `modules/ia/agent_graph.py` (depende de T002, T004, T005, T006)
- [X] T008 [P] [US1] Teste unitário: resposta de `institutional_node`/`chitchat_node` com padrão de confirmação sem `tool_calls` é roteada para `operational_node` (não para `END`), em `modules/ia/test_agent_graph.py`
- [X] T009 [P] [US1] Teste unitário: resposta institucional/chitchat normal (sem padrão de confirmação) continua roteada para `END` sem alteração de comportamento nem chamadas extras de LLM, em `modules/ia/test_agent_graph.py`
- [X] T010 [P] [US1] Teste unitário: mensagem de continuação (ex. "não entendi") classificada como `CONTINUATION` pelo `routing_agent` é corretamente mapeada para `PREVIOUS TURN INTENT`, em `modules/ia/test_agent_graph.py`

**Checkpoint**: User Story 1 completa e testável isoladamente — este é o MVP que resolve o incidente original do EDI-61.

---

## Phase 4: User Story 2 - Fatos de conversas passadas não repetem alucinações (Priority: P2)

**Goal**: O resumidor de sessão (`_summarize_session`) não declara mais um agendamento como "confirmado" quando não há nenhuma `ToolMessage` real de calendário correspondente no histórico da sessão resumida.

**Independent Test**: Gerar uma sessão cujo histórico contenha uma alegação textual de agendamento confirmado sem `ToolMessage` de sucesso correspondente, chamar `_summarize_session`, e verificar que o campo de resultado não declara o agendamento como confirmado; e que uma sessão com `ToolMessage` de sucesso real continua gerando resumo correto.

### Implementation for User Story 2

- [X] T011 [US2] Ajustar o filtro de mensagens em `_summarize_session` (`modules/ia/thread_session.py`) para considerar `ToolMessage` ao montar o contexto analisado (hoje filtra só `human`/`ai`), sem alterar o texto `conversa_texto` usado no prompt de forma que quebre a leitura humana do resumo
- [X] T012 [US2] Ajustar o prompt de `_summarize_session` (`modules/ia/thread_session.py`) para só declarar o campo `resultado` como agendamento confirmado/cancelado quando houver `ToolMessage` de sucesso correspondente no histórico; caso contrário, usar `null` ou descrição neutra (depende de T011)
- [X] T013 [P] [US2] Teste unitário: sessão com alegação textual de agendamento confirmado mas sem `ToolMessage` real gera resumo com resultado `null`/neutro, em `modules/ia/test_thread_session.py` (novo arquivo, mesma convenção de `test_*.py` colocado junto ao módulo)
- [X] T014 [P] [US2] Teste unitário: sessão com `ToolMessage` de sucesso real de agendamento continua gerando resumo com resultado confirmado corretamente, em `modules/ia/test_thread_session.py`

**Checkpoint**: User Story 2 completa e testável isoladamente.

---

## Phase 5: User Story 3 - Equipe consegue investigar rapidamente qualquer chamada real ao calendário (Priority: P3)

**Goal**: Toda ação real de calendário (criar, consultar, cancelar) e toda interceptação de confirmação sem ação real (US1) ficam localizáveis em produção com um `grep` simples por tag fixa.

**Independent Test**: Executar cada tipo de ação de calendário (criar, consultar, cancelar) e verificar que cada uma aparece no log com sua tag e dados mínimos (tenant_id, google_calendar_id, event_id quando aplicável, período).

### Implementation for User Story 3

- [X] T015 [P] [US3] Padronizar o log de sucesso/falha de `agendar_horario` com as tags `[CALENDAR_CREATE_OK]`/`[CALENDAR_CREATE_FAIL]`, incluindo tenant_id, google_calendar_id, período e event_id, em `modules/agendamento/tools/google_calendario/agenda_tool.py`
- [X] T016 [P] [US3] Padronizar o log de `consultar_agenda` com a tag `[CALENDAR_QUERY]`, incluindo tenant_id, google_calendar_id, período e contagem de eventos encontrados, em `modules/agendamento/tools/google_calendario/consulta_agenda_tool.py`
- [X] T017 [P] [US3] Revisar o nível de log atual de `cancelar_evento_google` e padronizar com as tags `[CALENDAR_CANCEL_OK]`/`[CALENDAR_CANCEL_FAIL]`, incluindo tenant_id, google_calendar_id e event_id, em `modules/agendamento/tools/google_calendario/delete_agenda_tool.py`
- [X] T018 [US3] Confirmar que o fluxo de reagendamento (cancelar + criar) passa pelas duas tools já ajustadas nos T015/T017 — confirmado: `agendar_horario` e `cancelar_evento_google` são as únicas duas tools de escrita no backend Google Calendar, então qualquer sequência de reagendamento (feita pelo LLM guiado pelas regras de TOOL EXECUTION já existentes no prompt operacional) já fica coberta pelas tags dos T015/T017 sem exigir mudança de fluxo. Nota: a seção `RESCHEDULING FLOW` de `prompts/operactional_prompt.md` ainda descreve o fluxo apenas em termos do fallback interno (`consulta_agendamento`), não do backend Google Calendar — ficou fora de escopo por ser mudança de conteúdo de prompt (Principle IV exige revisão dedicada de segurança/prompt-injection para esse tipo de mudança), não de logging
- [X] T019 [P] [US3] Teste unitário: chamada de `agendar_horario` bem-sucedida e com falha emite a tag `[CALENDAR_CREATE_OK]`/`[CALENDAR_CREATE_FAIL]`, em `modules/agendamento/tools/google_calendario/test_calendar_tools_logging.py` (desvio do caminho original do plano: criado um arquivo novo colocado junto às tools, em vez de `modules/agendamento/test_agente_atendimento.py`, que é um script manual sem nenhuma função `test_*` coletável pelo pytest — ver nota abaixo)
- [X] T020 [P] [US3] Teste unitário: chamada de `consultar_agenda` emite a tag `[CALENDAR_QUERY]`, em `modules/agendamento/tools/google_calendario/test_calendar_tools_logging.py`
- [X] T021 [P] [US3] Teste unitário: chamada de `cancelar_evento_google` bem-sucedida e com falha emite a tag `[CALENDAR_CANCEL_OK]`/`[CALENDAR_CANCEL_FAIL]`, em `modules/agendamento/tools/google_calendario/test_calendar_tools_logging.py`

**Checkpoint**: User Story 3 completa e testável isoladamente. Todas as três User Stories funcionam de forma independente.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validação final que atravessa as três User Stories

- [ ] T022 Rodar os 4 cenários de `specs/009-calendar-guardrail-redirect/quickstart.md` manualmente contra o ambiente local antes de considerar a feature pronta para revisão — **pendente**: requer ambiente local com Postgres e credenciais reais do Google Calendar rodando (não disponível nesta sessão de implementação); ver quickstart.md para o passo a passo
- [X] T023 [P] Rodar a suíte de testes completa (`pytest modules/ia/test_agent_graph.py modules/ia/test_thread_session.py modules/agendamento/tools/google_calendario/test_calendar_tools_logging.py -v`) — 19/19 testes passando (nota: `modules/ia/test_ia_assistante_rag.py` e `modules/agendamento/test_agente_atendimento.py`, citados no plano original, não contêm nenhuma função coletável pelo pytest — são scripts manuais pré-existentes, não suítes de teste; não fazem parte da baseline real)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente
- **Foundational (Phase 2)**: vazia nesta feature — nenhuma User Story está bloqueada
- **User Stories (Phase 3-5)**: todas podem começar assim que o Setup (T001) terminar; são independentes entre si (arquivos disjuntos) e podem ser feitas em paralelo ou na ordem de prioridade P1 → P2 → P3
- **Polish (Phase 6)**: depende das User Stories que forem entregues (no mínimo US1, para o MVP)

### Dentro de cada User Story

- **US1**: T002 bloqueia T004/T005/T007; T003 é paralelo e independente do resto; T006 depende de T004+T005 (precisa saber o sinal que eles produzem); T007 depende de T002, T004, T005, T006; os testes T008-T010 dependem da implementação correspondente estar pronta
- **US2**: T011 bloqueia T012; T013/T014 dependem de T011+T012
- **US3**: T015, T016, T017 são paralelos entre si (arquivos diferentes); T018 depende de T015+T017; T019-T021 dependem de sua respectiva tool já ajustada

### Parallel Opportunities

- T003 pode rodar em paralelo com T002/T004/T005 (parte diferente do mesmo arquivo, mas seção de prompt isolada do bloco de código dos nós — cuidado ao mesclar, mas sem dependência lógica)
- T015, T016, T017 (arquivos diferentes) totalmente paralelos
- T008, T009, T010 paralelos entre si (mesmo arquivo de teste, casos diferentes — aplicar com cuidado para não gerar conflito de merge, mas sem dependência lógica)
- US1, US2 e US3 podem ser feitas em paralelo por pessoas diferentes após o Setup

---

## Parallel Example: User Story 3

```bash
# Três tools de calendário em arquivos diferentes, sem dependência entre si:
Task: "Padronizar log de agendar_horario com [CALENDAR_CREATE_OK]/[CALENDAR_CREATE_FAIL] em modules/agendamento/tools/google_calendario/agenda_tool.py"
Task: "Padronizar log de consultar_agenda com [CALENDAR_QUERY] em modules/agendamento/tools/google_calendario/consulta_agenda_tool.py"
Task: "Padronizar log de cancelar_evento_google com [CALENDAR_CANCEL_OK]/[CALENDAR_CANCEL_FAIL] em modules/agendamento/tools/google_calendario/delete_agenda_tool.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 apenas)

1. Completar Phase 1: Setup (T001)
2. Phase 2: Foundational — vazia, sem bloqueio
3. Completar Phase 3: User Story 1 (T002-T010)
4. **PARAR e VALIDAR**: rodar os testes da US1 e o Cenário 1/2 do quickstart.md isoladamente
5. Esse ponto já resolve o incidente original do EDI-61 (agendamento fantasma)

### Incremental Delivery

1. Setup → Foundational (vazia) → pronto para começar
2. US1 → testar isoladamente → já é o MVP que corrige o bug relatado
3. US2 → testar isoladamente → impede que alucinações passadas continuem contaminando resumos futuros
4. US3 → testar isoladamente → dá à equipe visibilidade/observabilidade completa
5. Cada story agrega valor sem quebrar as anteriores (arquivos disjuntos)

---

## Notes

- [P] = arquivos diferentes, sem dependência lógica entre as tarefas
- [Story] mapeia cada tarefa à User Story correspondente do spec.md, para rastreabilidade
- Persistência local do agendamento (tabela de bookings) permanece fora de escopo, conforme spec.md > Assumptions
- Ao final de cada User Story, considerar um commit próprio (mensagem referenciando EDI-61) antes de seguir para a próxima

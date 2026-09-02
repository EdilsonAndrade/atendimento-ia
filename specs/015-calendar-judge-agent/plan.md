# Implementation Plan: calendar_judge_agent — verificar agendamento real antes de confirmar ao cliente

**Branch**: `edilsonaandrade/edi-72-calendar_judge_agent-verificar-agendamento-real-na-agenda` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/015-calendar-judge-agent/spec.md`

**Note**: This plan follows the workflow in `.specify/templates/plan-template.md`.

## Summary

Adicionar um novo nó `calendar_judge_agent` ao grafo LangGraph existente (`modules/ia/agent_graph.py`) que verifica, contra a integração real do Google Calendar (via `consultar_agenda`), se uma resposta de confirmação/consulta/cancelamento de agenda gerada sem `tool_calls` no turno corresponde a uma ação que de fato ocorreu — usando `tenant_id` + telefone do cliente + período como chave (não `thread_id`, que não é persistido no Calendar). Se a verificação falhar, o turno é redirecionado para `operational_node`, que executa a ação real reaproveitando as regras de negócio já existentes ali. Isso substitui a "prova por estado local" (presença de `ToolMessage` no turno) usada hoje pelo guardrail do EDI-61 por uma prova contra a fonte de verdade externa, fechando o furo identificado no incidente do EDI-72 (regex `BOOKING_CONFIRMATION_CLAIM_PATTERN` não cobria a frase real gerada em produção).

## Technical Context

**Language/Version**: Python 3.11+ (baseline atual do projeto)
**Primary Dependencies**: LangGraph (`StateGraph`, nós/arestas condicionais), LangChain (`ChatOpenAI` via DeepSeek), `langchain_core.messages` (reaproveita `_resposta_sem_lastro_de_tool` já existente)
**Storage**: N/A para este nó (não persiste nada novo) — consulta somente a integração externa já usada (Google Calendar via `calendar_service.list_events`, o mesmo backend de `consultar_agenda`)
**Testing**: pytest, colocado em `modules/ia/test_agent_graph.py` (convenção já usada pelos demais nós do grafo)
**Target Platform**: Linux containers (topologia de deploy atual)
**Project Type**: Web service (FastAPI backend) — mudança interna de orquestração, sem novo endpoint
**Performance Goals**: Nenhum aumento perceptível de latência para turnos sem suspeita de confirmação de agenda (o juiz só é acionado quando há suspeita); para turnos com suspeita, adiciona no máximo 1 chamada de consulta ao Google Calendar antes de responder
**Constraints**: Não duplicar regras de negócio de agendamento (múltiplos agendamentos, privacidade, horário de funcionamento) fora do `operational_node`; limite de 1 redirecionamento por turno para evitar loop
**Scale/Scope**: Roda no mesmo grafo multi-tenant já existente (`modules/ia/agent_graph.py`), afetando os tenants com `scheduling_enabled=True`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Multi-Tenant Isolation ✅ PASS
- A verificação usa `tenant_id` para resolver o `google_calendar_id` correto (mesmo mecanismo já usado por `consultar_agenda`/`agendar_horario`), garantindo que o juiz nunca consulte o calendário de outro tenant.
- Dentro do mesmo tenant, a chave de verificação inclui o telefone do cliente (não apenas o período), evitando que o agendamento de um cliente seja aceito como prova do agendamento de outro (User Story 1, cenário 3 do spec).

### Principle II: API-First, Backend-Only Boundary ✅ PASS
- Nenhum endpoint novo é criado ou modificado. `calendar_judge_agent` é um nó interno do grafo LangGraph, acionado apenas via `/api/v1/chat` já existente (FR-008 do spec).

### Principle III: Modular Clean Architecture — N/A (módulo legado, Governance > Legacy Migration Policy)
- `modules/ia/agent_graph.py` é um módulo legado listado explicitamente na Legacy Migration Policy da constituição. O novo nó segue o mesmo padrão dos nós vizinhos já existentes (`operational_node`, `institutional_node`, `_make_pre_end_guardrail_router`) — não introduz uma nova pasta `modules/<nome>/` nem justifica um retrofit isolado deste módulo.
- Regra 2 da Legacy Migration Policy é respeitada: o juiz depende dos métodos públicos já existentes (`build_consulta_tool`/`calendar_service.list_events`, `get_active_tools`, `TenantService`), sem acessar `infrastructure.connection` ou outro módulo diretamente.

### Principle IV: Security & Guardrails by Default ✅ PASS
- Esta é, por definição, uma mudança de guardrail: fecha um furo que permitia ao agente confirmar uma ação de calendário sem lastro real (risco de "falsa confirmação", citado explicitamente na constituição como exemplo de risco de guardrail).
- Nenhum dado sensível novo é exposto — a consulta usa os mesmos parâmetros (`tenant_id`, telefone, período) já manipulados por `consultar_agenda` hoje.

### Principle V: Asynchronous Processing for Heavy/AI Workloads ✅ PASS
- A chamada de verificação ao Google Calendar acontece dentro do próprio ciclo síncrono de `/api/v1/chat`, igual às demais tools de calendário já usadas por `operational_node` hoje — não é um workload de embedding/ingestão em lote, então não se aplica o requisito de mover para background task.

### Principle VI: Test-First Discipline ⚠️ ADAPTADO (módulo legado)
- Módulo legado não exige o split unit/integration completo de Principle VI, mas a mesma convenção de teste já usada em `modules/ia/test_agent_graph.py` (testes colocados, mockando `llm`/`calendar_service`) será seguida, cobrindo: verificação encontra evento (libera resposta), não encontra (redireciona), limite de retentativas (evita loop), e isolamento entre clientes do mesmo tenant (User Story 1, cenário 3).

## Project Structure

### Documentation (this feature)

```text
specs/015-calendar-judge-agent/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output (roteiro de teste manual)
└── tasks.md             # Phase 2 output (/speckit-tasks — ainda não gerado)
```

### Source Code (repository root)

```text
modules/ia/
├── agent_graph.py        # Adiciona: calendar_judge_agent (nó), aresta condicional pós-operational_node
│                          # e pós-institutional_node/chitchat_node (substitui o destino direto de
│                          # _make_pre_end_guardrail_router), extração de período/telefone da resposta,
│                          # contagem de retentativas por turno (AgentState)
└── test_agent_graph.py   # Novos testes: verificação encontra/não encontra evento, redirecionamento,
                           # limite de retentativas, isolamento por telefone dentro do mesmo tenant

modules/agendamento/tools/google_calendario/
└── consulta_agenda_tool.py   # Reaproveitado sem alteração de contrato — o juiz chama a mesma função
                                # de consulta (`consultar_agenda`/`calendar_service.list_events`), não
                                # uma nova tool exposta ao LLM
```

**Structure Decision**: Toda a mudança fica dentro do módulo legado já existente `modules/ia/`, seguindo o padrão dos nós vizinhos (`operational_node`, `institutional_node`, `chitchat_node`) e reaproveitando a infraestrutura de consulta de calendário já existente em `modules/agendamento/tools/google_calendario/`. Não é criado nenhum módulo novo, endpoint novo, ou tabela nova — consistente com Principle II e com a Legacy Migration Policy (Principle III).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Nenhuma violação. Principle III é tratado via Legacy Migration Policy (módulo grandfathered), não como violação — a mudança segue o padrão já estabelecido no próprio `modules/ia/agent_graph.py` para os nós existentes.

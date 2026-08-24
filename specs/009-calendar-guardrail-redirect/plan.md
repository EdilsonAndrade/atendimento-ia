# Implementation Plan: Impedir confirmação de agendamento sem ação real no calendário

**Branch**: `edilsonaandrade/edi-61-agendamentos-fantasma-institutional_nodechitchat_node` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-calendar-guardrail-redirect/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`institutional_node` e `chitchat_node` (LangGraph, `modules/ia/agent_graph.py`) não têm nenhuma tool de calendário vinculada e vão direto para `END`. Quando o `routing_agent` classifica incorretamente um turno operacional (confirmação/consulta de agenda) como INSTITUTIONAL ou CHITCHAT, o LLM pode narrar em texto uma confirmação de agendamento sem que a ação real ocorra no Google Calendar — já causou um agendamento fantasma em produção (EDI-61).

Abordagem técnica: reaproveitar o padrão de detecção de "confirmação sem lastro de tool" já existente em `_resposta_sem_lastro_de_tool`/`BOOKING_CONFIRMATION_CLAIM_PATTERN`, aplicando-o também na saída de `institutional_node` e `chitchat_node`. Em vez de `add_edge(node, END)` fixo, usar `add_conditional_edges` que redireciona esses casos para `operational_node` (único nó com tools de calendário vinculadas e todo o guardrail/regras de negócio já implementados), sem duplicar essas regras em outro nó. Em paralelo: corrigir a instrução contraditória do prompt do `routing_agent` (classe `CONTINUATION` nunca é uma saída válida), blindar `_summarize_session` (`modules/ia/thread_session.py`) para não persistir "agendamento confirmado" sem `ToolMessage` real correspondente, e padronizar tags de log fixas em todas as tools de calendário (`modules/agendamento/tools/google_calendario/*.py`) e no novo ponto de redirecionamento, para que qualquer ação real (ou tentativa interceptada) seja localizável em produção via grep.

## Technical Context

**Language/Version**: Python 3.13 (runtime local) / imagem de produção `python:3.11-slim` (Dockerfile) — código deve permanecer compatível com 3.11+
**Primary Dependencies**: LangGraph (`StateGraph`, `add_conditional_edges`), LangChain Core (`AIMessage`, `ToolMessage`, `SystemMessage`), `langchain-openai` (`ChatOpenAI`), `psycopg` (leitura de checkpoint em `thread_session.py`)
**Storage**: Nenhuma nova tabela. Logging estruturado via `print`/`logging` para stdout (mesmo padrão já usado em todo `agent_graph.py` e nas tools de calendário) — sem persistência adicional nesta feature (ver Assumptions do spec).
**Testing**: `pytest` — testes unitários colocados junto ao módulo (`modules/ia/test_agent_graph.py` já existe e cobre `_resposta_sem_lastro_de_tool`; `modules/agendamento/test_agente_atendimento.py` para as tools de calendário), seguindo a convenção já estabelecida no repositório.
**Target Platform**: Servidor Linux (container Docker), API FastAPI já em produção — esta feature não adiciona endpoint novo, só altera o comportamento interno do grafo LangGraph e dos logs.
**Project Type**: Backend único (API + workers), sem frontend neste repositório (ver Principle II da constituição).
**Performance Goals**: Sem meta nova de performance — o redirecionamento adiciona no máximo uma invocação extra de LLM (`operational_node`) apenas no caso raro de classificação incorreta detectada; não deve afetar o caminho feliz (resposta institucional/chitchat correta continua com uma única invocação, como hoje).
**Constraints**: Não duplicar regras de negócio de agendamento (múltiplos agendamentos, privacidade de calendário, horário de funcionamento, `SESSION CONTACT MEMORY`) fora do `operational_node` — reaproveitar via redirecionamento no grafo, não via novo `bind_tools`. Mudança em guardrail/prompt exige atenção a impacto de prompt-injection e segurança (Principle IV).
**Scale/Scope**: Mudança concentrada em `modules/ia/agent_graph.py` (grafo + guardrails + prompt do roteador), `modules/ia/thread_session.py` (resumidor de sessão) e `modules/agendamento/tools/google_calendario/*.py` (padronização de logs). Nenhuma mudança de schema de banco, nenhum endpoint novo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Multi-Tenant Isolation** — PASS. Nenhuma mudança toca isolamento de tenant; `tenant_id` já flui via `config["configurable"]` em todos os nós tocados e continua sendo repassado sem alteração.
- **II. API-First, Backend-Only Boundary** — PASS. Nenhum endpoint novo, nenhuma UI. Mudança é interna ao grafo LangGraph.
- **III. Modular Clean Architecture (NON-NEGOTIABLE para código novo)** — N/A para o código alterado: `modules/ia` e `modules/agendamento` são módulos legados listados explicitamente na *Legacy Migration Policy*. Esta feature é uma correção de bug + hardening de guardrail/logging dentro desses módulos, não uma reescrita nem um módulo novo — respeita a política ("Bug fixes in legacy modules do not require migrating the whole module to Clean Architecture first") e não introduz SQL novo fora dos repositórios existentes nem lógica de negócio direto em endpoint.
- **IV. Security & Guardrails by Default** — PASS, e é o próprio objetivo da feature: esta é uma mudança de guardrail de agente de IA relacionada à prevenção de "false calendar confirmations" — exatamente o exemplo citado na rationale deste princípio. O redirecionamento reaproveita o guardrail e as regras já revisadas do `operational_node`, em vez de criar um novo caminho de ação não revisado.
- **V. Asynchronous Processing for Heavy or AI Workloads** — PASS. O redirecionamento para `operational_node` acontece dentro do mesmo ciclo de grafo síncrono já existente (mesmo padrão de `tools` → `operational_node` já presente); não introduz nova chamada de IA fora do padrão já estabelecido no grafo.
- **VI. Test-First Discipline** — APLICÁVEL. Como é módulo legado (não um "novo use case/serviço" do zero), o requisito rígido de unit+integration test para *todo* novo endpoint não se aplica ao pé da letra, mas a correção de guardrail exige cobertura de teste equivalente ao padrão já usado em `modules/ia/test_agent_graph.py` (que já testa `_resposta_sem_lastro_de_tool`) — ver Fase 2/tasks para os casos de teste unitários do novo redirecionamento condicional e do ajuste no resumidor de sessão.

**Resultado**: Nenhuma violação. Nenhuma entrada necessária em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/009-calendar-guardrail-redirect/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
└── tasks.md              # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

Não há `contracts/` nesta feature: não há interface externa nova (nenhum endpoint HTTP, nenhum schema Pydantic novo) — a mudança é inteiramente interna ao grafo LangGraph e aos logs da aplicação.

### Source Code (repository root)

```text
# Option 1: Single project (backend único, sem frontend neste repositório — ver Principle II)
modules/
├── ia/
│   ├── agent_graph.py          # routing_agent (prompt), institutional_node, chitchat_node,
│   │                            # operational_node, _resposta_sem_lastro_de_tool, novos
│   │                            # add_conditional_edges de institutional_node/chitchat_node
│   ├── test_agent_graph.py     # testes unitários existentes + novos casos do redirecionamento
│   ├── thread_session.py       # _summarize_session — blindagem contra alegação sem ToolMessage
│   └── test_ia_assistante_rag.py
└── agendamento/
    ├── test_agente_atendimento.py
    └── tools/google_calendario/
        ├── agenda_tool.py          # agendar_horario — padronizar tags [CALENDAR_CREATE_OK/FAIL]
        ├── consulta_agenda_tool.py # consultar_agenda — padronizar tag [CALENDAR_QUERY]
        └── delete_agenda_tool.py   # cancelar_evento_google — padronizar tags [CALENDAR_CANCEL_OK/FAIL]

tests/
└── (sem mudança de estrutura; testes unitários permanecem colocados junto ao módulo,
     conforme convenção já registrada na Constitution > Current Architecture Map)
```

**Structure Decision**: Opção 1 (projeto único/backend), sem novos diretórios — toda a mudança acontece dentro de `modules/ia/` e `modules/agendamento/tools/google_calendario/`, módulos legados já existentes, seguindo a *Legacy Migration Policy* da constituição (correção de bug/guardrail, sem retrofit completo de Clean Architecture).

## Complexity Tracking

> Nenhuma violação de Constitution Check — tabela não aplicável, nenhuma entrada necessária.

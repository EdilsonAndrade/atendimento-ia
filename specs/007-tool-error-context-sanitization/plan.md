# Implementation Plan: Sanitização do contexto de conversa enviado ao LLM

**Branch**: `edilsonaandrade/edi-59-sanitizar-contexto-de-conversa-enviado-ao-llm-erros-janela-e` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/007-tool-error-context-sanitization/spec.md`

## Summary

Tools do agente de agendamento devolvem `str(e)` cru como conteúdo de `ToolMessage` quando uma exceção técnica ocorre (DB, Google Calendar API), poluindo o histórico persistido pelo `PostgresSaver` e reenviado ao LLM a cada turno subsequente dentro da janela do `trim_messages` — causa raiz de respostas erradas do agente após falhas internas. Esta feature adiciona: (1) um decorator `@safe_tool_result` (`util/tool_error_handling.py`) aplicado às 7 funções `@tool` afetadas, que captura a exceção, loga o erro completo (com tenant_id/thread_id quando disponíveis) e devolve uma mensagem curta genérica ao LLM; (2) aumento da janela de `trim_messages` de 50 para 95 mensagens em `modules/ia/agent_graph.py`; (3) tipagem `-> str` explícita em todas as `@tool`; (4) uma Camada 2 de memória — resumo + fatos estruturados gerados em background (`FastAPI BackgroundTasks`) quando `resolve_active_thread_id` detecta expiração de sessão por inatividade, persistidos em uma nova tabela `chat_thread_summaries` e injetados no prompt da próxima sessão do mesmo `base_thread_id`, no mesmo padrão do `build_customer_context_block` já existente.

## Technical Context

**Language/Version**: Python 3.13, LangChain/LangGraph
**Primary Dependencies**: LangChain, LangGraph (`trim_messages`, `PostgresSaver`), `langchain_openai.ChatOpenAI` (DeepSeek), FastAPI (`BackgroundTasks`), psycopg3
**Storage**: PostgreSQL — tabela existente `chat_thread_sessions`; nova tabela `chat_thread_summaries` (ver `data-model.md`)
**Testing**: pytest — `tests/unit/` (decorator de sanitização e corte de janela, sem chamada real de LLM/DB) e `tests/integration/` (fluxo do grafo com uma tool forçada a falhar), seguindo a separação já adotada no EDI-45
**Target Platform**: Linux server, container Docker (mesmo processo da API existente)
**Project Type**: web-service (backend único) — sem frontend
**Performance Goals**: nenhum requisito novo; a sanitização é overhead desprezível (try/except), e a geração de resumo (US4) roda fora do ciclo request/response
**Constraints**: a geração de resumo/fatos estruturados (US4) NÃO PODE bloquear a resposta ao cliente (Princípio V da constituição) — ver `research.md` §2
**Scale/Scope**: 1 decorator novo + aplicação em 7 arquivos de tool, 1 alteração de constante, 6 assinaturas de função com tipagem ajustada, 1 migration nova, 1 função de geração/persistência de resumo, integração com `BackgroundTasks` no endpoint de chat

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
| -- | -- |
| I. Multi-Tenant Isolation | **PASS** — a sanitização preserva `tenant_id` apenas nos logs internos (nunca vazado entre tenants na resposta ao cliente); o resumo de sessão (US4) é chaveado por `base_thread_id`, que já é isolado por cliente/tenant hoje via o mecanismo existente de `thread_session.py`. |
| II. API-First, Backend-Only | **N/A** — nenhum endpoint novo é exposto para consumo externo; a geração de resumo é um processo interno acionado a partir do endpoint de chat já existente. |
| III. Modular Clean Architecture | **PASS (módulo legado, item 2/3 da Legacy Migration Policy)** — o decorator de sanitização vive em `util/` (mesmo padrão de `ai_helpers.py`/`time_helpers.py`, não é lógica de negócio nova dentro de um módulo legado); o SQL de resumo fica concentrado em `modules/ia/thread_session.py`, o único ponto do módulo `ia` que já fala com o Postgres para controle de sessão — nenhum canal de acesso a banco novo é aberto (ver `research.md` §3). |
| IV. Security & Guardrails by Default | **N/A** — nenhuma mudança de autenticação/autorização; a mensagem sanitizada ao cliente é estritamente menos exposta que o comportamento atual (remove detalhe técnico). |
| V. Asynchronous Processing | **PASS (por desenho)** — a geração de resumo/fatos estruturados usa `FastAPI BackgroundTasks` disparada a partir do endpoint de chat, exatamente para não bloquear o ciclo request/response com a chamada de LLM de resumo (ver `research.md` §2). |
| VI. Test-First Discipline | **PASS (planejado)** — Phase 2 (`/speckit-tasks`) gera testes unitários (decorator, corte de janela, extração de fatos estruturados com repositório fake) e de integração (tool forçada a falhar via `TestClient`, expiração de sessão gerando resumo) antes/junto da implementação. |

Nenhuma violação exige entrada na tabela de Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/007-tool-error-context-sanitization/
├── plan.md              # Este arquivo
├── research.md          # Fase 0 — decisões técnicas
├── data-model.md         # Fase 1 — nova tabela chat_thread_summaries
└── tasks.md             # Fase 2 (gerado a seguir)
```

### Source Code (repository root)

Projeto único (backend Python/FastAPI existente); arquivos reais tocados por esta feature:

```text
migrations/versions/
└── 0006_chat_thread_summaries.py    # NOVO — tabela chat_thread_summaries

util/
└── tool_error_handling.py           # NOVO — decorator @safe_tool_result

modules/
├── agendamento/
│   ├── booking_tools.py             # MODIFICADO — decorator + tipagem -> str
│   ├── agenda_tool.py                # MODIFICADO — decorator + tipagem -> str
│   ├── delete_agenda_tool.py         # MODIFICADO — decorator + tipagem -> str
│   ├── consulta_agenda_tool.py       # MODIFICADO — decorator + tipagem -> str
│   └── tools/google_calendario/
│       ├── agenda_tool.py            # MODIFICADO — decorator
│       ├── consulta_agenda_tool.py   # MODIFICADO — decorator
│       └── delete_agenda_tool.py     # MODIFICADO — decorator
└── ia/
    ├── agent_graph.py                # MODIFICADO — trim_messages max_tokens 50 -> 95;
    │                                  #   injeta resumo/fatos estruturados no prompt
    └── thread_session.py             # MODIFICADO — detecta expiração, expõe função
                                       #   para gerar/persistir/consultar resumo

app/api/v1/endpoints/
└── chat.py                          # MODIFICADO — dispara BackgroundTasks quando
                                       #   thread_session sinaliza sessão expirada

tests/
├── unit/
│   ├── test_tool_error_handling.py           # NOVO
│   ├── test_agent_graph_trim_window.py       # NOVO
│   └── test_thread_session_summary.py        # NOVO
└── integration/
    └── test_chat_tool_failure_sanitized.py   # NOVO
```

**Structure Decision**: segue a estrutura já existente do projeto (backend único, sem `src/`/`frontend/`); o decorator cross-cutting fica em `util/` (mesmo padrão de `ai_helpers.py`), e a lógica de resumo de sessão fica concentrada em `modules/ia/thread_session.py`, consistente com a Legacy Migration Policy.

## Complexity Tracking

*Nenhuma violação da Constituição exige justificativa nesta tabela.*

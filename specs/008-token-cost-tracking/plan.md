# Implementation Plan: Rastreamento de custo de token por conversa e tenant

**Branch**: `edilsonaandrade/edi-60-rastrear-custo-de-token-por-conversatenant-usando` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/008-token-cost-tracking/spec.md`

## Summary

Hoje não existe nenhum rastreio de custo/consumo de token por conversa ou tenant. Esta feature adiciona um módulo novo `modules/token_usage/` (Domain/Application/Infrastructure, Princípio III da constituição, já que é capacidade net-new) que recebe a resposta de cada chamada ao LLM feita pelo agente (`routing_agent`, `institutional_node`, `chitchat_node`, `operational_node` — incluindo o retry do operacional), extrai o `usage_metadata` nativo do `ChatOpenAI`, calcula um custo estimado (preço por token configurável) e persiste um registro individual em uma nova tabela `chat_token_usage`, associado ao `tenant_id`, ao `base_thread_id` (conversa) e ao `node_type` que originou a chamada. Falhas de persistência nunca afetam a resposta ao cliente.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: `langchain_openai.ChatOpenAI` (`usage_metadata` nativo), psycopg3, `Decimal` (stdlib) para cálculo de custo
**Storage**: PostgreSQL — nova tabela `chat_token_usage` (ver `data-model.md`)
**Testing**: pytest — `tests/unit/` (Domain + Application com repositório fake, sem banco/LLM real) e `tests/integration/` (`PostgresTokenUsageRepository` contra banco real, e os 4 pontos de chamada em `agent_graph.py` gerando registro)
**Target Platform**: Linux server, container Docker (mesmo processo da API existente)
**Project Type**: web-service (backend único) — sem frontend; sem endpoint HTTP novo nesta feature (ver spec.md, Assumptions)
**Performance Goals**: overhead desprezível por chamada (1 insert simples); nunca pode adicionar latência perceptível à resposta ao cliente (FR-006)
**Constraints**: módulo NOVO, portanto Princípios III (Clean Architecture) e VI (unit + integration tests) são NON-NEGOTIABLE desde o primeiro commit — sem grace period de módulo legado
**Scale/Scope**: 1 migration nova, 1 módulo novo com 3 camadas (Domain/Application/Infrastructure), 1 helper de integração em `modules/ia/agent_graph.py` chamado em 5 pontos (4 nós + 1 retry)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
| -- | -- |
| I. Multi-Tenant Isolation | **PASS** — todo registro carrega `tenant_id` explícito, vindo do mesmo `config.configurable.tenant_id` já usado por todo o resto do grafo; nenhum dado é lido/somado entre tenants nesta feature (agregação fica para consumidor futuro). |
| II. API-First, Backend-Only | **PASS/N/A** — nenhum endpoint novo é exposto (decisão registrada em `spec.md`, Assumptions); é persistência interna, sem UI. |
| III. Modular Clean Architecture | **PASS (módulo novo, sem grace period)** — `modules/token_usage/` implementado com Domain (entidade + cálculo de custo, sem import de framework), Application (`RecordTokenUsageUseCase` dependendo de um `Protocol` `TokenUsageRepository`), Infrastructure (`PostgresTokenUsageRepository`). `modules/ia/agent_graph.py` (legado) só depende do caso de uso público da Application layer, nunca da Infrastructure diretamente. |
| IV. Security & Guardrails by Default | **N/A** — nenhuma mudança de autenticação/autorização; não expõe nenhum dado novo a nenhum consumidor externo. |
| V. Asynchronous Processing | **PASS** — a chamada ao LLM em si já é o trabalho pesado (já tratado pelo restante do sistema); o registro de custo é um insert leve e síncrono, mas protegido por try/except que nunca bloqueia nem atrasa perceptivelmente a resposta (FR-006) — não se qualifica como "AI-model-bound work" que o Princípio V exige rodar em background. |
| VI. Test-First Discipline | **PASS (planejado)** — Phase 2 gera testes unitários (Domain puro + Application com repositório fake) e de integração (Infrastructure contra Postgres real + os 4 pontos de chamada em `agent_graph.py`) antes/junto da implementação. |

Nenhuma violação exige entrada na tabela de Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/008-token-cost-tracking/
├── plan.md              # Este arquivo
├── research.md          # Fase 0 — decisões técnicas
├── data-model.md         # Fase 1 — nova tabela chat_token_usage + entidades
└── tasks.md             # Fase 2 (gerado a seguir)
```

### Source Code (repository root)

```text
migrations/versions/
└── 0007_chat_token_usage.py          # NOVO — tabela chat_token_usage

modules/token_usage/                  # NOVO módulo (Clean Architecture completa)
├── __init__.py
├── domain/
│   ├── __init__.py
│   └── token_usage_record.py         # TokenUsageRecord (dataclass) + calculate_cost_usd()
├── application/
│   ├── __init__.py
│   ├── ports.py                      # Protocol TokenUsageRepository
│   └── record_token_usage.py         # RecordTokenUsageUseCase
└── infrastructure/
    ├── __init__.py
    └── postgres_token_usage_repository.py   # PostgresTokenUsageRepository

modules/ia/
└── agent_graph.py                    # MODIFICADO — record_llm_usage() chamado após
                                       #   cada .invoke() (routing_agent, institutional_node,
                                       #   chitchat_node, operational_node x2)

tests/
├── unit/
│   ├── test_token_usage_domain.py            # NOVO — calculate_cost_usd, TokenUsageRecord
│   └── test_record_token_usage_use_case.py   # NOVO — use case com repositório fake
└── integration/
    ├── test_postgres_token_usage_repository.py   # NOVO — repositório real contra Postgres
    └── test_agent_graph_records_token_usage.py   # NOVO — chamadas reais aos 4 nós geram registro
```

**Structure Decision**: `modules/token_usage/` é o primeiro módulo do projeto construído com a Arquitetura Modular Limpa completa desde o início (Domain/Application/Infrastructure explícitos), conforme exigido pela constituição para código net-new — diferente da estrutura endpoint→service→repository ainda vigente nos módulos legados.

## Complexity Tracking

*Nenhuma violação da Constituição exige justificativa nesta tabela.*

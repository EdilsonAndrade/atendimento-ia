# Phase 1 Data Model: calendar_judge_agent

Não há tabela ou schema Pydantic persistente novo (nenhuma migration necessária). As entidades abaixo são
estruturas em memória, válidas apenas durante o turno.

## VerificationAttempt (em memória, não persistida)

Representa uma execução do `calendar_judge_agent`.

| Campo               | Tipo                                   | Origem / Observação |
|---------------------|-----------------------------------------|----------------------|
| `tenant_id`          | `str`                                   | `config["configurable"]["tenant_id"]` |
| `thread_id`          | `str`                                   | `config["configurable"]["thread_id"]` — usado só para log/correlação, nunca como chave de busca no Calendar |
| `action_type`        | `Literal["create","cancel","reschedule"]` | Inferido do padrão heurístico que disparou o pré-filtro (`BOOKING_CONFIRMATION_CLAIM_PATTERN`) |
| `customer_phone`      | `str \| None`                            | `extract_customer_profile(state["messages"])`; ausência ⇒ falha de verificação |
| `claimed_start_time`  | `str (ISO) \| None`                      | Extraído via LLM call curto (Decisão 2 do research.md) a partir do texto suspeito + `CALENDAR REFERENCE` |
| `claimed_end_time`    | `str (ISO) \| None`                      | Idem |
| `verification_result` | `Literal["confirmed","not_confirmed","extraction_failed"]` | Resultado da consulta real (`consultar_agenda`/`calendar_service.list_events`) |
| `redirected`          | `bool`                                  | Se o turno foi mandado de volta para `operational_node` |

## AgentState (extensão do estado existente do grafo)

Adiciona um campo efêmero ao `TypedDict AgentState` já existente em `modules/ia/agent_graph.py`:

| Campo                 | Tipo   | Regra |
|------------------------|--------|-------|
| `judge_redirect_count` | `int`  | Incrementado a cada redirecionamento do `calendar_judge_agent` para `operational_node` dentro do mesmo turno; resetado implicitamente porque não é persistido como fato de negócio — apenas contado durante a execução do grafo para o turno corrente (ver Decisão 4 do research.md: limite de 1 por turno, não por thread). |

## Chave de verificação (Key Entity do spec.md)

```
(tenant_id, customer_phone, claimed_start_time..claimed_end_time)
```

- `tenant_id` resolve `google_calendar_id` (isolamento entre tenants — Principle I).
- `customer_phone` é passado como `query` para `consultar_agenda`/`calendar_service.list_events` (parâmetro já suportado, sem mudança de contrato).
- `claimed_start_time`/`claimed_end_time` delimitam a janela de busca — mesmo papel que já cumprem em `consultar_agenda` hoje.

Nenhum novo índice, coluna ou tabela é necessário: a verificação é 100% uma leitura contra a integração externa (Google Calendar) já usada pelas tools existentes.

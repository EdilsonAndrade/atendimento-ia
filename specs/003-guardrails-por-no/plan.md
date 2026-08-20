# Implementation Plan: Guardrails Independentes por Nó (Operational, Institutional, Chitchat)

**Branch**: `edilsonaandrade/edi-42-permitir-associar-guardrails-ao-chitchat_node` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-guardrails-por-no/spec.md`
**Ticket**: EDI-42

**Note**: Este plano cobre **apenas backend/API** (`prompt_manager` + runtime do agente em `modules/ia`). A
"tela de associação de guardrails" citada no ticket é implementada em outro repositório (Constitution
Principle II) e consome exclusivamente os endpoints documentados em `contracts/`.

## Summary

Hoje `operational_node` e `institutional_node` compartilham obrigatoriamente o mesmo prompt/guardrails do
tenant (via `tenant_prompts` → `prompts` → `prompt_guardrails`), e `chitchat_node` é 100% hardcoded em
`agent_graph.py`, sem nenhuma configuração vinda do banco. Este plano introduz um atributo `node_type` em
`prompts` (`operational` | `institutional` | `chitchat`), torna o vínculo tenant↔prompt independente por nó
(corrigindo a desativação cruzada de vínculos), implementa a cadeia de fallback acordada
(`institutional → operational do tenant`; `chitchat → prompt padrão do nó → texto fixo atual`), e faz um seed
idempotente para que tenants já configurados não sofram nenhuma regressão de comportamento.

## Technical Context

**Language/Version**: Python 3.11 (backend FastAPI existente)
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg3 (SQL cru, sem ORM), LangGraph (nós do agente em
`modules/ia/agent_graph.py`)
**Storage**: PostgreSQL — tabelas existentes `prompts`, `guardrails`, `prompt_guardrails`, `tenant_prompts`;
**alteração**: `ALTER TABLE prompts ADD COLUMN node_type` (sem tabela nova)
**Testing**: pytest — testes unitários com repositório fake/real conforme convenção já usada em
`tests/unit/test_prompt_manager_fallback.py`; testes de integração contra Postgres real conforme
`tests/integration/test_prompt_manager_sync.py`
**Target Platform**: Linux container (deploy Docker/GHCR existente, sem infraestrutura nova)
**Project Type**: Serviço backend único (API REST) — sem frontend neste repositório
**Performance Goals**: Resolução do prompt/guardrails por nó permanece uma leitura simples indexada (mesma
ordem de grandeza da consulta `operational_node` já existente hoje, sem chamadas de rede adicionais)
**Constraints**: Nenhum vínculo de nó pode desativar vínculos ativos de outro nó do mesmo tenant (FR-009);
zero regressão para tenants já configurados antes desta feature (SC-003) sem exigir ação manual
**Scale/Scope**: Mesma escala do restante do `prompt_manager` — pequeno/médio número de tenants, 3 nós fixos
por tenant (não é um conjunto arbitrário de nós)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Multi-Tenant Isolation | Todas as queries novas/alteradas (`get_active_prompt_by_tenant`, `sync_tenant_prompt`, seed) continuam filtrando por `tenant_id`; nenhuma leitura cruza tenants. | PASS |
| II. API-First, Backend-Only Boundary | Apenas endpoints REST + schemas são alterados/adicionados (`contracts/prompt-node-type.md`); nenhum código de UI entra neste repositório. | PASS |
| III. Modular Clean Architecture | `prompt_manager` é módulo legado (predata Princípio III). Pela Legacy Migration Policy, a extensão (novo campo `node_type`, novo parâmetro nas funções existentes) reutiliza os métodos públicos já existentes do repositório/serviço, sem SQL novo fora de `PromptManagerRepository` e sem lógica de negócio nova direto no endpoint — mesmo padrão já aplicado em cima deste módulo pela feature 001. | PASS (carve-out legado, deliberado) |
| IV. Security & Guardrails by Default | Endpoints de `prompt_manager` seguem sem autenticação, mesmo estado pré-existente de todo o módulo (decisão já registrada e aceita na feature 001 — não é uma regressão introduzida aqui). Guardrails continuam sendo a defesa primária do agente; a mudança em si é aditiva (mais guardrails configuráveis, não menos). | PASS (nenhuma mudança de postura de segurança) |
| V. Asynchronous Processing | Não há trabalho pesado de IA/embeddings nesta feature — leitura/escrita de texto e associações relacionais, síncronas, como o restante de `prompt_manager` hoje. | N/A |
| VI. Test-First Discipline | Toda lógica nova (`node_type` na resolução de prompt, isolamento de `sync_tenant_prompt` por nó, cadeia de fallback institutional/chitchat, seed) ganha testes unitários (fakes) e de integração (Postgres real via `TestClient`/repositório), cobrindo caminho feliz, isolamento por nó e por tenant, e o caminho de fallback. | PASS (ver Project Structure → tests) |

Nenhuma violação não justificada. Não é necessário preencher Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-guardrails-por-no/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── prompt-node-type.md
└── tasks.md               # Phase 2 output (/speckit.tasks — not created by this command)
```

### Source Code (repository root)

```text
app/
├── api/v1/endpoints/
│   └── prompt_manager.py         # MODIFIED: node_type em query params (/prompts, /tenant/{id}) e no
│                                   #   corpo de POST/PUT /prompts
└── schemas/
    └── prompt_manager.py         # MODIFIED: PromptCreateSchema.node_type, TenantPromptOverviewResponse.node_type

modules/
├── prompt_manager/
│   ├── prompt_manager_repository.py  # MODIFIED: node_type em create_prompt/update_prompt/get_all_prompts;
│   │                                   #   get_active_prompt_by_tenant(tenant_id, node_type); sync_tenant_prompt
│   │                                   #   escopado por node_type (research.md R2); get_default_prompt(node_type);
│   │                                   #   nova rotina idempotente ensure_node_type_schema() (ALTER TABLE/índice)
│   │                                   #   e seed_missing_node_prompts() (research.md R4/R5)
│   └── prompt_manager_service.py     # MODIFIED: get_tenant_prompt_details(tenant_id, node_type) com a cadeia
│                                       #   de fallback institutional→operational e chitchat→default→local
└── ia/
    └── agent_graph.py                # MODIFIED: institutional_node e chitchat_node passam a resolver
                                        #   prompt+guardrails via PromptManagerService (node_type próprio),
                                        #   mantendo o fallback local atual como última instância

prompts/
└── load_prompt.py                    # MODIFIED: novas funções carregar_institutional_prompt(tenant_id) e
                                        #   carregar_chitchat_prompt(tenant_id), espelhando
                                        #   carregar_operacional_prompt() já existente

tests/
├── unit/
│   ├── test_prompt_manager_fallback.py     # EXTENDED: casos institutional/chitchat fallback
│   └── test_prompt_manager_node_type.py    # NEW: validação de node_type, get_default_prompt por nó
└── integration/
    ├── test_prompt_manager_sync.py             # EXTENDED: caso "vincular chitchat não desativa operational"
    ├── test_prompt_manager_node_type_api.py     # NEW: contratos de prompt-node-type.md via TestClient
    └── test_prompt_manager_seed.py              # NEW: seed idempotente (institutional copiado, chitchat default único)
```

**Structure Decision**: Extensão pontual do módulo legado `prompt_manager` (Legacy Migration Policy —
reaproveita repositório/serviço existentes, sem reescrita) e ajuste dos nós `institutional_node`/
`chitchat_node` em `modules/ia/agent_graph.py` para consultar o mesmo serviço já usado por
`operational_node`. Nenhum módulo novo é criado; nenhuma tabela nova é criada (apenas uma coluna em `prompts`).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

Nenhuma violação — tabela não aplicável.

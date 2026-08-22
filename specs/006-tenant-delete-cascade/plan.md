# Implementation Plan: Exclusão segura de tenant com desvínculo/exclusão em cascata de prompts e guardrails

**Branch**: `edilsonaandrade/edi-45-backend-exclusao-segura-de-tenant-com-desvinculoexclusao-em` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/006-tenant-delete-cascade/spec.md`

## Summary

Hoje `DELETE /tenants/{id}` apaga a linha do tenant sem nenhuma verificação, deixando `tenant_prompts` órfão (não há FK) e sem decidir o destino dos prompts/guardrails associados. Esta feature adiciona: (1) uma FK real entre `tenant_prompts.tenant_id` e `tenants.id`; (2) uma orquestração que, ao excluir um tenant, exclui de fato prompts/guardrails exclusivos dele e apenas desvincula os compartilhados/globais, avaliando cada um independentemente, tudo em uma única transação atômica; (3) um endpoint de pré-visualização (`GET /tenants/{id}/delete-impact`) para a UI mostrar o impacto antes de confirmar. A abordagem técnica reaproveita ao máximo os métodos já existentes em `PromptManagerRepository` (criados no EDI-43 para os bloqueios de exclusão de prompt/guardrail), compartilhando uma única conexão/transação entre os dois módulos.

## Technical Context

**Language/Version**: Python 3.13, FastAPI
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg3 (`psycopg[binary]`), Alembic
**Storage**: PostgreSQL — tabelas existentes `tenants`, `prompts`, `guardrails`, `tenant_prompts`, `prompt_guardrails`
**Testing**: pytest — `tests/unit/` (lógica isolada, com repositórios substituídos por fakes) e `tests/integration/` (contrato HTTP real via `TestClient`/`httpx`), seguindo o padrão já usado pelo EDI-43 (`tests/integration/test_prompt_delete_guard_api.py`, `test_guardrail_delete_guard_api.py`)
**Target Platform**: Linux server, container Docker (mesmo processo da API existente)
**Project Type**: web-service (backend único, REST API `/api/v1`) — sem frontend neste repositório (Princípio II da constituição)
**Performance Goals**: nenhum requisito de performance especial; é uma operação administrativa de baixa frequência (SC-003 pede apenas "sob 1 segundo" para os cenários exclusivos, o que qualquer transação local já cumpre)
**Constraints**: a operação inteira DEVE ser atômica (FR-009) apesar de `infrastructure/connection.py::get_db_connection()` abrir conexões com `autocommit=True` — ver `research.md` §3 para a técnica escolhida (`conn.transaction()` do psycopg3)
**Scale/Scope**: uma migration nova, 2 métodos novos em `PromptManagerRepository`, 1 orquestração nova em `TenantService`/`TenantRepository`, 1 endpoint novo + 1 endpoint modificado, testes unitários + de integração

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
| -- | -- |
| I. Multi-Tenant Isolation | **PASS** — o próprio propósito da feature é impedir que excluir um tenant afete dados de outro (prompt/guardrail compartilhado é preservado). Nenhum novo caminho de acesso cross-tenant é criado. |
| II. API-First, Backend-Only | **PASS** — só adiciona/altera endpoints REST versionados (`/api/v1/tenants/...`) com schema Pydantic; nenhum código de UI. |
| III. Modular Clean Architecture | **PASS (módulo legado)** — `tenant` é módulo grandfathered (Legacy Migration Policy); a regra aplicável é "não embutir lógica de negócio no endpoint" e "depender dos métodos públicos já existentes de outro módulo em vez de acessar `infrastructure.connection` ou internos diretamente". A técnica de `research.md` §4 (compartilhar a conexão via uma factory que devolve a conexão já aberta) permite reaproveitar os métodos públicos existentes de `PromptManagerRepository` sem duplicar SQL nem violar a fronteira do módulo. |
| IV. Security & Guardrails by Default | **GAP PRÉ-EXISTENTE, fora de escopo** — nenhum endpoint de `tenant.py` (incluindo o `DELETE` atual) exige credencial administrativa hoje. Não é introduzido nem agravado por esta feature; corrigir autenticação em todos os endpoints de tenant é uma mudança transversal que merece feature própria (ver `research.md` §5). |
| V. Async Processing | **N/A** — exclusão de tenant é uma operação de banco rápida, não é workload de IA/embeddings/documento grande. |
| VI. Test-First Discipline | **PASS (planejado)** — Phase 2 (`/speckit.tasks`) vai gerar tarefas de teste unitário (orquestração com repositórios fake) E de integração (HTTP real, cobrindo caminho feliz, isolamento entre tenants, e erro 404) antes/junto da implementação. |

Nenhuma violação exige entrada na tabela de Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/006-tenant-delete-cascade/
├── plan.md              # Este arquivo
├── research.md          # Fase 0 — decisões técnicas
├── data-model.md         # Fase 1 — schema, entidades, fluxo de decisão
├── quickstart.md        # Fase 1 — validação manual passo a passo
├── contracts/
│   ├── tenant-delete-impact.md
│   └── tenant-delete-cascade.md
└── tasks.md             # Fase 2 (/speckit.tasks — ainda não gerado)
```

### Source Code (repository root)

Projeto único (backend Python/FastAPI existente) — sem opções alternativas de estrutura; arquivos reais tocados por esta feature:

```text
migrations/versions/
└── 0003_tenant_prompts_fk.py        # NOVO — FK tenant_prompts.tenant_id → tenants.id

modules/
├── tenant/
│   ├── tenant_repository.py         # MODIFICADO — delete_tenant participa da transação compartilhada
│   └── tenant_service.py            # MODIFICADO — nova orquestração de exclusão + cálculo de impacto
└── prompt_manager/
    └── prompt_manager_repository.py # MODIFICADO — 2 métodos novos (ver research.md §6):
                                      #   get_prompts_linked_to_tenant_active(tenant_id)
                                      #   get_guardrail_links_for_prompt(prompt_id)

app/
├── api/v1/endpoints/tenant.py       # MODIFICADO — DELETE usa a nova orquestração;
                                      #   novo GET /tenants/{id}/delete-impact
└── schemas/tenant.py                # MODIFICADO — novo response schema de delete-impact

tests/
├── unit/
│   └── test_tenant_delete_cascade.py         # NOVO — lógica de decisão com repositórios fake
└── integration/
    └── test_tenant_delete_cascade_api.py     # NOVO — contrato HTTP real (happy path,
                                                #   isolamento entre tenants, 404)
```

**Structure Decision**: segue a estrutura já existente do projeto (backend único, sem `src/`/`frontend/`); os módulos de negócio ficam em `modules/<nome>/`, os endpoints em `app/api/v1/endpoints/`, e os testes na já estabelecida separação `tests/unit/` vs `tests/integration/` (adotada a partir do EDI-43, mais recente que a descrição estática da Constituição).

## Complexity Tracking

*Nenhuma violação da Constituição exige justificativa nesta tabela.*

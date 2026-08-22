# Implementation Plan: Vínculo explícito de prompt e guardrails globais no runtime

**Branch**: `edilsonaandrade/edi-43-backend-eliminar-fallback-implicito-de-prompt-e-aplicar` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)
**Linear**: EDI-43 (backend) · EDI-44 (frontend, consome o contrato desta feature)
**Input**: Feature specification from `/specs/005-prompt-binding-guardrails/spec.md`

## Summary

Eliminar o fail-open silencioso na resolução de prompts em `prompts/load_prompt.py`, centralizando os quatro caminhos de fallback hoje duplicados numa única rotina. Tenant sem prompt `operational` vinculado passa a produzir exceção rastreável em vez de cair no `.md` local; os guardrails `is_global` passam a ser resolvidos do banco em todos os caminhos, inclusive nesse de erro. Os `.md` viram fonte de seed e só são lidos no `except` de indisponibilidade do banco. Complementarmente: `prompt_id` obrigatório no cadastro de tenant, associação em massa prompt→N tenants, proteção de `DELETE` contra orfanar tenants, e migration Alembic de backfill aplicada no mesmo deploy.

**Abordagem técnica**: um novo módulo `prompts/prompt_resolver.py` concentra a resolução (política) enquanto `load_prompt.py` mantém as quatro funções públicas (adaptação para cada nó) e os helpers de renderização já existentes e testados. Um `PromptConfigurationError` distingue "erro de configuração" (falha, alerta) de "banco fora do ar" (contingência) — hoje ambos caem no mesmo `except Exception`, que é a causa-raiz do fail-open.

## Technical Context

**Language/Version**: Python 3.11 (`Dockerfile`: `python:3.11-slim`)
**Primary Dependencies**: FastAPI ≥0.110, Pydantic v2 ≥2.6, psycopg 3 (`psycopg[binary]`), Alembic ≥1.13, LangChain/LangGraph (consumidores do prompt resolvido)
**Storage**: PostgreSQL — tabelas `tenants`, `prompts`, `guardrails`, `prompt_guardrails`, `tenant_prompts` (N:N já existente, criada em `migrations/versions/0001_baseline.py:131`)
**Testing**: pytest ≥8.0 — `tests/unit/` (fakes, sem banco) e `tests/integration/` (banco real, fixtures `repo` e `db_cleanup` em `tests/integration/conftest.py`). Runner: `test.sh` → `pytest tests/ -v`
**Target Platform**: container Linux atrás de proxy reverso compartilhado
**Project Type**: web-service (API REST backend-only, sem UI neste repositório)
**Performance Goals**: a resolução ocorre por atendimento; o número de queries por resolução não deve crescer em relação ao atual (hoje 2: prompt ativo + guardrails)
**Constraints**: indisponibilidade do banco NÃO pode derrubar o atendimento (FR-007); a migração não pode deixar tenant existente em estado de erro (FR-029)
**Scale/Scope**: 4 funções de resolução, 5 endpoints tocados, 1 migration, ~4 tenants/prompts por instalação típica

### Descobertas de código que alteram o escopo

Duas coisas encontradas durante o levantamento que a descrição do EDI-43 não previa:

**1. A divergência do `/overview` é maior que a descrita no ticket.**
`get_tenant_prompt_details` (`prompt_manager_repository.py:315-320`) busca guardrails com um `JOIN prompt_guardrails` puro, **sem** `OR g.is_global = TRUE`. Já `get_guardrails_by_prompt` (`:142`), usada no runtime, inclui os globais. Consequência: mesmo para um tenant **com** vínculo, a tela mostra menos guardrails do que o agente recebe. O ticket descreveu a divergência só no caso "sem vínculo". O FR-003/SC-002 exige o mesmo conjunto nos dois caminhos, então esta query também precisa ser corrigida.

**2. `TenantRepository` e `PromptManagerRepository` usam estilos de conexão incompatíveis.**
`TenantRepository.__init__` (`tenant_repository.py:5`) chama `get_db_connection()` uma vez e guarda a conexão viva, com `commit()` explícito. `PromptManagerRepository` recebe a *factory* e usa `with self.get_connection() as conn` por operação. Criar tenant + vínculo atomicamente (FR-018) atravessa os dois estilos. Tratado em Complexity Tracking.

## Constitution Check

Avaliado contra `.specify/memory/constitution.md` v1.1.0.

| Princípio | Status | Observação |
| -- | -- | -- |
| **I. Multi-Tenant Isolation** (NON-NEGOTIABLE) | ✅ Reforça | Esta feature existe justamente para eliminar um vazamento entre contextos: hoje um tenant sem vínculo recebe conteúdo genérico do projeto. O princípio diz textualmente que endpoint sem identidade de tenant "MUST reject the request rather than fall back to a shared default" — FR-004 aplica exatamente isso à resolução de prompt. |
| **II. API-First, Backend-Only** | ✅ Conforme | Nenhum código de UI. O contrato de erro estruturado (FR-026) é publicado como schema Pydantic; a tela é o EDI-44. |
| **III. Modular Clean Architecture** (NON-NEGOTIABLE para código novo) | ⚠️ Parcial — justificado | `prompt_manager` e `tenant` são módulos **legacy** explicitamente grandfathered pela Legacy Migration Policy. Nenhum módulo novo sob `modules/` é criado. As 3 regras da política são respeitadas: sem lógica de negócio no endpoint, sem SQL novo fora do repositório, e o código novo usa os métodos públicos existentes. Ver Complexity Tracking. |
| **IV. Security & Guardrails by Default** | ✅ Reforça | Guardrail é a defesa primária citada pelo princípio. FR-005 garante que a política de segurança não falha junto com o prompt; FR-023/024 impedem remoção silenciosa de proteção. |
| **V. Async para cargas pesadas** | ➖ N/A | Nada de embedding/LLM batch é adicionado. O seed continua no startup, síncrono e idempotente, como já é. |
| **VI. Test-First Discipline** (NON-NEGOTIABLE para código novo) | ✅ Conforme | SC-011 exige os quatro cenários de resolução. Unit em `tests/unit/`, integração em `tests/integration/`, cobrindo happy path, fronteira multi-tenant e caminho de erro, conforme o princípio. |

**Gate**: PASSA. A única ressalva (III) está coberta pela Legacy Migration Policy do próprio documento e registrada em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-prompt-binding-guardrails/
├── plan.md              # Este arquivo
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/           # Fase 1
│   ├── error-envelope.md
│   ├── tenant-create.md
│   ├── prompt-delete.md
│   ├── guardrail-delete.md
│   └── link-tenants-bulk.md
├── checklists/
│   └── requirements.md  # Já criado pelo /speckit.specify
└── tasks.md             # Fase 2 — criado pelo /speckit.tasks, NÃO por este comando
```

### Source Code (repository root)

```text
prompts/
├── prompt_resolver.py          # NOVO — resolução centralizada + PromptConfigurationError
├── load_prompt.py              # ALTERADO — 4 funções públicas passam a delegar; helpers preservados
├── operactional_prompt.md      # Passa a ser fonte de seed (e contingência)
├── institutional_prompt.md     # idem
├── chitchat_prompt.md          # idem
└── guardrails.md               # idem — origem do guardrail is_global semeado

modules/prompt_manager/
├── prompt_manager_repository.py  # ALTERADO — seed ampliado, guards de delete, link em massa,
│                                 #   correção do is_global em get_tenant_prompt_details
└── prompt_manager_service.py     # ALTERADO — erros de domínio + orquestração dos novos casos

modules/tenant/
├── tenant_repository.py          # ALTERADO — criação atômica de tenant + vínculo
└── tenant_service.py             # ALTERADO — validação do prompt antes de criar

app/
├── main.py                       # ALTERADO — seed deixa de ter conteúdo hardcoded
├── api/v1/endpoints/
│   ├── prompt_manager.py         # ALTERADO — deletes com 409, novo POST /link-tenants
│   └── tenant.py                 # ALTERADO — POST passa a exigir prompt_id
└── schemas/
    ├── prompt_manager.py         # ALTERADO — schemas de link em massa e de erro
    └── tenant.py                 # ALTERADO — TenantCreate.prompt_id

migrations/versions/
└── 0002_backfill_tenant_prompt_links.py   # NOVO — backfill antes da obrigatoriedade

tests/
├── unit/
│   ├── test_prompt_resolver.py            # NOVO — os 4 cenários do SC-011
│   ├── test_prompt_manager_fallback.py    # ALTERADO — /overview com globais
│   ├── test_load_prompt_institutional.py  # ALTERADO — fallback local só no except
│   └── test_load_prompt_chitchat.py       # ALTERADO — idem
└── integration/
    ├── test_prompt_delete_guard_api.py    # NOVO
    ├── test_guardrail_delete_guard_api.py # NOVO
    ├── test_link_tenants_bulk_api.py      # NOVO
    ├── test_tenant_create_requires_prompt_api.py  # NOVO
    ├── test_prompt_manager_seed.py        # ALTERADO — seed dos 3 nós + guardrail global
    └── test_tenant_prompt_overview_api.py # ALTERADO — paridade com o runtime
```

**Structure Decision**: mantida a estrutura atual do repositório (Interface `app/` → Service `modules/<x>/*_service.py` → Repository `modules/<x>/*_repository.py`), com `prompts/` como pacote de resolução de conteúdo. O único arquivo novo de produção é `prompts/prompt_resolver.py`, que isola a **política** de resolução (o que esta feature muda) das **funções de adaptação** por nó em `load_prompt.py` (o que os chamadores já conhecem). Nenhum módulo novo sob `modules/` é criado, o que mantém a feature dentro do perímetro legacy grandfathered.

## Phase 0 — Research

Ver [research.md](./research.md). Sete decisões consolidadas, sem `NEEDS CLARIFICATION` pendente: as três ambiguidades de escopo foram resolvidas com o solicitante antes do specify e estão em Assumptions da spec.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — entidades, invariantes e o que a migration de backfill precisa garantir. **Nenhuma alteração de DDL**: o modelo N:N já suporta tudo; a migration é só de dados.
- [contracts/](./contracts/) — os cinco contratos publicados no EDI-44, em formato verificável.
- [quickstart.md](./quickstart.md) — como validar localmente, com os comandos de teste para o usuário executar.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Lógica nova em módulos legacy (`prompt_manager`, `tenant`) sem migrar para Clean Architecture (Princípio III) | A Legacy Migration Policy grandfathera exatamente estes módulos e determina que correções de bug não exigem migrar o módulo inteiro antes. Esta feature é a correção de um defeito de segurança em produção. | Migrar `prompt_manager` para Domain/Application/Infrastructure com ports antes de corrigir o fail-open atrasaria uma correção de segurança por um refactor estrutural que a própria constituição adiou para um "regressão" futuro (`TODO(LEGACY_RETROFIT_PLAN)`). |
| `prompts/prompt_resolver.py` como módulo novo fora de `modules/` | `prompts/` já é o pacote de conteúdo/carregamento do projeto e `load_prompt.py` já vive lá. O resolver é a política de resolução desse conteúdo. | Criar `modules/prompt_resolution/` obrigaria conformidade total com Princípio III (sem grace period para módulo novo sob `modules/`) e espalharia a resolução de prompt por dois lugares. Manter em `prompts/` é coerente com o que já existe. |
| Criação atômica de tenant + vínculo atravessando dois repositórios com estilos de conexão diferentes | FR-018 exige atomicidade: um tenant criado sem vínculo é exatamente o estado que esta feature existe para eliminar. | Criar o tenant e depois vincular, com compensação por `DELETE` em caso de falha, deixa uma janela em que o estado proibido existe — e a compensação pode falhar. A validação prévia do prompt (FR-017) reduz mas não elimina a janela. Decisão: uma única transação, detalhada em research.md R6. |

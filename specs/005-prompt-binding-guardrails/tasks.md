---
description: "Task list for 005-prompt-binding-guardrails (EDI-43)"
---

# Tasks: Vínculo explícito de prompt e guardrails globais no runtime

**Input**: Design documents from `/specs/005-prompt-binding-guardrails/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Branch**: `edilsonaandrade/edi-43-backend-eliminar-fallback-implicito-de-prompt-e-aplicar`

**Tests**: incluídos e obrigatórios. SC-011 exige os quatro cenários de resolução, e o Princípio VI da constituição torna unit + integração não-negociáveis para código novo.

**Execução de testes**: conforme a regra MANDATORY do CLAUDE.md, os comandos de teste são **entregues ao usuário para execução**, não executados pelo agente.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1..US5, conforme spec.md

## Path Conventions

Projeto único na raiz do repositório: `app/` (interface), `modules/` (service + repository), `prompts/` (resolução de conteúdo), `migrations/` (Alembic), `tests/unit/` e `tests/integration/`.

---

## Phase 1: Setup

**Purpose**: estabelecer a linha de base antes de qualquer alteração

- [ ] T001 Entregar ao usuário o comando `pytest tests/ -v` e registrar, em uma nota de trabalho, quais testes já falham **antes** das mudanças — sem essa linha de base não é possível distinguir regressão introduzida de falha preexistente

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: peças compartilhadas por múltiplas histórias

**⚠️ CRÍTICO**: nenhuma história pode começar antes desta fase

- [X] T002 Criar `prompts/prompt_resolver.py` com a exceção `PromptConfigurationError` (carregando `tenant_id`, `node_type` e os guardrails já resolvidos) e a assinatura da função de resolução parametrizada por `node_type` e por exigência de vínculo — sem lógica ainda, apenas a estrutura e o docstring explicando a separação política/renderização (research.md R2)
- [X] T003 [P] Adicionar em `app/schemas/prompt_manager.py` os schemas do envelope de erro: `ErrorBlocker` (`type`, `id`, `name?`, `tenant_count?`), `ErrorDetail` (`code` como `Literal` dos seis códigos, `message`, `blockers`) e uma função fábrica que monta o `dict` para o `HTTPException(detail=...)` — ver `contracts/error-envelope.md`

**Checkpoint**: estrutura pronta; US1 e US2 podem começar (sequencialmente, pois ambas editam `prompt_resolver.py` e `load_prompt.py`)

---

## Phase 3: User Story 1 - Guardrails globais alcançam todo tenant (Priority: P1) 🎯 MVP

**Goal**: guardrail marcado como global passa a proteger todos os tenants, inclusive os sem prompt vinculado, e a tela passa a mostrar exatamente o que o agente aplica.

**Independent Test**: configurar um guardrail global, disparar a resolução para um tenant sem vínculo e verificar que o texto chegou ao conteúdo final; comparar `/overview` com o runtime para o mesmo tenant.

### Tests for User Story 1

- [X] T004 [P] [US1] Criar `tests/unit/test_prompt_resolver.py` com os cenários de guardrail: sem vínculo + com global (resolve os globais), sem vínculo + sem global (vazio, **sem** ler o `.md`), com vínculo + global (união sem duplicação). Usar fakes do repositório, sem banco — Princípio VI
- [X] T005 [P] [US1] Criar `tests/integration/test_overview_runtime_parity_api.py` afirmando que, para o mesmo tenant, o conjunto de guardrails de `GET /api/v1/prompt-manager/tenant/{id}` é idêntico ao resolvido em runtime — nos dois casos: com vínculo e sem vínculo (FR-003, SC-002)

### Implementation for User Story 1

- [X] T006 [US1] Implementar em `prompts/prompt_resolver.py` a resolução de guardrails: com prompt ativo usa `get_guardrails_by_prompt(prompt_id)` (que já inclui os globais via `OR g.is_global = TRUE`); sem prompt ativo usa `get_global_guardrails()`. Manter 2 queries por resolução, sem regressão de custo (research.md R3)
- [X] T007 [US1] Reescrever `carregar_guardrails` em `prompts/load_prompt.py:94` para delegar ao resolver, removendo o `return GUARDRAIL_PATH.read_text(...)` do caminho "sem prompt ativo" — mantendo a leitura do `.md` apenas no `except` (FR-001, FR-006)
- [X] T008 [US1] Corrigir a query de guardrails de `get_tenant_prompt_details` em `modules/prompt_manager/prompt_manager_repository.py:315-320` para incluir os globais. Preferir reusar `get_guardrails_by_prompt` em vez de replicar a cláusula — duas queries com a mesma regra foi como o bug nasceu (research.md R4)
- [X] T009 [US1] Atualizar `tests/unit/test_prompt_manager_fallback.py` para refletir que o `/overview` de um tenant **com** vínculo agora inclui os guardrails globais — trocar a asserção pelo novo comportamento, nunca afrouxá-la
- [X] T010 [US1] Atualizar `tests/integration/test_tenant_prompt_overview_api.py` pela mesma razão
- [ ] T011 [US1] Entregar ao usuário: `pytest tests/unit/test_prompt_resolver.py tests/unit/test_prompt_manager_fallback.py tests/integration/test_overview_runtime_parity_api.py tests/integration/test_tenant_prompt_overview_api.py -v`

**Checkpoint**: guardrails globais alcançam todos os tenants e a tela bate com o runtime. Entregável isoladamente — resolve o defeito de segurança mesmo sem as demais histórias.

---

## Phase 4: User Story 2 - Erro de configuração deixa de ser silencioso (Priority: P1)

**Goal**: tenant sem prompt `operational` vinculado passa a falhar de forma rastreável, com os guardrails globais ainda aplicados, e o `.md` deixa de ser alcançável fora do `except`.

**Independent Test**: remover o vínculo operacional de um tenant, disparar a resolução e verificar que houve alerta identificando o tenant, em vez do texto genérico do projeto.

**⚠️ Depende de US1**: edita os mesmos arquivos (`prompt_resolver.py`, `load_prompt.py`).

### Tests for User Story 2

- [X] T012 [P] [US2] Estender `tests/unit/test_prompt_resolver.py` com o cenário de erro: sem vínculo `operational` levanta `PromptConfigurationError`, a exceção **carrega os guardrails globais resolvidos** (FR-005), e o conteúdo do `.md` local não aparece em lugar nenhum
- [X] T013 [P] [US2] Criar `tests/unit/test_prompt_resolver_db_down.py` afirmando que uma falha de conexão (não um `PromptConfigurationError`) cai no `.md` local e **não** levanta exceção — o quarto cenário do SC-011, que é o que impede a correção de virar queda de produção
- [X] T014 [P] [US2] Adicionar teste que fixa a **ordem** dos blocos `except` (`PromptConfigurationError` antes de `Exception`). Se a ordem inverter, o fail-open volta silenciosamente — research.md R1

### Implementation for User Story 2

- [X] T015 [US2] Implementar em `prompts/prompt_resolver.py` o levantamento de `PromptConfigurationError` quando `node_type == "operational"` e não há vínculo ativo, resolvendo os guardrails **antes** de levantar e anexando-os à exceção (FR-004, FR-005)
- [X] T016 [US2] Reescrever `carregar_operacional_prompt` em `prompts/load_prompt.py:138` para delegar ao resolver, com `except PromptConfigurationError` antes de `except Exception`, e remover a chamada a `_carregar_fallback_local` do caminho "sem vínculo" — mantendo-a apenas no `except Exception` (FR-006, FR-007)
- [X] T017 [US2] Registrar o alerta rastreável no caminho de `PromptConfigurationError`, identificando o `tenant_id` e o `node_type`, seguindo o padrão de log já usado no arquivo (FR-004, SC-004)
- [X] T018 [US2] Migrar `carregar_institutional_prompt` (`prompts/load_prompt.py:191`) para o resolver, **preservando** a cadeia atual: sem vínculo institucional próprio usa o `.md` local mas com os guardrails vindos do banco, não mais do `guardrails.md` (FR-002, FR-008)
- [X] T019 [US2] Migrar `carregar_chitchat_prompt` (`prompts/load_prompt.py:234`) para o resolver, **preservando** o nível 2 pelo `is_default` (FR-002, FR-008) — este nó não exige vínculo
- [X] T020 [US2] Verificar que `_render_prompt`, `_montar_guardrails_str` e `_aplicar_guardrails` permanecem intactos e continuam sendo os únicos responsáveis pela renderização — eles carregam correções de bugs reais de produção (FR-009, FR-010, research.md R2)
- [X] T021 [US2] Atualizar `tests/unit/test_load_prompt_institutional.py` e `tests/unit/test_load_prompt_chitchat.py`, que hoje afirmam o fallback local que esta história elimina
- [ ] T022 [US2] Entregar ao usuário: `pytest tests/unit/test_prompt_resolver.py tests/unit/test_prompt_resolver_db_down.py tests/unit/test_load_prompt_institutional.py tests/unit/test_load_prompt_chitchat.py tests/integration/test_chitchat_node_guardrails.py tests/integration/test_institutional_node_guardrails.py -v`

**Checkpoint**: o fail-open silencioso está eliminado e o atendimento sobrevive a banco fora do ar. **Com US1 + US2 o defeito central do EDI-43 está corrigido** — é o MVP real da feature.

---

## Phase 5: User Story 3 - Banco sempre nasce com o mínimo configurado (Priority: P2)

**Goal**: instalação nova já sobe com um prompt por `node_type` e um guardrail global, vindos dos `.md`.

**Independent Test**: subir contra banco vazio e verificar que as listas de prompts e guardrails não voltam vazias.

- [X] T023 [P] [US3] Estender `tests/integration/test_prompt_manager_seed.py`: banco sem registros produz ≥1 prompt por `node_type` e ≥1 guardrail `is_global` (FR-011, FR-012)
- [X] T024 [P] [US3] Adicionar ao mesmo arquivo os testes de idempotência: rodar o seed duas vezes não altera contagens (FR-013), e conteúdo editado pelo admin sobrevive a um novo seed (FR-013, SC-007)
- [X] T025 [P] [US3] Adicionar teste afirmando que o conteúdo semeado preserva o placeholder `{guardrails}` cru — se o seed renderizar o texto, os guardrails congelam e deixam de ser injetados por atendimento (FR-014)
- [X] T026 [US3] Ampliar `seed_missing_node_prompts` em `modules/prompt_manager/prompt_manager_repository.py:213` para receber o conteúdo dos quatro `.md` e garantir um prompt por `node_type` mais um guardrail `is_global=TRUE`. Critério de existência: `SELECT ... LIMIT 1` por `node_type`, e para o guardrail a existência de qualquer `is_global = TRUE` — nunca o título, que o admin pode renomear (research.md R5)
- [X] T027 [US3] Preservar a cópia operational→institucional que o seed já faz em `prompt_manager_repository.py:240-286` (comportamento do EDI-42) — a ampliação não pode quebrá-la
- [X] T028 [US3] Alterar `seed_node_type_prompts` em `app/main.py:123` para ler os quatro arquivos de `prompts/` e repassá-los, removendo o conteúdo hardcoded. Manter o `try/except` que impede uma falha de seed de derrubar o boot (FR-015)
- [ ] T029 [US3] Entregar ao usuário: `pytest tests/integration/test_prompt_manager_seed.py -v`, mais a validação de banco vazio descrita em `quickstart.md`

**Checkpoint**: instalação nova é utilizável sem configuração manual prévia.

---

## Phase 6: User Story 4 - Cadastro exige prompt e associação em massa (Priority: P2)

**Goal**: `POST /tenants/` passa a exigir `prompt_id` operacional, atomicamente; e um prompt pode ser aplicado a N tenants numa operação.

**Independent Test**: cadastrar sem prompt e verificar recusa; associar um prompt a três tenants numa chamada e verificar os três vínculos.

**Depende de US3 na prática** (a lista de escolha precisa não estar vazia), embora testável isoladamente criando um prompt à mão.

- [X] T030 [P] [US4] Criar `tests/integration/test_tenant_create_requires_prompt_api.py` cobrindo a matriz de `contracts/tenant-create.md`: `422` sem `prompt_id`, `404 PROMPT_NOT_FOUND`, `400 PROMPT_NODE_TYPE_INVALID`, sucesso com vínculo ativo, e **nenhum tenant criado** em cada caminho de erro
- [X] T031 [P] [US4] Adicionar ao mesmo arquivo o teste de atomicidade: falha simulada no `INSERT` do vínculo não deixa tenant algum no banco (FR-018)
- [X] T032 [P] [US4] Criar `tests/integration/test_link_tenants_bulk_api.py` cobrindo a matriz de `contracts/link-tenants-bulk.md`, incluindo o all-or-nothing com um tenant inexistente e a preservação de vínculos de outros `node_type` (FR-020, FR-021)
- [X] T033 [P] [US4] Adicionar `prompt_id: str` obrigatório em `TenantCreate` (`app/schemas/tenant.py:13`) e os schemas `BulkTenantPromptLinkSchema` (`prompt_id`, `tenant_ids` com `min_length=1`, `custom_content_override`) e a resposta correspondente em `app/schemas/prompt_manager.py`
- [X] T034 [US4] Implementar em `modules/tenant/tenant_repository.py` a criação atômica: os `INSERT` em `tenants` e `tenant_prompts` na mesma conexão com um único `commit()` e `rollback()` em falha. Documentar no docstring **por que** a transação é compartilhada, para que ninguém "corrija" separando os dois e reabra a janela (research.md R6)
- [X] T035 [US4] Implementar em `modules/tenant/tenant_service.py` a validação do prompt antes de qualquer escrita (existe? é `operational`?), levantando erros de domínio distintos para cada caso
- [X] T036 [US4] Ajustar `POST /` em `app/api/v1/endpoints/tenant.py:17` para traduzir os erros de domínio nos `404`/`400` do envelope estruturado
- [X] T037 [US4] Implementar `link_tenants_bulk` em `modules/prompt_manager/prompt_manager_repository.py`, numa transação única, reaproveitando a semântica de `sync_tenant_prompt:89` (desativa os do mesmo `node_type`, preserva os demais)
- [X] T038 [US4] Implementar o caso de uso correspondente em `modules/prompt_manager/prompt_manager_service.py`, validando prompt e tenants **antes** de escrever e devolvendo os não encontrados como `blockers`
- [X] T039 [US4] Adicionar `POST /link-tenants` em `app/api/v1/endpoints/prompt_manager.py`, mantendo o `/link-tenant` singular (`:53`) inalterado
- [ ] T040 [US4] Entregar ao usuário: `pytest tests/integration/test_tenant_create_requires_prompt_api.py tests/integration/test_link_tenants_bulk_api.py tests/integration/test_prompt_manager_sync.py -v`

**Checkpoint**: tenants novos nascem sempre vinculados, e a associação em massa funciona.

---

## Phase 7: User Story 5 - Exclusão não orfana tenant nem remove proteção (Priority: P2)

**Goal**: `DELETE` de prompt em uso e de guardrail global/em uso passam a ser recusados com o caminho de saída explícito.

**Independent Test**: tentar excluir um prompt vinculado e o guardrail global; verificar as recusas e os `blockers`.

- [X] T041 [P] [US5] Criar `tests/integration/test_prompt_delete_guard_api.py` cobrindo `contracts/prompt-delete.md`: `409` com 1 e com N vínculos ativos, `204` com vínculos só inativos, `204` sem vínculo, e a verificação de que após um `409` prompt e vínculos continuam intactos
- [X] T042 [P] [US5] Criar `tests/integration/test_guardrail_delete_guard_api.py` cobrindo `contracts/guardrail-delete.md`, incluindo os dois códigos, a **precedência** de `GUARDRAIL_IS_GLOBAL` quando ambas as condições valem (FR-025), e o caminho de saída (desmarcar global → excluir)
- [X] T043 [US5] Implementar em `modules/prompt_manager/prompt_manager_repository.py` a consulta dos tenants que bloqueiam um prompt (`tenant_prompts` com `is_active = TRUE`), retornando `id` e `name` de cada um para os `blockers`
- [X] T044 [US5] Implementar no mesmo arquivo a consulta dos prompts que bloqueiam um guardrail (associados via `prompt_guardrails` e com tenant ativo), retornando `id`, `name` e `tenant_count`
- [X] T045 [US5] Alterar `delete_prompt` (`prompt_manager_repository.py:196`) para não mais apagar `tenant_prompts` em cascata quando houver vínculo ativo — a cascata permanece válida apenas para vínculos inativos
- [X] T046 [US5] Alterar `delete_guardrail` (`prompt_manager_repository.py:205`) pela mesma lógica, com o teste de `is_global` tendo precedência
- [X] T047 [US5] Adicionar em `modules/prompt_manager/prompt_manager_service.py` os erros de domínio para os três bloqueios, carregando os `blockers`
- [X] T048 [US5] Ajustar os endpoints `delete_prompt` (`app/api/v1/endpoints/prompt_manager.py:78`) e `delete_guardrail` (`:96`) para retornar `409` com o envelope estruturado, preservando o `204` e o `404` atuais
- [ ] T049 [US5] Entregar ao usuário: `pytest tests/integration/test_prompt_delete_guard_api.py tests/integration/test_guardrail_delete_guard_api.py tests/integration/test_delete_guardrail_api.py -v`

**Checkpoint**: o invariante INV-2 não pode mais ser destruído pela área administrativa.

---

## Phase 8: Migração & Polish

**Purpose**: garantir que a produção existente atravesse o deploy sem tenant em estado de erro

- [X] T050 Criar `migrations/versions/0002_backfill_tenant_prompt_links.py` associando todo tenant sem vínculo `operational` ativo ao prompt `is_default` operacional. Seleção determinística por `created_at` (não herdar o `LIMIT 1` sem `ORDER BY` de `get_default_prompt:171`); `ON CONFLICT ... DO UPDATE SET is_active = TRUE`; **não falhar** quando não houver prompt `is_default` — é o estado legítimo de instalação nova, e falhar derrubaria a subida do container (research.md R7, data-model.md)
- [X] T051 Implementar o `downgrade` removendo apenas os vínculos criados pela própria migration, nunca os preexistentes
- [ ] T052 [P] Criar `tests/integration/test_backfill_migration.py`: tenant sem vínculo passa a ter vínculo; rodar duas vezes é idempotente; banco sem prompt `is_default` não falha (FR-028, FR-029, SC-010)
- [ ] T053 [P] Verificar que `tests/unit/test_alembic_revisions.py` e `tests/unit/test_no_runtime_ddl.py` continuam passando com a revision nova
- [ ] T054 Executar o roteiro completo de `quickstart.md`, entregando os comandos ao usuário — incluindo a validação de banco vazio, a de idempotência do seed e a checagem manual dos três formatos de erro
- [ ] T055 Entregar ao usuário a suíte completa: `pytest tests/ -v`, comparando com a linha de base de T001 para confirmar zero regressão
- [ ] T056 Marcar os checkboxes de escopo no EDI-43 e comentar o resultado; confirmar no EDI-44 que o contrato implementado bate com o publicado — se algo divergiu na implementação, o comentário do contrato precisa ser corrigido antes de o frontend começar

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sem dependências
- **Foundational (Fase 2)**: depende do Setup — **bloqueia todas as histórias**
- **US1 (Fase 3)** → **US2 (Fase 4)**: sequenciais, editam os mesmos arquivos
- **US3 (Fase 5)**, **US4 (Fase 6)**, **US5 (Fase 7)**: independentes entre si após a Fase 2; US4 depende de US3 na prática (lista de escolha não vazia), não em código
- **Migração & Polish (Fase 8)**: depende de US4 (a obrigatoriedade que o backfill precede)

### Ordem recomendada

```
Fase 1 → Fase 2 → US1 → US2  ← aqui o defeito central do EDI-43 está corrigido
                     ↓
              US3 → US4 → Fase 8
                     ↓
                    US5
```

### Within Each User Story

- Testes escritos antes da implementação, e devem **falhar** antes dela
- Repository antes de service, service antes de endpoint
- Testes que hoje afirmam o fallback local são **alterados**, nunca afrouxados

### Parallel Opportunities

- T002 e T003 (Fase 2) — arquivos diferentes
- T004 e T005 (US1) — arquivos de teste diferentes
- T012, T013, T014 (US2) — testes independentes
- T023, T024, T025 (US3) — mesmo arquivo de teste, mas casos independentes; paralelizáveis se escritos como funções separadas
- T030, T031, T032, T033 (US4)
- T041 e T042 (US5)
- T052 e T053 (Fase 8)
- Após a Fase 2, US3/US4/US5 podem ser tocadas por pessoas diferentes; US1 e US2 não, pois disputam `load_prompt.py`

---

## Parallel Example: User Story 5

```bash
# Os dois arquivos de teste de bloqueio são independentes:
Task: "Criar tests/integration/test_prompt_delete_guard_api.py"
Task: "Criar tests/integration/test_guardrail_delete_guard_api.py"

# As duas consultas de blockers tocam o mesmo repositório — sequenciais:
# T043 (tenants que bloqueiam prompt) → T044 (prompts que bloqueiam guardrail)
```

---

## Implementation Strategy

### MVP: US1 + US2

Diferente do padrão "US1 é o MVP": aqui as duas histórias P1 formam o incremento mínimo com sentido. US1 sozinha faz os guardrails globais alcançarem todos, mas o prompt genérico continuaria vazando silenciosamente; US2 sozinha faria o tenant sem vínculo falhar sem a rede de proteção que FR-005 exige. Juntas, corrigem o defeito descrito no EDI-43.

1. Fase 1 → Fase 2 → US1 → US2
2. **PARAR e VALIDAR**: os quatro cenários do SC-011
3. Este ponto já é implantável — desde que a Fase 8 (backfill) vá junto, senão tenants existentes sem vínculo passam a dar erro

⚠️ **US2 e Fase 8 são inseparáveis no deploy.** Ativar a exigência sem o backfill quebra produção; é o alerta da seção Migração do EDI-43.

### Entrega incremental

1. Fase 2 → fundação pronta
2. US1 + US2 + Fase 8 → defeito corrigido, produção segura ← primeiro deploy
3. US3 → instalação nova utilizável
4. US4 → tenants novos nascem vinculados; desbloqueia o EDI-44
5. US5 → o invariante fica protegido contra a área administrativa

---

## Notes

- `[P]` = arquivos diferentes, sem dependência pendente
- Os testes de `tests/unit/test_load_prompt_*.py` e `tests/integration/test_tenant_prompt_overview_api.py` **precisam mudar** — eles afirmam hoje o comportamento que a feature elimina. Trocar a asserção pelo novo comportamento; afrouxá-la para "passar" anula o valor do teste
- Fixtures de integração disponíveis em `tests/integration/conftest.py`: `repo` e `db_cleanup` (rastreia e limpa tenants/prompts/guardrails criados, mesmo com o teste falhando)
- A ordem dos blocos `except` em `load_prompt.py` é a garantia de toda a feature — daí o teste dedicado em T014

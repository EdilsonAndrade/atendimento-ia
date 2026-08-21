# Implementation Plan: Migrations versionadas do schema PostgreSQL (EDI-37)

**Branch**: `edilsonaandrade/edi-37-configurar-migrations-e-acesso-sql-do-projeto` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/004-alembic-migrations/spec.md`
**Linear**: [EDI-37](https://linear.app/edilsonandrade/issue/EDI-37/configurar-migrations-e-acesso-sql-do-projeto)

> **Nota sobre o nome da branch**: a regra do projeto (CLAUDE.md) exige que a branch carregue o nome da issue do Linear, que não segue o padrão numérico do Spec Kit. Os scripts do Spec Kit são executados com `SPECIFY_FEATURE=004-alembic-migrations`, e o diretório desta feature está registrado em `.specify/feature.json`.

## Summary

Adotar **Alembic** como versionador do schema PostgreSQL, mantendo **psycopg** como driver de todas as consultas. A migração `0001_baseline` é um espelho fiel da estrutura de produção, escrita em SQL literal; em produção ela é apenas **registrada** (`alembic stamp`), nunca executada, garantindo zero risco aos dados. Um `ENTRYPOINT` no contêiner aplica migrações pendentes antes de a aplicação subir — necessário porque o `command:` do `docker-compose.yml` substitui o `CMD`, fazendo o `start.sh` atual **não rodar em produção**. Por fim, as quatro rotinas que hoje executam DDL em tempo de execução são removidas, tornando as migrações a única fonte de verdade do schema.

## Technical Context

**Language/Version**: Python 3.11 (imagem de produção) / 3.13 (desenvolvimento)
**Primary Dependencies**: `alembic>=1.13` (**nova**), SQLAlchemy 2.0.45 (já presente, usada só pelo Alembic), psycopg 3.2.9 (driver de todas as consultas, inalterado), FastAPI
**Storage**: PostgreSQL **15.18** em produção (17.x em desenvolvimento) — 9 tabelas do projeto + 6 tabelas de bibliotecas de terceiros
**Testing**: pytest — `tests/unit/` (sem banco, executado pelo CI de deploy) e `tests/integration/` (exige PostgreSQL, execução local)
**Target Platform**: contêiner Linux ARM64 (VM Oracle Ampere Altra), imagem publicada no GHCR, orquestrada por `docker-compose.yml`
**Project Type**: web service (API FastAPI backend-only)
**Performance Goals**: deploy contra banco já atualizado adiciona **< 5 s** ao tempo de subida (SC-006)
**Constraints**: produção com dados reais de clientes — **zero perda tolerada**; a aplicação precisa funcionar com usuário de banco **sem permissão de DDL** (SC-004); segredos não podem ser versionados
**Scale/Scope**: 1 arquivo de configuração, 1 `env.py`, 1 migração de baseline, 1 script de entrypoint, 4 rotinas de DDL removidas, ~6 testes novos

## Constitution Check

*GATE: avaliado antes da Phase 0 e reavaliado após a Phase 1 design.*

| Princípio | Situação | Justificativa |
|---|---|---|
| **I. Multi-Tenant Isolation** (NON-NEGOTIABLE) | ✅ PASS | Impacto **nulo por construção**: a baseline reproduz exatamente a estrutura já em produção. Todas as colunas `tenant_id` (`agendamentos`, `tenant_prompts`, `whatsapp_instances`, `tenant_knowledge_base`), a chave `tenants.id` e os índices de lookup por tenant permanecem idênticos em tipo, restrição e granularidade. O armazenamento vetorial por tenant fica fora do controle do Alembic e segue intocado, assim como `db/<tenant_id>/knowledge_db/`. As rotinas de DDL removidas criavam estrutura global, nunca dados ou estrutura por tenant. Detalhamento em [research.md R11](./research.md). |
| **II. API-First, Backend-Only** | ✅ PASS | Nenhum endpoint, schema ou código de UI é criado ou alterado. A interface entregue é operacional (comandos de migração), documentada em [contracts/migration-cli.md](./contracts/migration-cli.md). |
| **III. Modular Clean Architecture** (NON-NEGOTIABLE para código novo) | ✅ PASS | `migrations/` é infraestrutura de build/deploy, não um `modules/<name>/` de negócio — não introduz lógica de domínio nem inverte dependências. Nos módulos tocados a mudança é **subtrativa**: remover `_ensure_table()` de `PostgresKnowledgeBaseRepository` (módulo que já segue domain/application/infrastructure) reduz responsabilidade do adaptador sem alterar sua porta. Nenhuma regra de negócio nova entra em módulo legado. |
| **IV. Security & Guardrails by Default** | ✅ PASS | `alembic.ini` mantém `sqlalchemy.url` vazio — nenhuma credencial versionada; a URL vem de `POSTGRES_DATABASE_URI`, sem fallback embutido. O `downgrade` da baseline é travado por variável de ambiente explícita, protegendo contra perda total de dados. Nenhum prompt ou guardrail da IA é alterado. |
| **V. Async Processing for Heavy Workloads** | ✅ PASS (melhora) | Nada novo entra no caminho da requisição. Ao contrário: a mudança **remove** `ALTER TABLE` que hoje roda em 8 métodos do `PromptManagerRepository` durante o atendimento de requisições. |
| **VI. Test-First Discipline** (NON-NEGOTIABLE para código novo) | ✅ PASS | Nenhum endpoint ou service novo é criado, mas a feature entrega os dois níveis mesmo assim: 3 testes unitários (normalização de URL, cadeia de revisões, teste-guarda anti-regressão de DDL) executados pelo CI, e 3 testes de integração contra banco real. Ver [research.md R9](./research.md). |
| **Quality Gate: mudança de schema documenta impacto multi-tenant** | ✅ PASS | Documentado em research.md R11, nesta tabela (Princípio I) e em [data-model.md](./data-model.md). |

**Resultado pré-Phase 0**: PASS, sem violações.
**Resultado pós-Phase 1**: PASS, sem violações. O design não introduziu novas camadas, dependências de negócio ou acoplamentos — a única dependência nova (`alembic`) é ferramenta de infraestrutura e sua transitiva pesada (SQLAlchemy) já estava no projeto.

## Project Structure

### Documentation (this feature)

```text
specs/004-alembic-migrations/
├── plan.md                     # Este arquivo
├── spec.md                     # Especificação (/speckit.specify)
├── research.md                 # Phase 0 — 11 decisões técnicas
├── data-model.md               # Phase 1 — baseline do schema
├── quickstart.md               # Phase 1 — guia operacional
├── contracts/
│   └── migration-cli.md        # Phase 1 — contrato dos comandos e do entrypoint
├── checklists/
│   └── requirements.md         # Validação de qualidade do spec
└── tasks.md                    # Phase 2 (/speckit.tasks — NÃO criado aqui)
```

### Source Code (repository root)

```text
alembic.ini                     # NOVO — config; sqlalchemy.url vazio, file_template sequencial
docker-entrypoint.sh            # NOVO — alembic upgrade head && exec "$@"
migrations/                     # NOVO
├── env.py                      #   URL normalizada p/ psycopg 3, advisory lock, include_object
├── script.py.mako              #   template de novas revisões
└── versions/
    └── 0001_baseline.py        #   espelho fiel de produção (SQL literal via op.execute)

Dockerfile                      # ALTERADO — ENTRYPOINT ["/app/docker-entrypoint.sh"]
requirements.txt                # ALTERADO — + alembic>=1.13

modules/
├── prompt_manager/prompt_manager_repository.py    # ALTERADO — remove ensure_node_type_schema() e suas 8 chamadas
├── ia/thread_session.py                           # ALTERADO — remove init_thread_sessions_table() e sua chamada
├── agendamento/booking_tools.py                   # ALTERADO — remove init_booking_table() e suas chamadas
├── agendamento/agenda_tool.py                     # ALTERADO — remove import e chamada de init_booking_table()
└── knowledge_base/infrastructure/
    └── postgres_knowledge_base_repository.py      # ALTERADO — remove _TABLE_DDL e _ensure_table()

tests/
├── unit/
│   ├── test_alembic_env_url.py         # NOVO — normalização da URL
│   ├── test_alembic_revisions.py       # NOVO — integridade da cadeia de revisões
│   └── test_no_runtime_ddl.py          # NOVO — teste-guarda anti-regressão
└── integration/
    └── test_migrations_baseline.py     # NOVO — upgrade em banco vazio, idempotência, gatilhos
```

**Structure Decision**: mantida a estrutura atual do repositório (API FastAPI backend-only com `app/`, `modules/`, `infrastructure/`, `tests/`). A feature adiciona apenas artefatos de infraestrutura na raiz — `alembic.ini`, `docker-entrypoint.sh` e o pacote `migrations/`. Diretório nomeado `migrations/` em vez do `alembic/` padrão porque descreve o conteúdo e não se confunde com o pacote da biblioteca. Nenhum `modules/<name>/` novo é criado, logo o Princípio III não impõe estrutura de camadas aqui.

## Ordem de implementação e dependências

As histórias do spec são entregues em 4 fases, e a ordem importa — a fase 4 só é segura depois que 1 a 3 estiverem funcionando.

| Fase | História | Entrega | Depende de |
|---|---|---|---|
| **1** | US1 (P1) | `alembic` no requirements, `alembic.ini`, `migrations/env.py`, `0001_baseline.py`, testes unitários | — |
| **2** | US2 (P1) | Procedimento de `stamp` validado em clone de produção + documentação no quickstart | Fase 1 |
| **3** | US3 (P2) | `docker-entrypoint.sh`, `ENTRYPOINT` no Dockerfile | Fase 1 |
| **4** | US4 (P3) | Remoção das 4 rotinas de DDL em runtime + teste-guarda | Fases 1–3 **em produção** |

> **Ponto de atenção operacional**: a fase 4 não pode ser mesclada antes de a fase 2 estar aplicada no banco de produção. Se o DDL em runtime sumir do código enquanto produção ainda não estiver sob controle das migrações, um banco novo levantado nesse intervalo ficaria sem tabelas.

## Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Baseline diverge da estrutura real de produção | O histórico passa a mentir; migrações futuras falham | Passo obrigatório de conferência (`pg_dump --schema-only`) **antes** do `stamp`, documentado no quickstart Cenário 1 |
| `alembic upgrade` em produção antes do `stamp` | Erro `relation already exists`, deploy vermelho | Ordem documentada; a fase 2 é executada manualmente e verificada antes de a fase 3 entrar |
| SQLAlchemy tenta usar psycopg2, ausente na imagem | Deploy quebra no boot, 100% indisponibilidade | Normalização da URL no `env.py` + teste unitário no CI ([research.md R2](./research.md)) |
| `downgrade base` executado por engano em produção | **Perda total** dos dados | Trava por variável de ambiente no `downgrade()` da baseline ([research.md R5](./research.md)) |
| Duas instâncias migrando simultaneamente | Deploy falha de forma confusa | Advisory lock transacional no `env.py` ([research.md R6](./research.md)) |
| DDL em runtime volta a ser adicionado no futuro | Retorno silencioso ao problema original | Teste-guarda no CI que varre o código-fonte ([research.md R9](./research.md)) |

## Complexity Tracking

> Preenchido apenas se o Constitution Check apresentar violações a justificar.

**Nenhuma violação.** Todos os sete itens do gate passam. A tabela permanece vazia intencionalmente.

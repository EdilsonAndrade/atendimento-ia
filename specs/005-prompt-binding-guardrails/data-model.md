# Phase 1 — Data Model: Vínculo explícito de prompt e guardrails globais

**Feature**: 005-prompt-binding-guardrails · **Plan**: [plan.md](./plan.md)

**Nenhuma alteração de DDL nesta feature.** O modelo N:N já suporta tudo o que os requisitos pedem. A única migration é de **dados** (backfill). Isto é intencional: o EDI-43 afirma que o modelo `tenant_prompts` já suporta associação em massa "sem migração", e o levantamento confirmou.

## Entidades

### `tenants`

| Campo | Observação |
| -- | -- |
| `id` | Identificador do tenant (texto, informado pelo cliente — não é UUID gerado) |
| `name`, `google_calendar_id`, `allowed_domains`, `created_at`, `updated_at`, `deleted_at` | Inalterados |

**Muda o contrato, não a tabela**: a criação passa a exigir um `prompt_id` de `node_type = 'operational'` (FR-016). O campo não é persistido em `tenants` — ele vira uma linha em `tenant_prompts` na mesma transação (FR-018).

### `prompts`

| Campo | Observação |
| -- | -- |
| `id` | UUID |
| `titulo`, `conteudo` | `conteudo` armazena o template **cru**, com `{guardrails}` intacto (FR-014) |
| `is_default` | **Muda de papel.** Deixa de ser mecanismo de resolução de runtime para o nó operational. Continua válido para o nó chitchat (nível 2, mantido) e como origem do backfill (R7). |
| `node_type` | `operational` \| `institutional` \| `chitchat` |

### `guardrails`

| Campo | Observação |
| -- | -- |
| `id` | UUID |
| `titulo`, `conteudo` | Conteúdo, nunca template — `{guardrails}` dentro do texto é removido na montagem |
| `is_global` | Aditivo. Aplica a todos os tenants sem associação manual. **Passa a bloquear exclusão** (FR-023). |

### `prompt_guardrails` (N:N)

Associação explícita prompt↔guardrail. Não confundir com o alcance dos globais: um guardrail `is_global` **não tem linha aqui** e mesmo assim se aplica a todos. Essa distinção é a razão de o critério de bloqueio de exclusão precisar dos dois testes (FR-023 + FR-024) — checar só a associação deixaria o guardrail global desprotegido.

### `tenant_prompts` (N:N)

| Campo | Observação |
| -- | -- |
| `tenant_id`, `prompt_id` | Chave composta única (há `ON CONFLICT (tenant_id, prompt_id)` no código atual) |
| `is_active` | No máximo um ativo por tenant **por node_type** |
| `custom_content_override` | Conteúdo específico do tenant; quando presente, vence o `conteudo` do prompt |

## Invariantes

| # | Invariante | Requisito | Onde é garantido |
| -- | -- | -- | -- |
| INV-1 | No máximo um vínculo ativo por tenant por `node_type` | FR-021 | `sync_tenant_prompt` já desativa os do mesmo `node_type` antes de ativar o novo |
| INV-2 | Todo tenant tem vínculo `operational` ativo | FR-016, FR-028 | Criação atômica (novos) + migration de backfill (existentes) + guards de DELETE (permanência) |
| INV-3 | Um prompt com vínculo ativo não pode ser excluído | FR-022 | Guard no DELETE — substitui o `DELETE` em cascata atual |
| INV-4 | Um guardrail `is_global` ou em uso não pode ser excluído | FR-023, FR-024 | Guard no DELETE, com `is_global` tendo precedência |
| INV-5 | Existe ao menos um prompt por `node_type` e um guardrail `is_global` | FR-011, FR-012 | Seed idempotente no startup |
| INV-6 | O conjunto de guardrails do `/overview` é igual ao do runtime | FR-003 | Ambos os caminhos passam a incluir `is_global` |

**INV-2 é o coração da feature.** As três defesas são complementares e nenhuma sozinha basta: o cadastro cobre tenants novos, o backfill cobre os existentes, e os guards de DELETE impedem que o invariante seja destruído depois. Sem a terceira, uma exclusão na tela de administração reabre exatamente o buraco que as outras duas fecharam.

## Matriz de resolução em runtime (o que muda)

| Nó | Com vínculo próprio | Sem vínculo próprio — **hoje** | Sem vínculo próprio — **depois** |
| -- | -- | -- | -- |
| `operational` | prompt do vínculo + guardrails (próprios ∪ globais) | ⚠️ `.md` local + `guardrails.md` | ❌ `PromptConfigurationError` + alerta; guardrails globais ainda resolvidos |
| `institutional` | prompt do vínculo + guardrails (próprios ∪ globais) | `.md` local + guardrails resolvidos pelo operational | `.md` local + **guardrails globais do banco** (herança mantida, FR-008) |
| `chitchat` | prompt do vínculo + guardrails (próprios ∪ globais) | prompt `is_default` do banco; se não houver, `.md` local | prompt `is_default` do banco (garantido pelo seed) + guardrails do banco |
| *qualquer* | — | `.md` local | **banco indisponível**: `.md` local (única leitura de arquivo em runtime, FR-007) |

A coluna do meio é o defeito: em três das quatro linhas, conteúdo de arquivo do projeto era entregue como se fosse configuração do cliente.

## Migration de dados: `0002_backfill_tenant_prompt_links`

**Upgrade** — para cada tenant sem vínculo `operational` ativo, criar o vínculo com o prompt `is_default = TRUE` de `node_type = 'operational'`:

- Seleção determinística do default: ordenar por `created_at` e pegar o primeiro. `get_default_prompt` usa `LIMIT 1` sem `ORDER BY`, o que pode variar entre execuções se houver mais de um `is_default` — a migration não pode herdar essa indeterminação.
- **Se não existir nenhum prompt `is_default` operational**: não fazer nada e não falhar. É o estado legítimo de instalação nova; o seed do startup cria o prompt semente logo em seguida. Falhar aqui derrubaria a subida do container.
- Usar `ON CONFLICT (tenant_id, prompt_id) DO UPDATE SET is_active = TRUE` para tolerar vínculos inativos preexistentes.
- Idempotente: rodar duas vezes não altera o resultado.

**Downgrade** — remover apenas os vínculos criados pela própria migration, nunca os que já existiam.

## Impacto na isolação multi-tenant

Exigido pelo Development Workflow da constituição ("Database schema or vector-store layout changes MUST document tenant-isolation impact explicitly").

Nenhuma partição por tenant é alterada — não há DDL. O efeito é de **reforço** do Princípio I: hoje, tenants sem vínculo compartilham um mesmo conteúdo genérico vindo dos arquivos do projeto, que é a definição de "fall back to a shared default" que o princípio proíbe. Depois, cada tenant só recebe conteúdo explicitamente vinculado a ele, e a ausência de vínculo é rejeitada em vez de absorvida.

Os guardrails `is_global` são a exceção deliberada e correta: são política **da plataforma**, não dado **de tenant**, e por isso devem mesmo alcançar todos.

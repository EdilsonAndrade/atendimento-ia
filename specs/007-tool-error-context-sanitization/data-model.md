# Data Model: Sanitização do contexto de conversa enviado ao LLM

## chat_thread_summaries (nova tabela — US4)

| Coluna | Tipo | Notas |
| --- | --- | --- |
| `id` | `serial primary key` | |
| `base_thread_id` | `varchar(255)` | mesma chave usada em `chat_thread_sessions.base_thread_id`; sem FK formal (tabela `chat_thread_sessions` não tem PK única exposta além do próprio `base_thread_id`, que não é declarado unique hoje — ver nota abaixo) |
| `resumo` | `text` | resumo curto (~200 tokens) gerado ao fim/expiração da sessão |
| `fatos_estruturados` | `jsonb` | `{"nome": str \| null, "interesse": str \| null, "objecao": str \| null, "resultado": str \| null}` — campos ausentes/nulos quando não identificáveis (FR-011) |
| `sessao_thread_id` | `varchar(255)` | o `active_thread_id` da sessão que gerou este resumo, para rastreabilidade |
| `created_at` | `timestamptz not null default now()` | |

Índice: `CREATE INDEX ON chat_thread_summaries (base_thread_id, created_at DESC)` — consulta típica é "resumo mais recente para este `base_thread_id`".

**Nota**: `chat_thread_sessions.base_thread_id` é hoje a chave de conflito do `ON CONFLICT (base_thread_id)` em `resolve_active_thread_id`, então já funciona como identificador único na prática, mesmo sem constraint `UNIQUE` explícita visível no código atual — a migration desta feature não presume alterar essa tabela, apenas referencia o mesmo valor de `base_thread_id` por convenção de aplicação, não por FK de banco.

## Sem mudança de schema para US1–US3

A sanitização de erro (US1) e a mudança de janela (US2) não introduzem nem alteram tabelas — atuam apenas no conteúdo das `ToolMessage` e no `trim_messages` em tempo de execução. A tipagem de retorno (US3) é uma mudança de assinatura de função Python, sem impacto de schema.

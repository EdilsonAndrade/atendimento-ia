# Research — Limite de mensagens por tenant (mensal)

## 1. Onde checar o bloqueio (evitar chamadas de LLM desnecessárias)

**Decisão**: a checagem de limite roda no Interface layer, ANTES de invocar o grafo (`app/api/v1/endpoints/chat.py` e `modules/webhook/whatsapp.py`), não dentro de `modules/ia/agent_graph.py`.

**Alternativas consideradas**: um nó-guarda no início do `StateGraph` (`routing_agent` viraria o segundo nó). Rejeitado porque exigiria uma aresta condicional nova e um jeito de "não gerar mensagem nenhuma" dentro do próprio grafo (LangGraph sempre produz algum estado final); checar antes do `invoke()` é mais simples, não tem custo de infraestrutura do grafo (sem passar pelo checkpointer), e garante literalmente zero chamadas de LLM quando bloqueado — o objetivo de negócio do ticket.

**Consequência**: os dois pontos de entrada (`chat.py`, `modules/webhook/whatsapp.py`) precisam do mesmo par de chamadas (checar antes, notificar depois). Nenhuma mudança em `agent_graph.py` é necessária.

## 2. Unidade de contagem e "fail-open" em erro de checagem

Já decidido em `/speckit.clarify` (ver `spec.md` > Clarifications): contagem por chamada de LLM, via `COUNT(*)` em `chat_token_usage` filtrado por `tenant_id` e `created_at >= início do mês corrente` (usa o índice já existente `ix_chat_token_usage_tenant_created`).

**Decisão nova (não coberta no clarify, decidida aqui por consistência com o FR-006 do EDI-60)**: se a própria checagem de limite falhar (ex.: Postgres indisponível), `CheckTenantLimitUseCase` faz **fail-open** — loga o erro e retorna "não bloqueado". Um erro transitório de infraestrutura nunca deve impedir um tenant pagante de ser atendido; o risco de um tenant ultrapassar o limite por alguns segundos de indisponibilidade é aceitável frente ao risco de bloquear tenants legítimos por uma falha technical alheia ao consumo real.

## 3. Idempotência das notificações de marco (50/80/100%)

**Decisão**: tabela `tenant_usage_notifications` com `UNIQUE (tenant_id, year_month, milestone)`. Cada tentativa de notificar um marco faz `INSERT ... ON CONFLICT DO NOTHING RETURNING id`; só envia o e-mail se uma linha foi de fato inserida (claim atômico, seguro sob concorrência de requisições paralelas do mesmo tenant).

**Por que não guardar "último marco notificado" como uma coluna no tenant**: não resolveria rajadas que pulam de <50% para >80% num único evento sem uma lógica extra para "notificar os marcos intermediários também" (FR-009, decidido no clarify). Testar os 3 marcos a cada chamada e deixar o `UNIQUE` constraint garantir "uma vez por mês" é mais simples e correto por construção — não exige computar "o que mudou desde a última contagem".

## 4. Redis: reaproveitar `evolution_redis` ou instância nova

**Decisão**: reaproveitar o `evolution_redis` já presente em `docker-compose.yml`/`docker-compose-local.yml` (mesma rede `proxy_default`), usando um índice lógico de banco diferente (`/2`, já que o Evolution API usa `/1`) para não colidir. Configurável via `REDIS_URL` (env var), com fallback de dev `redis://localhost:6379/2`.

**Alternativas consideradas**: instância Redis dedicada ao `chatatendimento-api`. Rejeitada por ora — adicionaria mais um container/custo de infra para um volume de mensagens que só existe quando o Postgres falha (caminho de exceção, não o caminho principal). Documentado como decisão revisitável: como o `REDIS_URL` é uma env var, trocar para uma instância dedicada no futuro não exige mudança de código, só de configuração/deploy.

**Risco aceito**: acoplamento operacional com o Redis do Evolution API (se o time responsável por ele reiniciar/reconfigurar sem saber do nosso uso, a fila de retry é afetada). Mitigado por: (a) DB index separado, (b) `REDIS_URL` configurável, (c) o pior caso de indisponibilidade do Redis é o mesmo pior caso de hoje (perda do registro, só que agora só quando Postgres E Redis falham ao mesmo tempo — estritamente melhor que o `main` atual).

## 5. Dead-letter

**Decisão**: um segundo Redis Stream (`token_usage_retry:dead_letter`), não uma tabela Postgres — mesma tecnologia da fila principal, evita introduzir mais uma dependência de schema para um caminho de exceção de exceção. O número de tentativas é rastreado usando o `delivery count` nativo do Redis Streams (`XPENDING` devolve quantas vezes cada entrada foi entregue a um consumer); ao exceder `TOKEN_USAGE_RETRY_MAX_ATTEMPTS` (padrão 5, configurável), o worker publica a entrada no stream de dead-letter (preservando `tenant_id`, `created_at` original, `thread_id`) e dá `XACK` na entrada original para tirá-la do PEL da fila principal.

## 6. Envio de e-mail

Não existe nenhum provedor de e-mail configurado no projeto hoje (sem SendGrid/SES/Mailgun). **Decisão**: usar `smtplib` (stdlib, sem nova dependência de pacote) com host/porta/credenciais via env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`) — mesmo padrão de configuração via `os.getenv` já usado no resto do projeto (não via `pydantic-settings`, que hoje só é usado para metadados da API). Isolado atrás do `EmailSenderPort`, então trocar por um provedor transacional depois é só uma nova Infrastructure, sem tocar Domain/Application.

## 7. Razão "chamadas por mensagem" (FR-013a/FR-013b)

Levantamento atual (`modules/ia/agent_graph.py`): toda mensagem passa por `routing_agent` (1) e depois por exatamente um entre `institutional_node`/`chitchat_node` (+1) ou `operational_node` (+1, podendo +1 de novo no retry de guardrail). **Pior caso hoje: 3** chamadas por mensagem. Sem dado histórico real de distribuição, o cenário "médio" da calculadora usa o MESMO valor (3) como padrão inicial — expor um número médio mais otimista sem dado real seria enganar o time comercial. Ambos os valores são configuráveis via env var (`TENANT_LIMIT_WORST_CASE_CALLS_PER_MESSAGE`, `TENANT_LIMIT_AVERAGE_CALLS_PER_MESSAGE`), revisáveis quando houver dado real de produção.

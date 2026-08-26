# Fase 0 — Research: Histórico consultável, resumo e outcome por sessão (EDI-53)

## 1. Reaproveitar `generate_and_store_session_summary` (EDI-59/61) em vez de um pipeline novo

**Decision**: A classificação de `outcome` e a geração de `follow_up_draft` acontecem na MESMA chamada de LLM que hoje já roda em `_summarize_session` (`modules/ia/thread_session.py`), disparada pelo mesmo gatilho (`resolve_active_thread_id` detecta expiração → `generate_and_store_session_summary` roda em thread daemon). O prompt existente é estendido para retornar também `outcome` e `follow_up_draft` no mesmo JSON, em vez de fazer uma segunda chamada separada ao LLM.

**Rationale**: `thread_session.py` já resolve exatamente o problema de "quando fechar a sessão" (idle timeout) e já monta o texto da conversa com o mesmo cuidado anti-alucinação do EDI-61 (linhas de `ToolMessage` como única fonte confiável sobre o que realmente aconteceu). Duplicar isso em um pipeline paralelo custaria uma 2ª chamada de LLM por sessão fechada (custo dobrado, sem benefício) e arriscaria as duas classificações divergirem (ex.: resumo dizendo "cliente confirmou agendamento" enquanto outcome diz `pensando`). Confirmado com o usuário (ver spec.md > Clarifications).

**Alternatives considered**:
- Pipeline novo e independente (rejeitado pelo usuário — custo de LLM duplicado, sem necessidade).
- Job assíncrono separado (ex.: cron que varre `chat_thread_summaries` recém-criados e classifica outcome depois) — rejeitado: o ticket exige que o outcome seja decidido "no fechamento de cada sessão", não recalculado depois por um worker (texto explícito do ticket).

**Impact on module boundaries**: `modules/ia/thread_session.py` é módulo legado (`ia`, grandfathered pela Constituição). A Política de Migração Legada permite que código legado adicione lógica nova desde que dependa de métodos públicos de um módulo, em vez de acessar `infrastructure.connection` ou internals de outro módulo diretamente. Como `follow_up_queue` é dado de um módulo NET-NEW (`modules/follow_up/`), `thread_session.py` chama o Use Case público desse módulo novo (`ClassifySessionOutcomeUseCase.execute(...)`) em vez de fazer `INSERT` raw SQL ali mesmo — assim o módulo novo nasce em conformidade com o Princípio III (Clean Architecture) e `thread_session.py` só passa a ter mais uma chamada de use case, no mesmo espírito de como `chat.py` já chama `check_tenant_limit_use_case`/`notify_usage_milestones_use_case`.

## 2. Onde persistir `conversation_messages` por turno

**Decision**: Um novo Use Case (`modules/conversation_history/application/record_conversation_turn.py`) é chamado nos dois pontos de entrada de mensagem já existentes — `app/api/v1/endpoints/chat.py` (widget/site) e `modules/webhook/whatsapp.py` (WhatsApp) — logo após o `invoke()` do grafo ter sucesso, gravando 2 linhas por turno: uma `role='human'` (o `payload.message`/texto recebido) e uma `role='ai'` (a última mensagem do resultado, a mesma que já é devolvida ao cliente). Mesma dupla-chamada que hoje já existe para `notify_usage_milestones_use_case` nesses dois arquivos.

**Rationale**: Só a última mensagem do estado final chega ao cliente (comentário existente em `agent_graph.py` sobre o guardrail EDI-61: "o cliente só vê a última mensagem do estado final") — gravar mensagens intermediárias de roteamento/tool-call em `conversation_messages` poluiria o histórico "consultável" que o ticket pede (o objetivo é histórico de CONVERSA, não trace de execução interna do grafo, que já existe no checkpoint do LangGraph para debug). `tenant_id`, `base_thread_id` (thread_id_base) e `active_thread_id` (thread_id_grafo) já estão resolvidos nesse ponto exato em ambos os arquivos, sem necessidade de replicar a lógica de `resolve_active_thread_id`.

**Alternatives considered**:
- Hook dentro de `agent_graph.py` (por nó) — rejeitado: geraria múltiplas linhas "ai" por turno (roteador + nó final), exigindo lógica extra para filtrar qual é a mensagem real vista pelo cliente; os dois pontos de entrada já têm exatamente essa resposta final isolada.
- Gravar de forma assíncrona/fire-and-forget (thread daemon, como o resumo de sessão) — rejeitado: é um único INSERT rápido (mesmo perfil de custo do já aceito `record_llm_usage`, chamado hoje de forma síncrona dentro dos nós do grafo antes de retornar); não se qualifica como "AI-model-bound work" do Princípio V, então correr em uma thread própria adicionaria complexidade sem necessidade. Uma falha aqui é só logada (try/except no próprio Use Case), nunca propagada.

## 3. Guardrail de `oferta_vigente` no prompt de `follow_up_draft`

**Decision**: O prompt estendido de `_summarize_session` recebe explicitamente o valor de `tenants.oferta_vigente_texto`/`oferta_vigente_validade` como contexto (ou a ausência dele) e uma instrução equivalente à já usada no guardrail anti-alucinação de `resultado` (EDI-61): o campo `follow_up_draft` só pode mencionar desconto/condição comercial se o texto da oferta foi fornecido no prompt E `oferta_vigente_validade >= data atual`; caso contrário, a instrução explicita "NUNCA mencione desconto, promoção ou condição comercial".

**Rationale**: Mesmo padrão já validado no código (guardrail de saída c92de57/EDI-61) — a defesa contra alucinação de oferta é colocar no prompt uma regra explícita e testável ("não invente X, use somente o valor Y fornecido"), não tentar filtrar a resposta depois por regex (frágil, falso-negativo alto).

**Alternatives considered**: Validação pós-geração via regex/lista de palavras-chave ("desconto", "%", "R$") — rejeitado como guardrail único: gera falsos positivos (draft pode citar preço normal do serviço sem ser uma oferta) e falsos negativos (o modelo pode inventar uma condição sem usar essas palavras). Pode ser adicionado como camada extra de defesa em profundidade no futuro, mas a regra no prompt é a defesa primária, testável via caso de teste dedicado (US3 da spec).

## 4. Estrutura de `oferta_vigente` em `tenants`

**Decision**: Duas colunas simples — `oferta_vigente_texto TEXT NULL` e `oferta_vigente_validade DATE NULL` — em vez de uma coluna JSONB única.

**Rationale**: Consistente com o padrão já usado em `tenants` para campos opcionais 1:1 (`monthly_message_limit INTEGER NULL`, EDI-63) e permite comparação direta de validade em SQL (`WHERE oferta_vigente_validade >= CURRENT_DATE`) sem precisar extrair de JSONB.

**Alternatives considered**: JSONB `oferta_vigente {texto, validade}` — rejeitado por não trazer benefício aqui (não é uma lista nem estrutura variável) e dificultar a query de validade.

## 5. Job de expurgo — script standalone, não worker/cron embutido

**Decision**: `modules/conversation_history/application/purge_expired_messages.py` (Use Case) + entrypoint `workers/conversation_history_purge.py` (`python -m workers.conversation_history_purge`), no mesmo padrão do `workers/token_usage_retry_worker.py` (EDI-63) — mas como script de execução única (roda, processa, termina), não como processo de longa duração. O agendamento (cron diário, etc.) é responsabilidade de infraestrutura fora deste repositório.

**Rationale**: O ticket já exclui explicitamente "Worker de disparo automático / cron diário" do escopo (ligado ao envio de follow-up); por analogia e para não introduzir um scheduler novo no código (não há nenhum hoje no projeto — grep confirmou ausência de APScheduler/Celery/cron em Python), o expurgo segue o padrão de script invocável já estabelecido, deixando o agendamento para a camada de infra (ex.: cron do container, como já ocorre para outras rotinas de manutenção).

**Alternatives considered**: `BackgroundTasks`/loop assíncrono embutido no processo da API — rejeitado: expurgo é uma operação de manutenção, não uma resposta a uma requisição; não se encaixa no ciclo request/response do Princípio V, e manter um scheduler dentro do processo da API duplicaria responsabilidade de infraestrutura.

## 6. Endpoints de leitura — routers dedicados, nested sob `/tenants/{tenant_id}`

**Decision**: Dois routers novos, cada um registrado em `app/main.py` (mesmo padrão de `global_notification_recipients_router`, não via `app/api/v1/router.py`, que hoje só agrega `chat`/`ingest`):
- `app/api/v1/endpoints/conversation_history.py` → `GET /api/v1/tenants/{tenant_id}/conversation-history/{base_thread_id}`
- `app/api/v1/endpoints/follow_up_queue.py` → `GET /api/v1/tenants/{tenant_id}/follow-up-queue?status=`

**Rationale**: Ambos os recursos são sempre acessados no contexto de um tenant (Princípio I) — nested path deixa isso explícito na própria rota, mesmo padrão já usado por `GET /tenants/{tenant_id}/usage` (EDI-63). Sem autenticação adicional além do que já existe hoje nos demais endpoints de tenant (mesma decisão já registrada no spec de EDI-63 e assumida aqui — ver spec.md > Assumptions).

**Alternatives considered**: Query-param-only (`GET /conversation-history?tenant_id=&base_thread_id=`) — rejeitado por inconsistência com o padrão já estabelecido (`/tenants/{id}/usage`, `/tenants/{id}/delete-impact`).

## 7. Módulos novos: `conversation_history` e `follow_up` (dois módulos, não um)

**Decision**: Dois módulos Clean Architecture separados, não um único módulo combinado.

**Rationale**: São dois bounded contexts com ciclos de vida e consumidores diferentes — `conversation_history` é dado bruto de conversa (write-heavy, todo turno) consumido só para leitura/expurgo; `follow_up` é dado derivado (1 registro por sessão fechada) com ciclo de vida próprio (`status` pendente→aprovado→enviado) que tickets futuros (worker de disparo, UI de aprovação) vão estender. Separar evita acoplar o schema/porta de um ao do outro; `follow_up` depende de `conversation_history` apenas indiretamente (via `thread_session.py`, que já tem o histórico da sessão pelo checkpoint do LangGraph — não precisa ler `conversation_messages` para classificar outcome).

**Alternatives considered**: Um módulo único `modules/conversation/` com duas sub-pastas — rejeitado, mistura duas taxas de mudança e dois times de consumidores futuros diferentes (analytics/BI para histórico vs. vendas/CS para follow-up).

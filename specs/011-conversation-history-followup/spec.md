# Feature Specification: Histórico consultável, resumo e outcome por sessão (Fundação de Follow-up)

**Feature Branch**: `edilsonaandrade/edi-53-follow-up-fundacao-historico-consultavel-resumo-e-outcome`
**Created**: 2026-08-26
**Status**: Draft
**Input**: User description: "[Follow-up] Fundação: histórico consultável, resumo e outcome por sessão (EDI-53) — hoje a conversa só é persistida via checkpoint do LangGraph (PostgresSaver), não consultável/filtrável/analisável via SQL. Precisamos de: (1) tabela `conversation_messages` estruturada, populada em paralelo ao checkpoint; (2) ao fechar cada sessão, classificar `outcome` (fechado/pensando/sem_resposta/recusado/em_andamento) e gerar `follow_up_draft` quando aplicável, com guardrail para nunca citar desconto fora de `tenants.oferta_vigente`; (3) campos novos em `tenants` (`oferta_vigente`, `retention_days`); (4) job de expurgo de `conversation_messages` por `retention_days`; (5) tabela `follow_up_queue`; (6) endpoints de leitura de histórico e da fila de follow-up. Fora de escopo: worker de disparo automático, envio efetivo (WhatsApp/e-mail), UI."

## Clarifications

### Session 2026-08-26

- Q: O ticket pede uma chamada ao LLM no fechamento da sessão para gerar `summary`+`outcome`+`follow_up_draft`, mas já existe `generate_and_store_session_summary` (EDI-59/61, `modules/ia/thread_session.py`) que gera `resumo`+`fatos_estruturados` e grava em `chat_thread_summaries` nesse mesmo gatilho (expiração de sessão). Como tratar a sobreposição? → A: Estender o fluxo existente — uma única chamada ao LLM em `thread_session.py` passa a produzir `resumo`+`fatos`+`outcome`+`follow_up_draft` juntos (um único prompt/uma única chamada). `outcome`/`follow_up_draft` alimentam a nova `follow_up_queue`; `resumo`/`fatos_estruturados` continuam sendo gravados em `chat_thread_summaries` exatamente como hoje. Evita uma 2ª chamada de LLM redundante por sessão fechada.
- Q: O expurgo por `retention_days` deve valer só para `conversation_messages` (única tabela citada no ticket) ou também para `chat_thread_summaries`/`follow_up_queue`? → A: Só `conversation_messages`, exatamente como descrito no ticket. Expurgo de `chat_thread_summaries`/`follow_up_queue` fica para um ticket futuro — não amplia o escopo desta feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Histórico de conversa consultável via SQL/API (Priority: P1)

Toda mensagem trocada numa sessão (cliente e atendente) passa a ser gravada também em uma tabela estruturada (`conversation_messages`), em paralelo ao checkpoint do LangGraph — sem substituí-lo. Isso permite consultar o histórico de um tenant/thread via SQL comum ou via endpoint de leitura, sem precisar decodificar o formato interno de checkpoint do LangGraph.

**Why this priority**: é a fundação de todo o resto do ticket (outcome, follow-up, analytics) — sem histórico estruturado e consultável, nada mais neste ticket tem dado para trabalhar.

**Independent Test**: enviar algumas mensagens em uma conversa de teste e confirmar, via SQL direto ou via endpoint de leitura, que cada mensagem (cliente e atendente) aparece em `conversation_messages` com `tenant_id`, `base_thread_id`, `active_thread_id`, `role` e `content` corretos, na ordem em que ocorreram.

**Acceptance Scenarios**:

1. **Given** uma conversa em andamento em um `base_thread_id`, **When** o cliente envia uma mensagem e o atendente responde, **Then** ambas as mensagens aparecem em `conversation_messages` com `role` (`human`/`ai`) e `content` corretos, sem atrasar a resposta ao cliente.
2. **Given** uma sessão que expira e gera um novo `active_thread_id` para o mesmo `base_thread_id` (EDI-59), **When** novas mensagens chegam, **Then** elas são gravadas com o novo `active_thread_id`, mas continuam associadas ao mesmo `base_thread_id` para consulta do histórico completo.
3. **Given** um `tenant_id` e um `base_thread_id` válidos, **When** o endpoint de leitura de histórico é chamado, **Then** retorna as mensagens daquele thread em ordem cronológica, isolado de mensagens de outros tenants/threads.

---

### User Story 2 - Sessão fechada gera outcome e rascunho de follow-up (Priority: P1)

Quando uma sessão expira (mesmo gatilho hoje usado por `generate_and_store_session_summary`), a mesma chamada ao LLM que já gera `resumo`/`fatos_estruturados` passa a também classificar um `outcome` (`fechado`, `pensando`, `sem_resposta`, `recusado`, `em_andamento`) e, quando o outcome for `pensando` ou `sem_resposta`, gerar um `follow_up_draft` personalizado (usando o nome do cliente via `extract_customer_profile`). O par outcome/draft é gravado como um novo registro em `follow_up_queue`, com status `pendente`.

**Why this priority**: é o valor central do ticket ("Fundação... resumo e outcome por sessão") — sem outcome classificado, não existe fila de follow-up para nenhum ticket futuro consumir.

**Independent Test**: encerrar (por inatividade) uma sessão de teste com uma conversa onde o cliente não respondeu à última pergunta do atendente, e confirmar que exatamente um registro aparece em `follow_up_queue` com `outcome = 'sem_resposta'` e um `draft_message` preenchido e coerente com a conversa.

**Acceptance Scenarios**:

1. **Given** uma sessão que expira por inatividade, **When** a classificação roda, **Then** exatamente um registro é gravado em `follow_up_queue` (idempotente — reprocessar a mesma sessão expirada não duplica o registro).
2. **Given** uma conversa em que o cliente confirmou um agendamento com respaldo de `ToolMessage` real (mesmo cuidado anti-alucinação do EDI-61), **When** a sessão fecha, **Then** `outcome = 'fechado'` e nenhum `follow_up_draft` é gerado (campo nulo).
3. **Given** uma conversa em que o cliente parou de responder após o atendente enviar uma proposta, **When** a sessão fecha, **Then** `outcome = 'sem_resposta'` (ou `pensando`, conforme o teor da última fala do cliente) e um `follow_up_draft` não vazio é gerado.
4. **Given** uma sessão sem nenhuma mensagem trocada (thread vazio), **When** a expiração dispara, **Then** nenhum registro é criado em `follow_up_queue` nem em `chat_thread_summaries` (mesmo comportamento já existente hoje para resumo vazio).
5. **Given** a chamada ao LLM falha ou lança exceção, **When** isso ocorre, **Then** o erro é apenas logado (mesmo padrão try/except de `generate_and_store_session_summary`) e nunca propaga nem bloqueia a resolução da sessão/resposta ao cliente atual.

---

### User Story 3 - Draft de follow-up nunca inventa desconto (Priority: P2)

O prompt que gera o `follow_up_draft` só pode citar desconto/condição comercial se ela vier do campo `tenants.oferta_vigente` (texto + validade) daquele tenant. Se `oferta_vigente` estiver vazio ou expirado, o draft não pode mencionar nenhuma oferta, mesmo que o modelo "ache" plausível sugerir uma.

**Why this priority**: guardrail de segurança de conteúdo — sem ele, a US2 já entrega outcome, mas o draft de follow-up seria arriscado de usar (mesma classe de risco do guardrail de saída do c92de57/EDI-61: o modelo pode inventar uma condição comercial que a empresa nunca ofereceu).

**Independent Test**: gerar o draft para um tenant sem `oferta_vigente` cadastrada e confirmar que nenhuma menção a desconto/condição comercial aparece no texto; depois cadastrar uma `oferta_vigente` válida e confirmar que o draft, quando cita uma oferta, cita exatamente o texto cadastrado (não uma variação inventada).

**Acceptance Scenarios**:

1. **Given** um tenant sem `oferta_vigente` (nula) ou com `oferta_vigente` expirada, **When** um `follow_up_draft` é gerado para esse tenant, **Then** o texto não contém nenhuma menção a desconto, condição comercial ou promoção.
2. **Given** um tenant com `oferta_vigente` válida (dentro da validade), **When** um `follow_up_draft` é gerado e o modelo decide citar a oferta, **Then** o conteúdo citado corresponde ao texto de `oferta_vigente`, sem inventar valores/condições adicionais.

---

### User Story 4 - Fila de follow-up consultável por tenant/status (Priority: P2)

Um endpoint de leitura permite consultar os registros de `follow_up_queue` filtrando por `tenant_id` e `status` (`pendente`, `aprovado`, `enviado`, `descartado`, `opt_out`), para que um ticket futuro (worker de disparo, UI de aprovação) tenha uma API pronta para consumir.

**Why this priority**: consumidores futuros (worker, UI) dependem desse endpoint; sem ele a fila gerada pela US2 fica presa no banco.

**Independent Test**: com registros de diferentes status na fila para o mesmo tenant, chamar o endpoint filtrando por `status=pendente` e confirmar que só os registros pendentes daquele tenant retornam.

**Acceptance Scenarios**:

1. **Given** múltiplos registros em `follow_up_queue` de tenants diferentes, **When** o endpoint é chamado com um `tenant_id`, **Then** retorna apenas os registros daquele tenant.
2. **Given** registros com status variados para o mesmo tenant, **When** o endpoint é chamado com filtro de `status`, **Then** retorna apenas os registros daquele status.

---

### User Story 5 - Expurgo de histórico antigo por tenant (Priority: P3)

Cada tenant tem um `retention_days` configurável (inteiro). Um job de expurgo apaga de `conversation_messages` as mensagens mais antigas que `retention_days` do respectivo tenant.

**Why this priority**: importante para compliance/armazenamento, mas não bloqueia o valor das US1-US4 — pode rodar dias depois do restante estar em produção.

**Independent Test**: cadastrar um tenant com `retention_days` baixo (ex.: 1), inserir mensagens de teste com `created_at` antigo, rodar o job de expurgo, e confirmar que só as mensagens mais antigas que o limite são removidas, preservando as recentes e as de outros tenants com `retention_days` diferente.

**Acceptance Scenarios**:

1. **Given** um tenant com `retention_days = 30` e mensagens com `created_at` de 40 dias atrás, **When** o job de expurgo roda, **Then** essas mensagens são apagadas de `conversation_messages`.
2. **Given** um tenant com `retention_days = NULL` (não configurado), **When** o job de expurgo roda, **Then** nenhuma mensagem desse tenant é apagada (sem retenção configurada = sem expurgo automático).
3. **Given** dois tenants com `retention_days` diferentes, **When** o job roda, **Then** cada tenant tem suas mensagens expurgadas de acordo com seu próprio `retention_days`, nunca aplicando o valor de um tenant a outro.

---

### Edge Cases

- Sessão expira, mas o `active_thread_id` correspondente não tem nenhuma mensagem em `conversation_messages` (ex.: falha isolada na gravação por mensagem) — a classificação de outcome usa o que o checkpoint do LangGraph tiver (mesma fonte já usada por `_get_session_messages`), sem depender exclusivamente de `conversation_messages` estar completo.
- A mesma sessão expira e é processada duas vezes (ex.: race condition, reprocessamento manual) — o registro em `follow_up_queue` não deve duplicar (idempotência, FR explícito no ticket).
- `oferta_vigente` tem texto preenchido mas validade já expirada na data em que o draft é gerado — tratado como "sem oferta vigente" (mesmo efeito de campo nulo).
- Tenant tem `retention_days` configurado menor que o tempo de sessão ainda em andamento (idle window) — o expurgo nunca deve remover mensagens de uma sessão ainda ativa; a checagem é sobre `created_at` da mensagem, então isso só afeta tenants com `retention_days` extremamente baixo, um risco de configuração aceito (não validado ativamente por esta feature).
- Endpoint de leitura de histórico é chamado sem filtro de tenant — deve ser rejeitado (mesma isolação multi-tenant já aplicada nos demais endpoints do projeto).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE persistir toda mensagem de uma sessão (cliente e atendente) em uma tabela estruturada `conversation_messages` (`tenant_id`, `base_thread_id`, `active_thread_id`, `role`, `content`, `created_at`), em paralelo ao checkpoint já existente do LangGraph (`PostgresSaver`), sem substituí-lo nem atrasar a resposta ao cliente.
- **FR-002**: O sistema DEVE, ao expirar uma sessão (mesmo gatilho de `resolve_active_thread_id`/`generate_and_store_session_summary`), classificar um `outcome` (`fechado` | `pensando` | `sem_resposta` | `recusado` | `em_andamento`) para aquela sessão, na mesma chamada ao LLM que já gera `resumo`/`fatos_estruturados`.
- **FR-003**: Quando `outcome` for `pensando` ou `sem_resposta`, o sistema DEVE gerar um `follow_up_draft` personalizado (usando o nome do cliente via `extract_customer_profile`, quando disponível); para os demais outcomes, `follow_up_draft` DEVE ficar nulo.
- **FR-004**: O sistema DEVE gravar `outcome`, `summary` e `follow_up_draft` como um novo registro em `follow_up_queue` (`tenant_id`, `base_thread_id`, `outcome`, `summary`, `draft_message`, `status='pendente'`, `attempts=0`, `created_at`), exatamente um registro por sessão fechada (idempotente — reprocessar a mesma sessão expirada não cria duplicata).
- **FR-005**: O prompt que gera `follow_up_draft` NUNCA DEVE citar desconto ou condição comercial que não venha do campo `tenants.oferta_vigente` daquele tenant, válido na data de geração; se `oferta_vigente` estiver nula ou expirada, o draft não pode mencionar nenhuma oferta.
- **FR-006**: O sistema DEVE adicionar os campos `oferta_vigente` (texto + validade, nullable) e `retention_days` (inteiro, nullable) à tabela `tenants`.
- **FR-007**: O sistema DEVE oferecer um job de expurgo que apaga de `conversation_messages` as mensagens com `created_at` mais antigo que `retention_days` do respectivo tenant; tenants com `retention_days` nulo não têm nenhuma mensagem expurgada automaticamente.
- **FR-008**: O sistema DEVE expor um endpoint de leitura do histórico de conversa, filtrável por `tenant_id` (obrigatório) e `base_thread_id`, retornando as mensagens de `conversation_messages` em ordem cronológica.
- **FR-009**: O sistema DEVE expor um endpoint de leitura da fila de follow-up, filtrável por `tenant_id` (obrigatório) e `status`, retornando os registros de `follow_up_queue` correspondentes.
- **FR-010**: Falhas na geração de outcome/summary/draft (ex.: erro do LLM) DEVEM ser apenas logadas, nunca propagadas — mesmo padrão de isolamento de falha já usado em `generate_and_store_session_summary` (não pode atrasar/bloquear a resolução de sessão do cliente atual).
- **FR-011**: O campo `resultado`/`outcome` NUNCA DEVE ser classificado como `fechado` (agendamento confirmado) com base apenas na fala do "Atendente" (mensagens `ai`) — precisa de uma `ToolMessage` real correspondente comprovando a ação, mesmo cuidado anti-alucinação já aplicado em `_summarize_session` (EDI-61).

### Key Entities *(include if feature involves data)*

- **Conversation Message** (`conversation_messages`, nova): uma mensagem individual de uma sessão, com `tenant_id`, `base_thread_id`, `active_thread_id`, `role`, `content`, `created_at`; complementa (não substitui) o checkpoint do LangGraph.
- **Follow-up Queue Entry** (`follow_up_queue`, nova): outcome + resumo + rascunho de follow-up de uma sessão fechada, com ciclo de vida via `status` (`pendente` → `aprovado`/`descartado`/`opt_out` → `enviado`), `attempts`, `approved_by`, `approved_at`.
- **Tenant** (extensão): ganha `oferta_vigente` (texto + validade, nullable) e `retention_days` (inteiro, nullable).
- **Chat Thread Summary** (`chat_thread_summaries`, já existente via EDI-59/61): continua recebendo `resumo`/`fatos_estruturados`; não é modificada por esta feature além de compartilhar a mesma chamada de LLM que agora também produz outcome/draft.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das mensagens trocadas em sessões novas (pós-deploy) ficam disponíveis em `conversation_messages`, consultáveis via SQL/endpoint sem decodificar o checkpoint do LangGraph.
- **SC-002**: Toda sessão fechada gera exatamente um registro de outcome em `follow_up_queue` — nunca zero (quando há conversa) nem mais de um (idempotência).
- **SC-003**: 0% dos `follow_up_draft` gerados mencionam desconto/condição comercial fora do texto cadastrado em `oferta_vigente` do tenant.
- **SC-004**: Um tenant com `retention_days` configurado nunca acumula em `conversation_messages` mensagens mais antigas que esse limite, após o job de expurgo rodar.
- **SC-005**: Os dois endpoints de leitura (histórico e fila de follow-up) respondem corretamente isolados por tenant, cobertos por teste de integração.

## Assumptions

- O gatilho de fechamento de sessão continua sendo exclusivamente a expiração por inatividade já implementada em `resolve_active_thread_id`/`SESSION_IDLE_MINUTES` (EDI-59) — esta feature não introduz um novo mecanismo de "fechar sessão".
- A classificação de outcome e a geração de `follow_up_draft` são feitas na MESMA chamada de LLM que hoje gera `resumo`/`fatos_estruturados` em `_summarize_session` (`modules/ia/thread_session.py`) — ver seção Clarifications. Não há uma segunda chamada de LLM nem um pipeline separado.
- O job de expurgo (FR-007) é um script/comando invocável (mesmo padrão de processo dedicado usado pelo worker de retry do EDI-63, ex. `python -m workers.<nome>`), sem agendamento automático embutido no código desta feature — o agendamento (cron externo) é responsabilidade de infraestrutura, fora do escopo desta implementação.
- O expurgo por `retention_days` (FR-007) se aplica apenas a `conversation_messages`, exatamente como descrito no ticket — `chat_thread_summaries` e `follow_up_queue` ficam fora do expurgo automático nesta feature (ver Clarifications).
- Os endpoints de leitura (FR-008, FR-009) seguem o mesmo padrão dos demais endpoints do projeto (`app/api/v1/endpoints/tenant.py`) — sem autenticação adicional além do que já existe hoje.
- Worker de disparo automático de follow-up, envio efetivo (WhatsApp/e-mail) e UI de aprovação são tickets futuros, fora do escopo desta feature — `follow_up_queue` só precisa expor os dados e o endpoint de leitura para viabilizá-los depois.
- Os valores exatos do enum `outcome` são os cinco listados no ticket (`fechado`, `pensando`, `sem_resposta`, `recusado`, `em_andamento`); novos valores, se necessários, ficam para revisão futura.

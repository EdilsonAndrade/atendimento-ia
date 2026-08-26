# Feature Specification: Limite de mensagens por tenant (mensal)

**Feature Branch**: `edilsonaandrade/edi-63-limite-de-mensagens-por-tenant-mensal-flag-byok-com-chave-de`
**Created**: 2026-08-25
**Status**: Draft
**Input**: User description: "Limite de mensagens por tenant (mensal) + flag BYOK com chave de API própria (EDI-63) — definir um limite mensal de mensagens por tenant, evitando que o volume de uso de um único tenant estoure a margem calculada na precificação (custo de IA hoje é 100% absorvido pela InterasisAI). Inclui enforcement (bloqueio silencioso ao cliente final), notificações progressivas por e-mail (50%, 80%, 100%, reset), UI admin para configurar limite/e-mails, e um mecanismo de resiliência (fila de retry) para garantir que a contagem de uso em `chat_token_usage` não seja perdida em caso de falha na gravação."

## Clarifications

### Session 2026-08-25

- Q: Como contar "mensagem" para o limite mensal (por turno do cliente final ou por chamada de LLM)? → A: Por chamada de LLM — cada chamada real ao LLM (linha em `chat_token_usage`) conta 1 unidade no limite mensal. É mais fiel ao custo real de IA (motivo original do ticket), mas o número não corresponde 1:1 às mensagens reais dos clientes finais, já que uma única mensagem pode disparar 3-4 chamadas (roteador, institucional/chitchat, operacional, retry). Para fins comerciais, ao vender um plano ao tenant em "mensagens" (ex.: 1000 mensagens/mês para os clientes finais dele), o `monthly_message_limit` configurado internamente precisa ser maior, aplicando a razão média de chamadas por mensagem — ex.: um plano vendido como "1000 mensagens/mês" pode exigir `monthly_message_limit` configurado como ~3000.
- Q: Numa rajada que cruza mais de um marco (50% e 80%) numa única mensagem, dispara todos os e-mails dos marcos cruzados ou só o mais alto atingido? → A: Todos os marcos cruzados disparam, em sequência (o e-mail de 50% e o de 80% são ambos enviados, mesmo que a chamada que causou o pulo já tenha ultrapassado os dois).
- Q: Falha permanente numa entrada da fila de retry (Redis) — limite de tentativas com dead-letter, ou retry indefinido? → A: Limite de tentativas (N, configurável) com fila de dead-letter separada para investigação manual e alerta; cada entrada da dead-letter preserva `tenant_id`, horário original e `thread_id` para rastreabilidade. Um painel no front-end para visualizar a dead-letter fica para um ticket separado, mas os dados já devem sair estruturados o suficiente para isso.
- Q: Mensagem bloqueada por limite atingido deve ficar visível para admin/suporte além do e-mail de 100%? → A: Sim, deve ser registrada (log estruturado ou métrica) para o suporte identificar bloqueios em andamento, sem esperar o e-mail de 100%.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant que atinge o limite mensal para de gerar respostas (Priority: P1)

Quando o volume de mensagens de um tenant no mês corrente atinge o `monthly_message_limit` configurado, o agente deixa de responder aos clientes finais desse tenant — a mensagem do cliente final chega, mas nenhuma resposta automática é gerada (nem uma mensagem de "limite atingido"). Tenants sem limite configurado continuam funcionando exatamente como hoje.

**Why this priority**: é a capacidade central do ticket — sem o bloqueio, nenhum controle de margem existe de fato, e o restante (notificações, UI) só faz sentido em torno dessa regra.

**Independent Test**: configurar um `monthly_message_limit` baixo para um tenant de teste, enviar mensagens até ultrapassar o limite, e confirmar que a partir da mensagem que cruza o limite o agente não gera mais resposta, enquanto um tenant sem limite configurado continua respondendo normalmente.

**Acceptance Scenarios**:

1. **Given** um tenant com `monthly_message_limit` = 1000 e 999 mensagens já contabilizadas no mês, **When** o cliente final envia a mensagem de número 1000, **Then** o agente processa normalmente (ainda dentro do limite).
2. **Given** o mesmo tenant já com 1000 mensagens contabilizadas no mês, **When** o cliente final envia uma nova mensagem, **Then** o agente não gera nenhuma resposta para essa mensagem.
3. **Given** um tenant com `monthly_message_limit` = NULL, **When** qualquer volume de mensagens é enviado, **Then** o agente continua respondendo normalmente, sem nenhum bloqueio.

---

### User Story 2 - Tenant e InterasisAI recebem avisos progressivos de consumo (Priority: P2)

Conforme o consumo mensal de um tenant cruza os marcos de 50%, 80% e 100% do limite, e-mails são disparados automaticamente. Os avisos de 50% e 80% vão apenas para os e-mails cadastrados no próprio tenant (`notification_emails`); o aviso de 100% (bloqueio) vai também para os e-mails internos da InterasisAI (`global_notification_recipients`). Cada aviso é enviado uma única vez por marco por mês.

**Why this priority**: sem aviso, o bloqueio da US1 pega o tenant de surpresa e gera atrito/suporte; mas o bloqueio em si já entrega o valor de proteção de margem mesmo sem os avisos.

**Independent Test**: configurar um limite baixo e e-mails de notificação em um tenant de teste, enviar mensagens até cruzar cada marco, e confirmar que cada e-mail é disparado exatamente uma vez, para os destinatários corretos em cada marco.

**Acceptance Scenarios**:

1. **Given** um tenant com `notification_emails` cadastrados, **When** o consumo do mês cruza 50% do `monthly_message_limit`, **Then** um e-mail de aviso de 50% é enviado a todos os `notification_emails` do tenant, uma única vez.
2. **Given** o mesmo tenant, **When** o consumo cruza 80%, **Then** um e-mail de aviso de 80% é enviado aos `notification_emails` do tenant, uma única vez, sem reenviar o aviso de 50%.
3. **Given** o mesmo tenant, **When** o consumo atinge 100% (bloqueio), **Then** um e-mail é enviado aos `notification_emails` do tenant E a todos os `global_notification_recipients` ativos (ou ao fallback `contato@interasisai.com.br` se a lista global estiver vazia).
4. **Given** um tenant sem nenhum `notification_emails` cadastrado, **When** qualquer marco é cruzado, **Then** nenhum e-mail é enviado ao tenant, mas o bloqueio em si (US1) continua ocorrendo normalmente ao atingir 100%.

---

### User Story 3 - Admin configura limite, e-mails e acompanha consumo (Priority: P3)

Na tela onde já se edita `name`, `google_calendar_id`, `allowed_domains` e `scheduling_enabled` do tenant, o admin passa a poder definir o `monthly_message_limit` e gerenciar a lista de `notification_emails` (adicionar/remover múltiplos e-mails). Uma nova seção de "Configurações Globais" permite gerenciar `global_notification_recipients`. A tela também exibe o consumo atual do mês (mensagens usadas / limite / %) com indicação visual por cor (verde <50%, amarelo 50-80%, vermelho ≥80%). A área admin também ganha uma calculadora de dimensionamento de plano: dado um número de chamadas de LLM (o valor a configurar em `monthly_message_limit`) e quantos nós do agente uma mensagem tipicamente aciona, ela estima quantas mensagens reais de clientes finais aquele limite comporta — útil pro time comercial saber, por exemplo, que 1000 chamadas de LLM podem representar só ~300 mensagens reais de clientes se toda mensagem acionar todos os nós do fluxo.

**Why this priority**: sem UI, o limite e os e-mails só poderiam ser configurados diretamente no banco — a US1 e US2 já entregam o valor de negócio principal (proteção de margem e aviso) mesmo com configuração manual temporária.

**Independent Test**: abrir a tela de edição de um tenant, configurar `monthly_message_limit` e adicionar/remover e-mails de `notification_emails`, salvar, e confirmar que os valores persistem e que o indicador de consumo reflete o uso real do mês.

**Acceptance Scenarios**:

1. **Given** a tela de edição de um tenant, **When** o admin define um `monthly_message_limit` e salva, **Then** o valor é persistido e passa a ser aplicado no enforcement (US1).
2. **Given** a tela de edição de um tenant, **When** o admin adiciona ou remove e-mails de `notification_emails`, **Then** a lista atualizada é usada nas próximas notificações (US2).
3. **Given** um tenant com 31% do limite mensal consumido, **When** o admin visualiza a tela, **Then** vê o indicador "156 / 500 mensagens (31%)" com destaque visual verde.
4. **Given** a tela de "Configurações Globais", **When** o admin adiciona um novo e-mail interno, **Then** esse e-mail passa a receber os alertas de 100% de bloqueio de qualquer tenant.
5. **Given** a calculadora de dimensionamento de plano, **When** o admin informa um número de chamadas de LLM (ex.: 1000) e o cenário de nós acionados por mensagem (ex.: pior caso — todos os nós: roteador + operacional + retry), **Then** o sistema calcula e exibe a estimativa de mensagens reais de clientes finais correspondente (ex.: 1000 ÷ ~3-4 nós ≈ 250-333 mensagens reais).
6. **Given** a calculadora de dimensionamento de plano, **When** o admin altera o cenário de nós acionados (ex.: de "pior caso" para "médio"), **Then** a estimativa de mensagens reais é recalculada de acordo, sem exigir salvar nada — é uma ferramenta de simulação, não uma configuração persistida do tenant.

---

### User Story 4 - Contagem de uso não se perde em falha transitória do banco (Priority: P2)

Hoje, cada chamada ao LLM grava um registro em `chat_token_usage` de forma síncrona; se essa gravação falhar (ex.: Postgres temporariamente indisponível), o registro se perde silenciosamente (apenas logado). Como o enforcement da US1 depende dessa tabela para contar o consumo do mês, essa perda poderia deixar um tenant ultrapassar o limite sem o sistema perceber. Ao falhar a gravação direta, o registro passa a ser publicado em uma fila de retry (Redis Streams) e um worker dedicado o reprocessa e grava no Postgres assim que possível — inclusive reprocessando qualquer pendência acumulada quando o próprio worker sobe após ter ficado fora do ar.

**Why this priority**: sem isso, o enforcement da US1 fica sujeito a contagem incorreta em cenários de instabilidade — não bloqueia o MVP do limite (que já funciona no caminho feliz), mas é necessário para a contagem ser confiável o suficiente para bloquear um tenant com segurança.

**Independent Test**: simular indisponibilidade temporária do Postgres durante uma chamada ao LLM, confirmar que o registro de uso aparece na fila de retry, restaurar o Postgres, subir o worker (inclusive após o worker também ter ficado fora do ar) e confirmar que o registro pendente é gravado em `chat_token_usage` sem duplicação.

**Acceptance Scenarios**:

1. **Given** uma falha transitória ao gravar diretamente em `chat_token_usage`, **When** a falha ocorre, **Then** o registro de uso é publicado na fila de retry (Redis Streams) em vez de ser apenas descartado/logado.
2. **Given** um registro pendente na fila de retry, **When** o worker está no ar e o Postgres está disponível, **Then** o worker grava o registro em `chat_token_usage` e confirma (`XACK`) a entrada, removendo-a da lista de pendências.
3. **Given** o worker cai no meio do processamento de um registro (antes do `XACK`), **When** o worker sobe novamente, **Then** ele identifica a entrada pendente (PEL) e a reprocessa, sem perder o registro.
4. **Given** o worker fica completamente fora do ar por um período e mensagens continuam se acumulando na fila, **When** o worker volta a subir, **Then** ele processa todo o backlog acumulado antes (ou em conjunto com) as novas entradas, sem perder nenhuma.
5. **Given** uma entrada da fila de retry falha repetidamente ao ser reprocessada, **When** o número configurável de tentativas se esgota, **Then** ela é movida para uma fila de dead-letter separada (preservando `tenant_id`, horário original e `thread_id`) e um alerta é disparado, em vez de continuar sendo retentada indefinidamente.

---

### Edge Cases

- Um tenant atinge exatamente 100% do limite no meio de uma conversa em andamento — a mensagem seguinte do cliente final (a que cruza o limite) não gera resposta; mensagens anteriores já respondidas não são afetadas retroativamente.
- Um marco (50%, 80%, 100%) é cruzado em uma única mensagem que pula de, por exemplo, 45% para 85% (rajada de chamadas simultâneas) — os e-mails de todos os marcos cruzados (50% e 80%, nesse exemplo) disparam em sequência, cada um ainda respeitando o limite de uma vez por mês.
- Uma entrada da fila de retry falha repetidamente (ex.: dado corrompido) e nunca seria reprocessada com sucesso — após um número configurável de tentativas, ela é movida para uma fila de dead-letter em vez de ficar sendo retentada para sempre, preservando `tenant_id`, horário original e `thread_id` para investigação manual.
- `notification_emails` é uma lista vazia ou nula — nenhum e-mail de tenant é enviado, mas o bloqueio em si (US1) e o alerta para `global_notification_recipients` no marco de 100% continuam ocorrendo.
- `global_notification_recipients` está vazia — usar `contato@interasisai.com.br` como fallback no alerta de 100%.
- A fila de retry (Redis) acumula um volume grande de pendências por uma indisponibilidade prolongada do Postgres — o worker deve conseguir drenar o backlog de forma incremental ao voltar, sem exigir intervenção manual.
- O próprio Redis reinicia sem persistência (AOF) habilitada — mensagens ainda não confirmadas (`XACK`) podem ser perdidas; por isso a persistência do Redis é um pré-requisito de infraestrutura desta feature, não um detalhe opcional.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE permitir configurar um `monthly_message_limit` (inteiro, opcional) por tenant; quando não configurado (`NULL`), o tenant continua sem nenhum limite de uso.
- **FR-002**: O sistema DEVE contar, para cada tenant, o volume de chamadas ao LLM do mês corrente a partir das linhas em `chat_token_usage` (`tenant_id` + `created_at`) — cada chamada real ao LLM (roteador, institucional, chitchat, operacional, incluindo retries) conta 1 unidade no limite mensal, independentemente de quantas chamadas uma única mensagem do cliente final tenha disparado internamente.
- **FR-003**: Quando o consumo do mês corrente de um tenant atinge o `monthly_message_limit`, o sistema DEVE deixar de gerar resposta do agente às mensagens seguintes daquele tenant, sem enviar nenhuma mensagem automática de "limite atingido" ao cliente final.
- **FR-003a**: Toda vez que uma mensagem de cliente final for bloqueada por limite atingido, o sistema DEVE registrar esse bloqueio (log estruturado ou métrica), identificável por tenant, de forma que o suporte consiga confirmar que um tenant está sendo bloqueado sem depender do e-mail de 100%.
- **FR-004**: O sistema DEVE permitir cadastrar múltiplos `notification_emails` por tenant (lista), editáveis no cadastro e na edição do tenant.
- **FR-005**: O sistema DEVE manter uma lista global `global_notification_recipients` (e-mails internos da InterasisAI), cadastrável dinamicamente via tela de "Configurações Globais", com fallback para `contato@interasisai.com.br` quando vazia.
- **FR-006**: O sistema DEVE disparar um e-mail aos `notification_emails` do tenant ao cruzar 50% do limite, com mensagem indicando quantas mensagens já foram usadas do total.
- **FR-007**: O sistema DEVE disparar um e-mail aos `notification_emails` do tenant ao cruzar 80% do limite, com mensagem indicando quantas mensagens restam até o bloqueio.
- **FR-008**: O sistema DEVE disparar um e-mail aos `notification_emails` do tenant E a todos os `global_notification_recipients` (ou ao fallback) ao atingir 100% do limite (bloqueio).
- **FR-009**: Cada alerta de marco (50%, 80%, 100%) DEVE ser enviado no máximo uma vez por tenant por mês; se uma única chamada fizer o consumo pular diretamente por mais de um marco (ex.: de 45% para 85%), os e-mails de todos os marcos cruzados nessa chamada DEVEM ser disparados em sequência (ex.: 50% e depois 80%), cada um ainda respeitando o limite de uma vez por mês.
- **FR-010**: O sistema DEVE disparar um e-mail de reset aos `notification_emails` do tenant quando o ciclo mensal reinicia (o mecanismo de reset em si é tratado em ticket separado — EDI-64).
- **FR-011**: A UI de admin do tenant DEVE permitir definir/editar `monthly_message_limit` e gerenciar (adicionar/remover) `notification_emails`.
- **FR-012**: A UI de admin DEVE exibir o consumo atual do mês do tenant (mensagens usadas / limite / percentual), com destaque visual por cor (verde <50%, amarelo 50-80%, vermelho ≥80%).
- **FR-013**: A UI de admin DEVE oferecer uma tela de "Configurações Globais" para listar, adicionar e remover e-mails de `global_notification_recipients`.
- **FR-013a**: Ao configurar o `monthly_message_limit` de um tenant, a UI de admin DEVE deixar claro que a contagem é por chamada de LLM (não por mensagem real do cliente final), exibindo ao lado do campo uma estimativa de quantas mensagens reais de clientes finais aquele limite costuma representar.
- **FR-013b**: A área admin DEVE oferecer uma calculadora de dimensionamento de plano, independente da edição de um tenant específico: o admin informa um número de chamadas de LLM e um cenário de nós acionados por mensagem (no mínimo "pior caso" — todos os nós do fluxo acionados em toda mensagem — e "médio" — razão configurável, ex.: ~3-4 nós), e o sistema calcula e exibe a estimativa correspondente de mensagens reais de clientes finais (chamadas ÷ nós por mensagem), recalculando ao vivo quando os valores de entrada mudam, sem persistir nada.
- **FR-014**: Quando a gravação direta de um registro de uso em `chat_token_usage` falhar, o sistema DEVE publicar esse registro em uma fila de retry (Redis Streams) em vez de apenas descartá-lo/logá-lo.
- **FR-015**: Um worker dedicado DEVE consumir a fila de retry e gravar cada registro pendente em `chat_token_usage`, confirmando (`XACK`) somente após a gravação ser bem-sucedida.
- **FR-016**: Ao subir, o worker DEVE verificar e reprocessar qualquer backlog de mensagens pendentes na fila de retry (inclusive as que ficaram pendentes por o próprio worker ter caído no meio do processamento anterior), antes de considerar a fila em dia.
- **FR-017**: A infraestrutura de Redis usada pela fila de retry DEVE ter persistência habilitada (AOF), para que um restart do Redis não descarte registros ainda não confirmados.
- **FR-018**: Após um número configurável de tentativas de reprocessamento sem sucesso, uma entrada da fila de retry DEVE ser movida para uma fila/lista de dead-letter separada, preservando `tenant_id`, horário original e `thread_id`, e disparando um alerta para investigação manual. Um painel de visualização dedicado da dead-letter fica fora do escopo desta feature (ticket futuro), mas os dados já devem sair estruturados por tenant/horário/thread_id para viabilizá-lo depois.

### Key Entities *(include if feature involves data)*

- **Tenant** (extensão): ganha `monthly_message_limit` (inteiro, opcional) e `notification_emails` (lista de e-mails, opcional).
- **Global Notification Recipient**: e-mail interno da InterasisAI que recebe todos os alertas de bloqueio (100%) de qualquer tenant; possui estado ativo/inativo.
- **Registro de Custo de Token** (`chat_token_usage`, já existente via EDI-60): fonte usada para contar o consumo mensal por tenant.
- **Entrada da Fila de Retry**: representação de um registro de uso de token ainda não confirmado em `chat_token_usage`, pendente de reprocessamento pelo worker.
- **Entrada de Dead-Letter**: entrada da fila de retry que esgotou o número de tentativas de reprocessamento, movida para investigação manual; preserva `tenant_id`, horário original e `thread_id`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das mensagens de um tenant que ultrapassa o `monthly_message_limit` deixam de gerar resposta do agente, sem nenhuma mensagem de erro perceptível ao cliente final.
- **SC-002**: Tenants sem `monthly_message_limit` configurado mantêm exatamente o comportamento atual (sem nenhuma alteração perceptível).
- **SC-003**: Cada marco de consumo (50%, 80%, 100%) gera no máximo um e-mail por tenant por mês, mesmo sob rajadas de mensagens.
- **SC-004**: Um admin consegue configurar limite e e-mails de notificação de um tenant e ver o resultado refletido no indicador de consumo em menos de um ciclo de atualização de página (sem necessidade de suporte técnico).
- **SC-005**: Uma indisponibilidade temporária do banco de dados (até o tempo de recuperação típico de infraestrutura) não causa perda de nenhum registro de contagem de uso — todo registro pendente é gravado assim que o banco volta, sem duplicação.

## Assumptions

- O mecanismo de reset automático do contador mensal (atrelado a uma data de ciclo/pagamento) é tratado em ticket separado (EDI-64); esta feature apenas dispara o e-mail de reset quando esse reset ocorre, mas não implementa o próprio disparo do reset.
- BYOK (chave de API própria do tenant), citado no título original do ticket, foi arquivado por inviável e está fora do escopo desta feature.
- O limite é agregado por tenant (soma de todos os clientes finais dele) — não há limite por cliente final individual dentro de um tenant.
- Redis já está disponível na infraestrutura do projeto (presente em `docker-compose.yml`/`docker-compose-local.yml`), portanto a fila de retry (US4) reaproveita essa infraestrutura em vez de introduzir uma nova dependência.
- A contagem do limite mensal é por chamada real de LLM (linha em `chat_token_usage`), não por mensagem real do cliente final — ver seção Clarifications. Exemplo comercial: se o fluxo típico de uma mensagem dispara ~3 chamadas de LLM (roteador + operacional + eventual retry), um plano vendido como "1000 mensagens/mês" ao tenant deve ser configurado como `monthly_message_limit` ≈ 3000; essa razão é um valor de referência/configurável, não uma constante fixa no código.
- O número exato de tentativas antes de mover uma entrada para a dead-letter (FR-018), e a razão de chamadas-por-mensagem usada como estimativa na UI (FR-013a) e como cenário "médio" da calculadora (FR-013b), são parâmetros configuráveis cujos valores padrão serão definidos em `/speckit.plan`.
- Levantamento atual dos nós do agente que geram chamada de LLM (`modules/ia/agent_graph.py`): `routing_agent` (sempre roteia primeiro), e depois exatamente um entre `institutional_node`, `chitchat_node` ou `operational_node` — sendo que `operational_node` pode chamar o LLM uma segunda vez (retry de guardrail com `tool_choice="required"`). Pior caso hoje por mensagem: 3 chamadas (`routing_agent` + `operational_node` + retry). O cenário "pior caso" da calculadora (FR-013b) deve usar esse número, revisitável conforme novos nós forem adicionados ao agente.

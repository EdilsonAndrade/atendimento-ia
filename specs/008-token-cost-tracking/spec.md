# Feature Specification: Rastreamento de custo de token por conversa e tenant

**Feature Branch**: `edilsonaandrade/edi-60-rastrear-custo-de-token-por-conversatenant-usando`
**Created**: 2026-08-23
**Status**: Draft
**Input**: User description: "Rastrear custo de token por conversa/tenant usando usage_metadata do LangGraph (EDI-60) — medir em tempo real o gasto por token por conversa por tenant, usando o mecanismo nativo do LangChain/LangGraph (usage_metadata), e armazenar em uma tabela 1:N (uma conversa tem N registros de custo por token). Cada registro deve indicar qual tipo de nó gerou o custo (operational_node, roteador/chitchat, etc.) e ficar aberto para incluir outros nós no futuro. Deve ter created_at para permitir purga futura de dados antigos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada chamada ao LLM tem seu custo registrado automaticamente (Priority: P1)

Toda vez que o agente chama o LLM (para rotear a intenção, responder institucional, conversar (chitchat) ou executar o fluxo operacional de agendamento), o sistema registra quantos tokens de entrada e saída foram consumidos naquela chamada específica, o custo estimado correspondente, de qual tenant e de qual conversa ela veio, e qual nó do agente a originou — sem que isso afete a resposta dada ao cliente nem sua latência de forma perceptível.

**Why this priority**: é a capacidade central do ticket — sem isso, não existe nenhum dado de custo para agregar por tenant ou por conversa.

**Independent Test**: enviar uma mensagem de chat que aciona pelo menos o roteador e o nó operacional, e confirmar que aparecem registros de uso de token para cada uma dessas chamadas, com tenant, conversa e nó corretos.

**Acceptance Scenarios**:

1. **Given** uma mensagem de cliente que aciona o roteador e o nó operacional, **When** o agente processa a mensagem, **Then** um registro de uso de token é persistido para a chamada do roteador e outro para a chamada do nó operacional, cada um com seu próprio `node_type`.
2. **Given** um registro de uso de token persistido, **When** ele é consultado, **Then** contém tokens de entrada, tokens de saída, custo estimado, `tenant_id` e identificador da conversa.
3. **Given** uma falha ao persistir um registro de uso de token (ex.: banco temporariamente indisponível), **When** isso ocorre, **Then** a resposta ao cliente não é afetada nem atrasada por causa dessa falha.

---

### User Story 2 - Custos ficam agrupáveis por conversa e por tenant, prontos para purga futura (Priority: P2)

Cada registro de custo de token referencia a conversa (`base_thread_id`) e o tenant a que pertence, de forma que seja possível somar o custo total de uma conversa específica ou de todos os atendimentos de um tenant. Cada registro também guarda a data de criação, para que uma rotina futura de retenção possa apagar registros antigos sem exigir mudança de schema.

**Why this priority**: sem isso, os dados de custo existem mas não são úteis para nenhuma decisão de negócio (quanto um tenant custa, quais conversas são mais caras) nem sustentáveis a longo prazo (tabela cresce sem limite).

**Independent Test**: gerar registros de custo para duas conversas de tenants diferentes, e confirmar que é possível somar o custo de cada conversa e de cada tenant separadamente a partir dos campos persistidos; confirmar que todo registro tem `created_at` preenchido.

**Acceptance Scenarios**:

1. **Given** múltiplos registros de custo de uma mesma conversa, **When** agrupados por `base_thread_id`, **Then** o custo total daquela conversa pode ser calculado somando os registros.
2. **Given** múltiplos registros de custo de tenants diferentes, **When** agrupados por `tenant_id`, **Then** o custo total de cada tenant pode ser calculado separadamente.
3. **Given** qualquer registro de custo, **When** consultado, **Then** possui `created_at` preenchido, utilizável por uma rotina de purga futura (fora do escopo desta feature).

---

### Edge Cases

- Uma chamada ao LLM não retorna informação de uso de token (`usage_metadata` ausente ou incompleto) — o sistema não deve falhar nem bloquear a resposta ao cliente; o registro pode ficar incompleto ou não ser gravado, mas o fluxo de conversa segue normalmente.
- Um nó novo é adicionado futuramente ao agente (além de roteador, institucional, chitchat e operacional) — deve ser possível registrar o custo desse nó novo usando o mesmo mecanismo, sem exigir uma nova migration de schema.
- O nó operacional tenta uma segunda chamada ao LLM (retry com `tool_choice="required"`, mecanismo de guardrail já existente) — cada chamada real ao LLM gera seu próprio registro de custo, refletindo o custo real incorrido, não apenas uma chamada "lógica".
- Um tenant só usa nós de chitchat/institucional, sem nenhuma tool de agendamento ativa — o rastreamento de custo funciona igual, sem depender de agendamento estar habilitado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE capturar as métricas de uso de token (tokens de entrada, tokens de saída) nativamente devolvidas pelo LLM a cada chamada, sem estimativa manual.
- **FR-002**: O sistema DEVE registrar, para cada chamada ao LLM, o `tenant_id`, o identificador da conversa (`base_thread_id`) e o tipo de nó do agente que originou a chamada (ex.: `operational_node`, `routing_agent`, `chitchat_node`, `institutional_node`).
- **FR-003**: O sistema DEVE calcular e persistir um custo estimado para cada chamada, a partir dos tokens de entrada/saída e de um valor por token configurável.
- **FR-004**: O sistema DEVE persistir cada chamada ao LLM como um registro individual (não agregado), de forma que múltiplas chamadas da mesma conversa fiquem associadas a ela (relação 1:N conversa → registros de custo).
- **FR-005**: O sistema DEVE registrar a data/hora de criação de cada registro de custo.
- **FR-006**: Uma falha ao registrar o custo de uma chamada NÃO DEVE impedir, atrasar de forma perceptível, nem alterar a resposta dada ao cliente.
- **FR-007**: O modelo de dados DEVE permitir adicionar o rastreamento de custo a novos nós do agente no futuro sem exigir alteração de schema (o tipo do nó é um valor de dado, não uma coluna ou tabela por nó).
- **FR-008**: O sistema DEVE cobrir com o rastreamento de custo todas as chamadas ao LLM existentes hoje no agente: roteador, institucional, chitchat, operacional (incluindo a chamada de retry com `tool_choice="required"` do operacional).

### Key Entities *(include if feature involves data)*

- **Registro de Custo de Token**: um registro por chamada real ao LLM, contendo tenant, conversa, tipo de nó, tokens de entrada/saída, custo estimado e data de criação.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das chamadas ao LLM feitas pelo agente (roteador, institucional, chitchat, operacional, incluindo retries) geram um registro de custo correspondente, quando o LLM devolve informação de uso de token.
- **SC-002**: O custo total de qualquer conversa ou tenant pode ser obtido somando os registros persistidos, sem necessidade de reprocessar mensagens.
- **SC-003**: Uma falha na persistência do registro de custo nunca resulta em erro, atraso perceptível ou alteração da resposta ao cliente.
- **SC-004**: Adicionar rastreamento de custo a um nó novo do agente não exige nenhuma migration de banco — apenas identificar esse nó com um novo valor de `node_type` nas chamadas já existentes ao mecanismo de registro.

## Assumptions

- O valor monetário por token é configurável (variável de ambiente), pois pode mudar conforme o plano/contrato do provedor do LLM (DeepSeek); esta feature não é responsável por manter esse valor atualizado automaticamente.
- Não é criado nenhum endpoint HTTP de consulta/agregação de custo nesta feature — o ticket pede apenas a captura e persistência dos dados; uma UI/relatório de custo por tenant é um consumidor futuro, possivelmente com ticket próprio.
- A rotina de purga de registros antigos (mencionada como motivação para `created_at`) está fora do escopo desta feature — apenas o campo que a viabiliza é entregue aqui.
- O identificador de conversa usado para agrupar custos é o `base_thread_id` (o mesmo identificador estável do cliente já usado por `chat_thread_sessions`/`chat_thread_summaries`, ver EDI-59), não o `active_thread_id` de sessão, que muda a cada expiração por inatividade.
- Por ser uma capacidade nova (não uma correção pontual em módulo legado), esta feature é implementada como um módulo novo (`modules/token_usage/`), seguindo a Arquitetura Modular Limpa (Princípio III da constituição) desde o primeiro commit — diferente do EDI-59, que alterou apenas módulos legados já existentes.

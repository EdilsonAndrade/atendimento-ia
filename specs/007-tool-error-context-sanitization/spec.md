# Feature Specification: Sanitização do contexto de conversa enviado ao LLM

**Feature Branch**: `edilsonaandrade/edi-59-sanitizar-contexto-de-conversa-enviado-ao-llm-erros-janela-e`
**Created**: 2026-08-23
**Status**: Draft
**Input**: User description: "Sanitizar contexto de conversa enviado ao LLM (erros, janela e tipagem das tools) (EDI-59) — tools do agente de agendamento devolvem exceção crua (str(e)) como ToolMessage, poluindo o histórico reenviado ao LLM a cada turno e causando respostas erradas após falhas internas (DB, Google Calendar API). Também é necessário aumentar a janela de mensagens enviada ao LLM de 50 para 95, padronizar a tipagem de retorno de todas as tools, e implementar uma camada de resumo + fatos estruturados ao fim/expiração da sessão."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cliente não recebe nem contamina a conversa com erro técnico interno (Priority: P1)

Durante um atendimento, uma tool do agente falha por um motivo técnico interno (erro de conexão com o banco, erro da API do Google Calendar, condição de corrida em um horário já ocupado por outro atendimento simultâneo). Hoje, o texto bruto da exceção (podendo conter detalhes de infraestrutura) é devolvido como resposta da tool e fica salvo no histórico da conversa, sendo reenviado ao LLM em todos os turnos seguintes — o que já foi observado causando respostas incorretas do agente depois de uma falha. Com a correção, o cliente recebe uma mensagem curta e seguravel de que algo deu errado e pode tentar novamente, o erro técnico completo fica registrado nos logs da aplicação para investigação, e o histórico da conversa enviado ao LLM não carrega mais o texto bruto da exceção.

**Why this priority**: É a causa raiz do problema relatado — o LLM respondendo de forma errada após uma falha interna. Sem essa correção, as demais melhorias desta feature não resolvem o sintoma que motivou o ticket.

**Independent Test**: Forçar uma falha em uma tool (ex.: desconectar o banco temporariamente ou simular exceção) durante uma conversa, confirmar que a resposta ao cliente é genérica e não contém o texto da exceção, que o erro completo aparece no log da aplicação, e que uma nova pergunta do cliente no mesmo turno/sessão não é respondida de forma incoerente por causa do erro anterior.

**Acceptance Scenarios**:

1. **Given** uma tool de agendamento lança uma exceção durante a execução, **When** o erro é capturado, **Then** o conteúdo devolvido como `ToolMessage` ao LLM é uma mensagem curta e genérica, sem stack trace, sem texto de driver de banco ou de API externa.
2. **Given** uma tool lança uma exceção, **When** o erro é capturado, **Then** o erro completo (mensagem original, tipo da exceção, tenant_id e thread_id quando disponíveis) é registrado no log da aplicação.
3. **Given** um erro técnico já ocorreu em um turno anterior da mesma sessão, **When** o cliente envia uma nova mensagem não relacionada ao erro, **Then** o agente responde normalmente à nova pergunta, sem repetir ou reagir ao erro anterior.

---

### User Story 2 - Conversas mais longas mantêm contexto relevante sem cortar cedo demais (Priority: P2)

Em conversas que envolvem várias idas e vindas com uso de tools (consultar disponibilidade, negociar horário, confirmar, tirar dúvidas via base de conhecimento), a janela de histórico enviada ao LLM hoje é limitada a 50 mensagens totais (contando também as mensagens internas de tool), o que na prática representa poucas trocas reais quando o fluxo usa bastante ferramentas. Aumentar essa janela reduz a chance de o agente "esquecer" informações dadas pelo cliente no início de uma conversa mais longa.

**Why this priority**: Melhora a qualidade da experiência em conversas longas, mas não é a causa do bug relatado (por isso P2, depois da correção de erro).

**Independent Test**: Simular uma conversa com mais de 50 mensagens totais (incluindo tool calls/respostas) e confirmar que informações fornecidas pelo cliente dentro da janela de 95 mensagens continuam disponíveis ao LLM no turno atual.

**Acceptance Scenarios**:

1. **Given** uma sessão de conversa com até 95 mensagens totais no histórico, **When** o agente monta o prompt para o LLM, **Then** todas essas mensagens (respeitando o corte por `start_on="human"`) são incluídas.
2. **Given** uma sessão com mais de 95 mensagens, **When** o agente monta o prompt, **Then** apenas as últimas 95 são incluídas, mantendo o mesmo comportamento de corte seguro já existente (nunca iniciar com uma `ToolMessage` órfã).

---

### User Story 3 - Tipagem de retorno consistente em todas as tools do agente (Priority: P2)

As funções decoradas com `@tool` usadas pelo agente de agendamento devem declarar explicitamente seu tipo de retorno, para deixar claro (para quem desenvolve e para ferramentas de análise estática) que toda tool devolve texto simples ao LLM, e para facilitar a aplicação uniforme da sanitização de erro da User Story 1.

**Why this priority**: É uma correção de consistência que sustenta a User Story 1 (o wrapper de sanitização de erro parte do pressuposto de que toda tool devolve `str`), mas não tem efeito observável isolado para o cliente final — por isso mesma prioridade da US2, decidido pela ordem de dependência técnica.

**Independent Test**: Rodar checagem de tipos (ou inspeção do código) em todas as funções `@tool` do módulo `modules/agendamento` e confirmar que todas declaram `-> str`.

**Acceptance Scenarios**:

1. **Given** o conjunto de funções `@tool` usadas pelo agente, **When** o código é revisado, **Then** todas declaram explicitamente `-> str` como tipo de retorno.

---

### User Story 4 - Resumo e fatos estruturados da sessão ficam disponíveis para conversas futuras (Priority: P3)

Quando uma sessão de conversa expira por inatividade (mecanismo já existente via `CHAT_SESSION_IDLE_MINUTES`) ou termina, o sistema gera um resumo curto e um conjunto de fatos estruturados (nome do cliente, interesse/serviço demonstrado, objeção levantada, resultado da conversa) e os disponibiliza para serem injetados no contexto de uma conversa futura do mesmo cliente (mesmo `base_thread_id`), complementando o transcript bruto (já persistido integralmente) e a base de conhecimento (RAG, já existente).

**Why this priority**: É uma melhoria de continuidade entre sessões, valiosa mas independente das correções de conteúdo/janela — pode ser entregue depois, sem bloquear as demais.

**Independent Test**: Encerrar uma sessão (por expiração de inatividade) que contenha nome do cliente e um serviço de interesse mencionado, e confirmar que um resumo curto e os fatos estruturados correspondentes ficam gravados e associados ao `base_thread_id`, prontos para serem consultados na próxima sessão desse mesmo cliente.

**Acceptance Scenarios**:

1. **Given** uma sessão de conversa que expira por inatividade, **When** a expiração é detectada, **Then** um resumo curto (texto) e fatos estruturados (nome, interesse, objeção, resultado — quando identificáveis na conversa) são gerados e persistidos, associados ao `base_thread_id`.
2. **Given** um `base_thread_id` com resumo/fatos estruturados de uma sessão anterior, **When** o cliente inicia uma nova sessão dentro desse mesmo `base_thread_id`, **Then** esse resumo fica disponível para ser injetado no contexto do agente, da mesma forma que hoje já ocorre com os dados de contato via `build_customer_context_block`.
3. **Given** uma sessão sem nenhuma informação relevante de cliente/interesse (ex.: conversa que não avançou), **When** a sessão expira, **Then** o sistema não é obrigado a gerar fatos estruturados vazios ou inventados — campos sem informação ficam ausentes/nulos, nunca preenchidos com suposição.

---

### Edge Cases

- Uma tool falha por um erro esperado de regra de negócio (ex.: horário já ocupado) — essa mensagem já é uma mensagem de negócio válida hoje (não é uma exceção crua) e deve continuar sendo enviada ao LLM normalmente, sem ser tratada como "erro técnico" a sanitizar.
- Duas exceções técnicas diferentes ocorrem na mesma sessão, em turnos distintos — cada uma deve ser sanitizada e logada independentemente, sem acumular ruído no histórico.
- A geração do resumo/fatos estruturados (US4) falha (ex.: erro na chamada ao LLM de resumo) — a expiração da sessão e o início de uma nova sessão não podem ficar bloqueados por essa falha; o sistema segue sem resumo disponível para aquele ciclo.
- Uma sessão expira sem nunca ter tido troca de mensagens suficiente para gerar um resumo útil — não gerar resumo/fatos nesse caso.
- Uma conversa ultrapassa a nova janela de 95 mensagens sem nunca ter tido nenhum erro — comportamento de corte segue idêntico ao já existente, apenas com o novo tamanho.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE capturar exceções técnicas lançadas pelas tools do agente de agendamento (banco de dados, API do Google Calendar, e demais falhas não esperadas) antes de devolvê-las como resultado da tool.
- **FR-002**: Quando uma exceção técnica for capturada, o sistema DEVE devolver ao LLM (como conteúdo da `ToolMessage`) uma mensagem curta, genérica e seguravel para o cliente, sem stack trace, sem texto originado do driver de banco de dados ou de API externa.
- **FR-003**: Quando uma exceção técnica for capturada, o sistema DEVE registrar nos logs da aplicação o erro completo (mensagem original e tipo da exceção), incluindo `tenant_id` e identificador de sessão/thread quando disponíveis no contexto da chamada.
- **FR-004**: O sistema NÃO DEVE aplicar a sanitização de FR-002/FR-003 a mensagens de negócio válidas devolvidas intencionalmente pelas tools (ex.: "horário já ocupado"), apenas a exceções técnicas não tratadas.
- **FR-005**: O sistema DEVE aumentar a janela de mensagens consideradas na montagem do prompt do LLM (nó operacional) de 50 para 95 mensagens, preservando o comportamento atual de corte (`start_on="human"`, `end_on=("human", "tool")`).
- **FR-006**: Todas as funções `@tool` usadas pelo agente de agendamento DEVEM declarar explicitamente o tipo de retorno `-> str`.
- **FR-007**: O sistema DEVE gerar, ao detectar a expiração de uma sessão por inatividade, um resumo curto em texto da sessão encerrada.
- **FR-008**: O sistema DEVE extrair, quando identificáveis na conversa, fatos estruturados da sessão encerrada: nome do cliente, interesse/serviço demonstrado, objeção levantada (se houver) e resultado da conversa (ex.: agendou, não agendou, apenas tirou dúvida).
- **FR-009**: O sistema DEVE persistir o resumo e os fatos estruturados associados ao `base_thread_id`, de forma que fiquem recuperáveis por uma sessão futura do mesmo cliente.
- **FR-010**: Uma falha na geração do resumo/fatos estruturados (FR-007/FR-008) NÃO DEVE impedir nem atrasar a expiração normal da sessão ou o início de uma nova sessão para o cliente.
- **FR-011**: O sistema NÃO DEVE inventar ou supor valores para campos de fatos estruturados que não puderem ser identificados com base real na conversa — campos não identificados ficam ausentes.

### Key Entities *(include if feature involves data)*

- **Resumo de Sessão**: registro associado a um `base_thread_id`, contendo um resumo textual curto e os fatos estruturados (nome, interesse, objeção, resultado) extraídos de uma sessão de conversa encerrada por expiração de inatividade.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das exceções técnicas capturadas nas tools do agente resultam em uma `ToolMessage` sem texto de exceção crua (stack trace, erro de driver, erro de API externa) chegando ao LLM ou ao cliente.
- **SC-002**: 100% dos erros técnicos capturados ficam registrados de forma completa e correlacionável (tenant/sessão) nos logs da aplicação.
- **SC-003**: Após uma falha técnica em uma tool, a próxima pergunta do cliente no mesmo turno/sessão recebe uma resposta coerente com a pergunta feita, sem menção ao erro técnico anterior.
- **SC-004**: Conversas com até 95 mensagens totais no histórico preservam informações fornecidas pelo cliente no início da conversa disponíveis para o LLM no turno atual.
- **SC-005**: 100% das funções `@tool` do módulo de agendamento declaram `-> str` como tipo de retorno.
- **SC-006**: Sessões que expiram por inatividade e contêm informação de cliente identificável geram resumo e fatos estruturados recuperáveis pelo próximo atendimento do mesmo `base_thread_id`.

## Assumptions

- O corte de sessão por inatividade (`CHAT_SESSION_IDLE_MINUTES`, `modules/ia/thread_session.py`) permanece inalterado — esta feature não substitui nem remove esse mecanismo, apenas complementa com resumo/fatos estruturados (US4).
- "Mensagem curta e genérica" para o cliente (FR-002) não precisa ser idêntica em todas as tools — cada tool pode ter uma mensagem de fallback própria e adequada ao contexto (ex.: agendamento vs. consulta), desde que nunca inclua detalhe técnico.
- A geração do resumo/fatos estruturados (US4) pode usar uma chamada adicional ao LLM já configurado no projeto (DeepSeek via `ChatOpenAI`), seguindo o padrão de custo baixo (~200 tokens) mencionado no ticket de origem.
- O armazenamento do resumo/fatos estruturados (FR-009) é feito em PostgreSQL, reaproveitando a infraestrutura de conexão já existente (`infrastructure/connection.py`), consistente com o restante do projeto.
- Esta feature não cobre a rotina de purga/retenção de dados antigos (mensagens, resumos) — está fora de escopo, tratada em ticket(s) separado(s) quando necessário.

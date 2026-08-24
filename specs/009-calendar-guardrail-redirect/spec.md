# Feature Specification: Impedir confirmação de agendamento sem ação real no calendário

**Feature Branch**: `edilsonaandrade/edi-61-agendamentos-fantasma-institutional_nodechitchat_node`
**Created**: 2026-08-24
**Status**: Draft
**Input**: User description: "Feature ligada ao ticket Linear EDI-61 (InterasisAI). Corrigir 'agendamentos fantasma': quando o routing_agent classifica incorretamente um turno de confirmação/consulta de agenda como INSTITUTIONAL ou CHITCHAT, o institutional_node e o chitchat_node não têm nenhuma tool de calendário vinculada e vão direto para END — então o LLM pode narrar em texto uma confirmação de agendamento sem que o evento tenha sido criado de fato no Google Calendar. Requisitos: (1) redirecionar para o operational_node em vez de END quando detectada confirmação sem tool; (2) corrigir o prompt do routing_agent para permitir a saída CONTINUATION; (3) o resumidor de sessão não deve persistir alegações de agendamento sem ToolMessage real; (4) padronizar logs de todas as tools de calendário e do redirecionamento de guardrail com tags fixas e fáceis de localizar em produção."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cliente nunca recebe confirmação de agenda que não existe (Priority: P1)

Um cliente está conversando com o assistente sobre agendar, consultar ou cancelar um horário. Em algum turno, o classificador de intenção interpreta errado a mensagem do cliente (por exemplo, confunde uma resposta curta como "pode ser às 9" ou um e-mail digitado isoladamente com uma pergunta institucional ou papo informal). Mesmo assim, o cliente nunca deve receber um texto que dê a entender que um horário foi consultado, reservado ou cancelado, a menos que essa ação tenha realmente acontecido no calendário.

**Why this priority**: É a falha que já causou dano real em produção — cliente combinou uma sessão com a empresa, recebeu confirmação, e o horário simplesmente não existia quando ele foi conferir. Isso quebra a confiança no atendimento e pode gerar prejuízo (cliente que não aparece porque a empresa nunca soube do encontro real, ou vice-versa).

**Independent Test**: Forçar deliberadamente uma classificação incorreta de um turno de confirmação de agenda (ou simular a resposta do classificador) e verificar que a resposta final entregue ao cliente só confirma/relata algo sobre o calendário depois de uma ação real ter sido executada no turno.

**Acceptance Scenarios**:

1. **Given** um cliente enviando uma mensagem de continuação de um fluxo de agendamento (ex.: confirmando nome, e-mail ou horário) que acaba sendo processada fora do fluxo operacional de agenda, **When** o sistema gera uma resposta que teria conteúdo de confirmação/consulta de agenda sem nenhuma ação real de calendário no turno, **Then** o sistema deve completar a ação de calendário de verdade antes de responder ao cliente, em vez de apenas descrever a ação em texto.
2. **Given** um cliente perguntando algo puramente institucional (ex.: "qual o site da empresa?") sem qualquer relação com agenda, **When** o sistema responde, **Then** a resposta não deve ser desviada nem atrasada — o comportames institucional atual continua funcionando normalmente.

---

### User Story 2 - Fatos de conversas passadas não repetem alucinações (Priority: P2)

Quando uma conversa fica muito tempo inativa, o sistema gera um resumo automático que é reaproveitado em conversas futuras com o mesmo cliente. Se, por qualquer motivo, uma sessão anterior tiver produzido um relato de agendamento sem que a ação real tivesse ocorrido, esse relato falso não deve ser gravado como "resultado confirmado" no resumo, para não contaminar o atendimento nas próximas conversas com esse cliente.

**Why this priority**: É a camada que perpetua o erro mesmo depois de a causa direta ser corrigida — sem isso, o dano de uma eventual falha residual continua se propagando para novas conversas do mesmo cliente.

**Independent Test**: Gerar uma sessão cujo histórico contenha um texto de confirmação de agendamento sem nenhuma ação real de calendário associada, forçar a expiração da sessão, e verificar que o resumo gerado não declara o agendamento como confirmado.

**Acceptance Scenarios**:

1. **Given** uma sessão expirada cujo histórico contém uma alegação em texto de agendamento confirmado mas nenhuma ação real de calendário correspondente, **When** o resumo da sessão é gerado, **Then** o campo de resultado não deve declarar o agendamento como confirmado.
2. **Given** uma sessão expirada cujo histórico contém uma ação real de calendário concluída com sucesso, **When** o resumo da sessão é gerado, **Then** o campo de resultado deve continuar refletindo corretamente esse resultado real.

---

### User Story 3 - Equipe consegue investigar rapidamente qualquer chamada real ao calendário (Priority: P3)

Quando a equipe técnica precisa investigar uma dúvida ou reclamação sobre agendamento ("o cliente diz que agendou, mas não aparece"), ela precisa conseguir localizar rapidamente nos registros da aplicação se e quando uma ação real de calendário (criar, consultar, cancelar) foi executada para aquele atendimento, e também identificar os casos em que o sistema chegou a interceptar uma tentativa de confirmação sem ação real.

**Why this priority**: Não impede o problema por si só, mas é o que permite confirmar que a correção está funcionando em produção e diagnosticar rapidamente qualquer caso residual, reduzindo o tempo de investigação de incidentes como o que originou este pedido.

**Independent Test**: Provocar cada tipo de ação de calendário (criar, consultar, cancelar) e o cenário de interceptação de confirmação sem ação real, e verificar que cada um pode ser localizado nos registros da aplicação de forma inequívoca e sem precisar vasculhar manualmente todo o texto da conversa.

**Acceptance Scenarios**:

1. **Given** uma ação de calendário (criar, consultar ou cancelar) executada com sucesso ou com falha, **When** a operação termina, **Then** deve existir um registro localizável que identifique claramente o tipo de operação, o resultado e os dados mínimos para rastreá-la (tenant, período/horário e identificador do evento quando aplicável).
2. **Given** uma tentativa de confirmação de agenda sem ação real que foi interceptada e redirecionada, **When** isso ocorre, **Then** deve existir um registro localizável que identifique essa interceptação separadamente das operações reais de calendário.

### Edge Cases

- O que acontece se, mesmo depois do redirecionamento, a ação real de calendário também falhar (ex.: Google Calendar indisponível)? O cliente deve ser informado da falha real, nunca de uma confirmação.
- O que acontece se o cliente fizer múltiplos pedidos de agendamento na mesma mensagem, e essa mensagem for a que sofre o redirecionamento? O comportamento de "um agendamento por vez" já existente deve continuar sendo respeitado depois do redirecionamento.
- O que acontece com tenants que não têm agenda/calendário habilitado? Nenhuma mudança de comportamento é esperada para eles — não há ação de calendário real possível, então não há o que redirecionar.
- O que acontece se uma pergunta institucional legítima contiver, incidentalmente, palavras parecidas com confirmação de horário (ex.: perguntar sobre o horário de funcionamento da empresa)? Isso não deve ser tratado como confirmação de agendamento nem disparar o redirecionamento.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST impedir que qualquer resposta entregue ao cliente afirme ou dê a entender que uma consulta, criação ou cancelamento de horário ocorreu, a menos que essa ação tenha sido executada de fato no mesmo turno.
- **FR-002**: Quando o sistema identificar que está prestes a entregar uma resposta desse tipo sem a ação real correspondente, MUST completar a ação de calendário de verdade antes de responder, reaproveitando o mesmo fluxo/regras de negócio já usado para agendamento (inclusive as regras de múltiplos agendamentos, privacidade de calendário e horário de funcionamento), em vez de duplicar essas regras em outro lugar.
- **FR-003**: O comportamento de perguntas institucionais e de conversa casual sem relação com agenda MUST continuar funcionando normalmente, sem atraso ou desvio perceptível para o cliente.
- **FR-004**: O classificador de intenção MUST ser capaz de reconhecer e agir corretamente sobre mensagens de continuação de um fluxo em andamento (ex.: respostas curtas que só fazem sentido no contexto do turno anterior), sem ficar preso a uma saída que não contempla esse caso.
- **FR-005**: Ao gerar o resumo de uma sessão expirada, o sistema MUST NOT registrar como fato confirmado uma alegação de agendamento que não tenha uma ação real de calendário correspondente no histórico da conversa.
- **FR-006**: O sistema MUST manter um registro localizável para cada ação real de calendário (criação, consulta e cancelamento de evento), incluindo no mínimo: identificação do tenant, tipo de operação, resultado (sucesso ou falha) e os dados necessários para localizar o evento/período envolvido.
- **FR-007**: O sistema MUST manter um registro localizável e distinto sempre que uma tentativa de confirmação sem ação real for detectada e redirecionada para a execução real, incluindo tenant, origem da tentativa e identificação da conversa.
- **FR-008**: O fluxo de reagendamento (que envolve cancelar um horário e criar outro) MUST ter cada uma das duas etapas registrada de forma localizável, seguindo o mesmo padrão das demais ações de calendário.

### Key Entities

- **Registro de ação de calendário**: representa uma tentativa de criar, consultar ou cancelar um compromisso — quem (tenant), o quê (tipo de operação), quando, e o resultado (sucesso/falha e identificador do evento quando aplicável). Usado para auditoria e investigação de incidentes.
- **Registro de interceptação de confirmação sem ação**: representa um momento em que o sistema percebeu que estava prestes a confirmar algo de agenda sem uma ação real correspondente, e por isso completou a ação de verdade antes de responder. Usado para medir a frequência do problema original e confirmar que a correção está funcionando.
- **Resumo de sessão**: registro estruturado (já existente) gerado ao fim de uma conversa inativa, contendo fatos como nome, interesse e resultado do atendimento; passa a exigir uma ação real de calendário como evidência antes de declarar um agendamento como resultado confirmado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero casos, em amostragem de conversas de produção após o lançamento, em que o cliente recebe uma confirmação de agendamento sem o evento correspondente existir de fato no calendário.
- **SC-002**: 100% das ações reais de calendário (criação, consulta, cancelamento) executadas em produção podem ser encontradas nos registros da aplicação usando um único termo de busca por tipo de operação, sem precisar ler o conteúdo completo da conversa.
- **SC-003**: Toda vez que o sistema intercepta uma tentativa de confirmação sem ação real, a ação de calendário correta é executada e refletida na resposta final ao cliente no mesmo turno, sem exigir uma nova mensagem do cliente.
- **SC-004**: Resumos de sessão gerados após o lançamento não declaram mais um agendamento como "confirmado" quando não há nenhuma ação real de calendário correspondente no histórico da sessão resumida.

## Assumptions

- O padrão de texto que caracteriza uma "confirmação ou consulta de agenda sem ação real" pode continuar sendo detectado de forma heurística (como já ocorre hoje no fluxo operacional), sem exigir um classificador novo — esta feature estende essa detecção para os demais fluxos de conversa, não a reconstrói do zero.
- Persistir o resultado do agendamento em uma tabela própria (fonte de verdade local, além do próprio Google Calendar) é uma melhoria estrutural maior, tratada separadamente e fora do escopo desta entrega — aqui o foco é impedir a confirmação falsa e garantir rastreabilidade via registros/logs.
- O comportamento e as regras de negócio já existentes para o fluxo operacional de agenda (um agendamento por vez, privacidade de calendário, horário de funcionamento, reaproveitamento de dados de contato já informados) continuam válidos e não devem ser duplicados em outro fluxo — apenas reaproveitados quando um caso de outro fluxo precisar da ação real de calendário.
- "Registro localizável" significa que a equipe técnica consegue encontrar a informação relevante nos mecanismos de observabilidade já usados pela aplicação (atualmente, saída de log da aplicação), sem necessidade de uma nova ferramenta de monitoramento.

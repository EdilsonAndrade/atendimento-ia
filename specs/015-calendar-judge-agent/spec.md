# Feature Specification: calendar_judge_agent — verificar agendamento real antes de confirmar ao cliente

**Feature Branch**: `edilsonaandrade/edi-72-calendar_judge_agent-verificar-agendamento-real-na-agenda`
**Created**: 2026-09-02
**Status**: Draft
**Input**: Ticket Linear EDI-72 (InterasisAI). "Novo incidente do mesmo tipo do EDI-61, mas desta vez dentro do próprio operational_node. Teste em produção (tenant demo-clinica): a IA respondeu 'Seu agendamento foi confirmado com sucesso!' sem nenhuma chamada de tool. O evento nunca foi criado no Google Calendar. Criar um agente juiz (calendar_judge_agent) que, antes de qualquer resposta de confirmação/consulta/cancelamento chegar ao cliente, verifica de fato na integração de agendamento (consulta_agenda) se a ação ocorreu, usando tenant_id + telefone do cliente + período como chave (thread_id não é chave válida, pois não é persistido no Google Calendar). Se não confirmar, redireciona para o operational_node agendar de verdade."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cliente nunca recebe confirmação de agendamento que não existe de fato no calendário (Priority: P1)

Um cliente conversa com o assistente sobre criar um agendamento. Em algum turno, o modelo gera uma resposta de confirmação em texto (ex.: "Seu agendamento foi confirmado com sucesso!") sem ter chamado a tool `agendar_horario` naquele turno — como já ocorreu em produção. Antes dessa resposta ser entregue ao cliente, o sistema deve verificar de fato, consultando a integração de agendamento (Google Calendar), se o evento correspondente existe. Só então a resposta pode seguir; caso contrário, o sistema deve executar a ação real antes de responder.

**Why this priority**: É a mesma classe de falha do EDI-61, mas confirmada agora acontecendo mesmo dentro do `operational_node` (que já tem o guardrail de regex) — a heurística de texto tem furos que só uma verificação contra a fonte de verdade real fecha.

**Independent Test**: Forçar deliberadamente uma resposta de confirmação de agendamento sem `ToolMessage` correspondente no turno e verificar que o `calendar_judge_agent` consulta a agenda real, não encontra o evento, e redireciona o turno para `operational_node` executar a ação de fato antes de qualquer resposta chegar ao cliente.

**Acceptance Scenarios**:

1. **Given** uma resposta de confirmação de agendamento gerada sem `tool_calls` no turno atual, **When** o `calendar_judge_agent` consulta a integração de agendamento usando tenant_id + telefone do cliente + período alegado e **não encontra** o evento, **Then** o turno é redirecionado para `operational_node`, que executa a ação real de calendário antes de qualquer resposta ser entregue ao cliente.
2. **Given** a mesma situação, **When** o `calendar_judge_agent` consulta a integração e **encontra** o evento correspondente (tenant + telefone + período batendo), **Then** a resposta original é liberada normalmente para o cliente, sem nova chamada de tool.
3. **Given** um agendamento existente para o cliente A (mesmo tenant), **When** o cliente B confirma um agendamento diferente na mesma janela de tempo, **Then** o `calendar_judge_agent` não deve considerar o evento do cliente A como prova do agendamento do cliente B (a verificação deve ser específica ao telefone do cliente atual, não apenas ao tenant/período).

---

### User Story 2 - Verificação cobre também cancelamento e reagendamento, não só criação (Priority: P2)

Um cliente pede para cancelar ou reagendar um horário. Se a resposta do modelo afirmar que o cancelamento/reagendamento ocorreu sem lastro real de tool, o `calendar_judge_agent` deve verificar a condição correta para cada caso: ausência do evento cancelado, ou ausência do horário antigo somado à presença do novo (reagendamento é cancelar + criar).

**Why this priority**: Sem isso, a mesma classe de "ação fantasma" continua possível nesses dois fluxos, só que sem cobertura — o incidente que originou este ticket foi de criação, mas a causa raiz (heurística de texto sem verificação real) é idêntica nos três fluxos.

**Independent Test**: Forçar uma resposta de "cancelamento confirmado" sem `ToolMessage` de `cancelar_evento_google` no turno, e verificar que o `calendar_judge_agent` consulta a agenda, constata que o evento ainda existe, e redireciona para `operational_node` executar o cancelamento real antes de responder. Repetir o teste equivalente para reagendamento.

**Acceptance Scenarios**:

1. **Given** uma resposta afirmando cancelamento sem `ToolMessage` de cancelamento no turno, **When** o `calendar_judge_agent` consulta a agenda e o evento ainda está presente, **Then** o turno é redirecionado para `operational_node` para executar o cancelamento real.
2. **Given** uma resposta afirmando reagendamento sem lastro de tool, **When** o `calendar_judge_agent` verifica que o horário antigo ainda existe e/ou o novo não existe, **Then** o turno é redirecionado para `operational_node` para completar as duas etapas (cancelar o antigo, criar o novo) antes de responder.

---

### User Story 3 - Sistema não trava conversas institucionais/chitchat com a verificação (Priority: P3)

Perguntas que não têm relação com confirmação de agenda (ex.: institucional, chitchat) não devem sofrer nenhum atraso perceptível por causa do `calendar_judge_agent`.

**Why this priority**: Garante que a correção não introduz regressão de latência/custo generalizada — a verificação real contra o Google Calendar só se justifica quando há suspeita concreta de confirmação sem lastro.

**Independent Test**: Enviar uma pergunta institucional pura (ex.: "qual o endereço da clínica?") e verificar que o `calendar_judge_agent` não é acionado (nenhuma chamada extra à integração de agendamento ocorre) e a resposta segue o fluxo normal sem atraso.

**Acceptance Scenarios**:

1. **Given** uma pergunta institucional sem qualquer menção a agendamento, **When** o sistema responde, **Then** o `calendar_judge_agent` não deve ser acionado e o tempo de resposta deve permanecer no mesmo patamar de hoje.

### Edge Cases

- O que acontece se, mesmo depois do redirecionamento, a ação real de calendário também falhar (ex.: Google Calendar indisponível, horário já ocupado por outro cliente)? O cliente deve ser informado da falha real, nunca de uma confirmação — mesmo padrão de tratamento de erro já usado em `agendar_horario`/`cancelar_evento_google`.
- O que acontece se o `calendar_judge_agent` redirecionar para `operational_node` e o modelo gerar novamente uma confirmação sem lastro (loop)? Deve haver um limite de retentativas por turno (ex.: 1 redirecionamento); ao esgotar, cair no fallback seguro já existente ("Desculpa, tive um problema para verificar isso agora...").
- O que acontece se não for possível extrair um período (data/hora) estruturado do texto de confirmação, por não haver `tool_call` nem dados suficientes na mensagem? Tratar como falha de verificação (equivalente a "não encontrado") e redirecionar para `operational_node`, nunca liberar a resposta sem verificação.
- O que acontece com tenants sem agenda/calendário habilitado (`scheduling_enabled=False` ou sem `google_calendar_id`)? Nenhuma mudança de comportamento — não há integração real para consultar, então o `calendar_judge_agent` não tem o que fazer (mesmo edge case já tratado no EDI-61 para o redirecionamento institucional/chitchat).
- O que acontece se dois clientes diferentes do mesmo tenant tiverem telefones parecidos ou o telefone não estiver disponível na sessão? A verificação deve exigir telefone conhecido da sessão (`SESSION CONTACT MEMORY`); na ausência dele, tratar como falha de verificação (não liberar a confirmação sem uma chave de identificação válida).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST impedir que qualquer resposta de confirmação, consulta ou cancelamento de agenda chegue ao cliente sem que o `calendar_judge_agent` tenha verificado, consultando a integração real de agendamento, a existência (ou ausência, no caso de cancelamento) do evento correspondente.
- **FR-002**: A verificação MUST usar como chave a combinação de tenant_id (para resolver qual calendário consultar), telefone do cliente conhecido na sessão (para filtrar os eventos, via parâmetro já existente na consulta) e o período (data/hora) alegado na resposta a ser verificada. thread_id MUST NOT ser usado como chave de correlação com o Google Calendar, pois não é persistido no evento.
- **FR-003**: Quando a verificação falhar (evento não encontrado quando deveria existir; ou encontrado quando deveria ter sido cancelado), o sistema MUST redirecionar o turno para `operational_node` para executar a ação real de calendário — reaproveitando as regras de negócio já existentes ali (múltiplos agendamentos, privacidade de calendário, horário de funcionamento, `SESSION CONTACT MEMORY`) — em vez de duplicá-las em outro componente.
- **FR-004**: O sistema MUST limitar a quantidade de redirecionamentos por turno (evitar loop) e, ao esgotar o limite, MUST substituir a resposta por um pedido de repetição ao cliente (mesmo padrão de fallback já usado no guardrail existente), nunca entregar uma confirmação não verificada.
- **FR-005**: Perguntas e respostas sem relação com confirmação/consulta/cancelamento de agenda MUST continuar funcionando sem atraso perceptível — o `calendar_judge_agent` só deve ser acionado quando houver suspeita de que a resposta afirma uma ação de calendário sem `tool_calls` no turno atual.
- **FR-006**: O sistema MUST cobrir os três fluxos de calendário: criação (`agendar_horario`), cancelamento (`cancelar_evento_google`) e reagendamento (cancelar + criar), cada um com a condição de verificação apropriada.
- **FR-007**: O sistema MUST manter um registro localizável (log com tag fixa, seguindo o padrão `[CALENDAR_*]` já estabelecido no EDI-61) para toda verificação do `calendar_judge_agent`, incluindo tenant_id, thread_id, o tipo de verificação e o resultado (confirmado / não confirmado / redirecionado).
- **FR-008**: Esta funcionalidade MUST NOT introduzir nenhum novo endpoint HTTP — é lógica interna do grafo de orquestração; o contrato de `/api/v1/chat` permanece inalterado.

### Key Entities

- **Verificação de calendário (calendar_judge_agent)**: representa uma tentativa de confirmar, contra a integração real de agendamento, se uma ação (criar/cancelar/reagendar) alegada em uma resposta realmente ocorreu. Contém: tenant_id, telefone do cliente, período verificado, tipo de ação esperada, resultado (confirmado/não confirmado) e se houve redirecionamento.
- **Chave de verificação**: a combinação (tenant_id, telefone do cliente, período) usada para localizar o evento correto na agenda do tenant, distinguindo entre clientes diferentes que possam ter agendamentos no mesmo tenant/janela de tempo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero casos, em amostragem de conversas de produção após o lançamento, em que o cliente recebe uma confirmação de agendamento (criação, cancelamento ou reagendamento) sem que o evento correspondente exista de fato (ou tenha sido removido, no caso de cancelamento) no calendário real.
- **SC-002**: Toda vez que o `calendar_judge_agent` intercepta uma confirmação sem lastro, a ação de calendário correta é executada e refletida na resposta final ao cliente no mesmo turno, sem exigir uma nova mensagem do cliente (respeitado o limite de retentativas).
- **SC-003**: Conversas sem relação com agenda (institucional/chitchat/perguntas gerais) não apresentam aumento perceptível de latência após o lançamento — o `calendar_judge_agent` não é acionado fora do contexto de confirmação de agenda.
- **SC-004**: 100% das verificações do `calendar_judge_agent` (confirmadas, não confirmadas e redirecionadas) podem ser encontradas nos registros da aplicação usando um único termo de busca por tipo de resultado.

## Assumptions

- O gatilho de "suspeita de confirmação sem lastro" reaproveita/evolui a heurística já existente (`_resposta_sem_lastro_de_tool` / `BOOKING_CONFIRMATION_CLAIM_PATTERN`) como pré-filtro barato antes de pagar o custo de uma chamada real à integração de agendamento — não é reconstruída do zero.
- O telefone do cliente já está disponível na sessão via `SESSION CONTACT MEMORY` (`extract_customer_profile`/`build_customer_context_block`) no momento em que o `calendar_judge_agent` precisa verificar — não é necessário pedir esse dado novamente ao cliente.
- A extração do período (data/hora) alegado na resposta a ser verificada, quando não há `tool_call` estruturado para reaproveitar, pode ser resolvida via parsing dedicado do texto ou via um LLM call curto e barato (mesmo padrão de custo do `routing_agent`) — detalhe de implementação a decidir na fase de plano técnico.
- Não é escopo desta entrega persistir o resultado do agendamento em uma tabela própria (fonte de verdade local além do Google Calendar) — segue como melhoria estrutural separada, já registrada como assunção no EDI-61.
- O comportamento e as regras de negócio já existentes no fluxo operacional (um agendamento por vez, privacidade de calendário, horário de funcionamento, reaproveitamento de dados de contato) continuam válidos e não são duplicados no `calendar_judge_agent` — ele apenas verifica e redireciona, quem executa a ação continua sendo `operational_node`.

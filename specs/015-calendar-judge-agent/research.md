# Phase 0 Research: calendar_judge_agent

## Decisão 1 — Gatilho do juiz: reaproveitar heurística existente, não recriar do zero

**Decisão**: Manter `_resposta_sem_lastro_de_tool` (regex `BOOKING_CONFIRMATION_CLAIM_PATTERN`/`TOOL_CALL_MARKUP_LEAK_PATTERN`) como pré-filtro barato, mas **corrigir o padrão que falhou** (`agendamento\s+confirmad` → tolerar "agendamento **foi** confirmado" e variações "confirmado/reservado com sucesso"). O `calendar_judge_agent` só é acionado quando esse pré-filtro disparar.

**Alternativas consideradas**:
- Classificador LLM dedicado (tipo `routing_agent`, "esta resposta afirma ação de agenda concluída? SIM/NÃO") a cada turno sem `tool_calls`. Rejeitado **para o MVP** por custo/latência extra em todo turno de texto puro (ex.: perguntas de esclarecimento do próprio fluxo operacional, que também terminam sem tool_call). Fica registrado como evolução futura se o regex corrigido continuar apresentando furos (medir via SC-004 do spec — logs de resultado do juiz).
- Rodar o juiz sempre que não há `tool_calls` e há tools de agenda ativas. Rejeitado: penalizaria toda pergunta de esclarecimento legítima do `operational_node` ("Qual dia você prefere?") com uma consulta desnecessária ao Google Calendar.

## Decisão 2 — Extração do período (start_time/end_time) para verificação

**Decisão**: Quando a resposta suspeita não tem `tool_calls` (não há args estruturados prontos), extrair o período via um LLM call curto e determinístico (`temperature=0`, mesmo padrão de custo do `routing_agent`), reaproveitando a tabela `CALENDAR REFERENCE`/`get_tabela_dias` já injetada no prompt operacional para resolver termos relativos ("amanhã", "quinta-feira") em data absoluta. Prompt de saída estruturada (`start_time`/`end_time` ISO) via `with_structured_output` ou schema Pydantic simples — mesmo padrão já usado pelas tools (`CreateAppointmentInput`/`SearchAppointmentInput`).

**Alternativas consideradas**:
- Parser de data/hora por regex sobre o texto em português livre. Rejeitado: alta variedade de fraseado ("amanhã de manhã às 8", "dia 03/09 às 08:00", "quinta que vem"), mesma classe de fragilidade que já causou o incidente original (regex sobre linguagem natural).
- Exigir que o `operational_node` sempre inclua os args da tentativa de tool call (mesmo malformada) no state. Rejeitado: no incidente real não houve tentativa de tool call alguma — o modelo foi direto para texto, não há o que reaproveitar.

## Decisão 3 — Fonte do telefone do cliente

**Decisão**: Reaproveitar `extract_customer_profile(state["messages"])` (já usado para montar `SESSION CONTACT MEMORY`) para obter o telefone conhecido da sessão. Se ausente, tratar como falha de verificação (edge case do spec: "não liberar a confirmação sem uma chave de identificação válida").

**Alternativas consideradas**: Extrair telefone da própria resposta de confirmação (parsing). Rejeitado: o telefone normalmente não aparece na mensagem final ao cliente (por design, já que é dado sensível) — só na `description` do evento e no contexto de sessão.

## Decisão 4 — Limite de retentativas / anti-loop

**Decisão**: Adicionar um contador efêmero no `AgentState` (`judge_redirect_count`, resetado a cada nova mensagem `Human`) incrementado a cada redirecionamento do juiz para `operational_node`. Ao atingir 1, não redireciona de novo — substitui a resposta pelo fallback já existente ("Desculpa, tive um problema para verificar isso agora...") e loga `[CALENDAR_JUDGE_UNRESOLVED]`.

**Alternativas consideradas**: Limite global por thread_id (persistente entre turnos). Rejeitado: um cliente legítimo pode ter mais de um agendamento fantasma-suspeito em turnos diferentes da mesma conversa; o limite deve ser por turno, não acumulativo pela vida da thread.

## Decisão 5 — Onde o juiz se encaixa nas arestas do grafo existente

**Decisão**: O juiz substitui o destino final tanto de `operational_node` (quando termina sem `tool_calls` e o pré-filtro dispara) quanto o redirecionamento hoje feito por `_make_pre_end_guardrail_router` (usado por `institutional_node`/`chitchat_node`, EDI-61) — nos dois casos, em vez de forçar `tool_choice="required"` (operational_node) ou redirecionar cegamente (institutional/chitchat), a aresta condicional passa a chamar `calendar_judge_agent`, que decide entre liberar a resposta ou mandar para `operational_node` executar a ação real.

**Alternativas consideradas**: Manter o `tool_choice="required"` atual dentro do `operational_node` como está e adicionar o juiz só para institutional/chitchat. Rejeitado: o incidente do EDI-72 mostrou que o furo acontece **dentro do próprio operational_node** também — restringir o juiz aos outros dois nós deixaria a causa raiz real sem cobertura.

# Quickstart / Roteiro de Teste: calendar_judge_agent

Este roteiro deve ser executado pelo usuário após a implementação (ver regra do projeto: agente não sobe
container/testa o site sozinho). Assume o ambiente já em execução (`docker compose up` na stack local) e um
tenant com `scheduling_enabled=True` e `google_calendar_id` configurado (ex.: `demo-clinica`).

## Cenário 1 — Confirmação sem tool call é interceptada e corrigida (User Story 1)

1. Inicie uma conversa no canal de teste (web chat ou WhatsApp sandbox) com o tenant `demo-clinica`.
2. Conduza o fluxo normal de agendamento até o ponto de confirmação (especialidade → dia/período →
   convênio/particular → nome/telefone → horário → unidade).
3. Force o cenário de regressão (ambiente de teste/staging): monkeypatch temporário no LLM para devolver a
   string `"Seu agendamento foi confirmado com sucesso!"` sem `tool_calls` no turno de confirmação — mesma
   reprodução usada em `modules/ia/test_agent_graph.py` para este caso.
4. Verifique no log da aplicação:
   - `[CALENDAR_JUDGE] verification_result=not_confirmed` (ou tag equivalente definida na implementação),
     com `tenant_id`, `thread_id` e o período extraído.
   - Em seguida, `[TOOL: agendar_horario]` e `[CALENDAR_CREATE_OK]` — a ação real acontecendo antes da
     resposta final.
5. Confirme que a resposta que chega ao cliente só existe **depois** desses logs, nunca antes.
6. Execute esta consulta SQL (ajustando `tenant_id`) para conferir, se o feature também expuser uma tabela de
   auditoria de tentativas do juiz (caso essa parte opcional do EDI-61 seja implementada em conjunto):
   ```sql
   SELECT * FROM calendar_verification_log
   WHERE tenant_id = 'demo-clinica'
   ORDER BY created_at DESC
   LIMIT 5;
   ```
   (Se essa tabela não existir nesta entrega — ver Assumptions do spec.md, é opcional — pule este passo e
   valide só pelos logs de aplicação/Grafana Loki.)

## Cenário 2 — Confirmação real é liberada sem verificação extra desnecessária

1. Repita o fluxo de agendamento até a confirmação, desta vez **sem** o monkeypatch (fluxo real).
2. Confirme no log que `agendar_horario` foi chamado normalmente e que **não** houve acionamento do
   `calendar_judge_agent` neste turno (ele só entra quando há suspeita sem `tool_calls`) — ou, se o desenho
   final também verificar confirmações com `tool_calls`, confirme que o resultado é `confirmed` e a resposta
   não é bloqueada nem atrasada.
3. Confira o evento diretamente no Google Calendar do tenant (ou via `curl` abaixo) para o horário agendado.

## Cenário 3 — Isolamento entre clientes do mesmo tenant

1. Agende um horário para o Cliente A (telefone X) em uma conversa.
2. Em uma segunda conversa (thread diferente), force a mesma condição de confirmação sem tool call do
   Cenário 1, mas para o Cliente B (telefone Y), em um período diferente do agendamento do Cliente A.
3. Confirme que o `calendar_judge_agent` **não** aceita o evento do Cliente A como prova para o Cliente B —
   o log deve mostrar `not_confirmed` e o redirecionamento normal para `operational_node` criar o
   agendamento real do Cliente B.

## Cenário 4 — Perguntas institucionais não sofrem atraso

1. Envie uma pergunta puramente institucional (ex.: "qual o endereço da unidade central?") para o mesmo
   tenant.
2. Confirme no log que o `calendar_judge_agent` **não** é acionado (nenhuma chamada a `consultar_agenda`
   originada por ele nesse turno) e que o tempo de resposta permanece no mesmo patamar de antes da mudança.

## Verificação via API (opcional, complementar aos logs)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: demo-clinica" \
  -d '{"thread_id": "teste-judge-001", "message": "sim, pode confirmar"}'
```

Use este `curl` apenas para reproduzir turnos específicos durante o teste manual — não substitui a
verificação dos logs, que é a evidência real de que a ação de calendário ocorreu antes da resposta.

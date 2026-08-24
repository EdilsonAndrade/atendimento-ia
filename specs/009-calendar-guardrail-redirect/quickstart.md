# Quickstart: Validando a correção do EDI-61 localmente

## Pré-requisitos

- Ambiente já configurado conforme `CLAUDE.md` (ver `specs/006-tenant-delete-cascade/plan.md` para stack/shell commands do projeto).
- Container `chatatendimento-api` rodando localmente com um tenant que tenha `scheduling_enabled=True` e `google_calendar_id` configurado (mesmo tenant "1234"/`interasisai` usado no incidente original é suficiente).

## Cenário 1 — Redirecionamento funciona (guardrail em institutional_node/chitchat_node)

1. Inicie uma conversa nova (thread_id novo) com o tenant de teste.
2. Envie uma mensagem que historicamente foi mal classificada como INSTITUTIONAL/CHITCHAT mas é parte de um fluxo de confirmação (ex.: responder só com um e-mail, ou "pode ser às 9" isolado, sem contexto operacional explícito na própria mensagem).
3. **Antes da correção**: resposta podia confirmar/relatar agenda em texto sem nenhuma linha `[CALENDAR_*]` no log.
4. **Depois da correção**: verificar no log da aplicação que, se a resposta gerada bateu no padrão de confirmação sem tool, aparece uma linha `[CALENDAR_GUARDRAIL_REDIRECT]` seguida de uma chamada real de tool (`[CALENDAR_QUERY]`, `[CALENDAR_CREATE_OK]` etc.) no mesmo turno, e a resposta final ao cliente só reflete o resultado real dessa chamada.

## Cenário 2 — Caminho feliz não regride

1. Envie uma pergunta puramente institucional (ex.: "qual o site da empresa?") e uma mensagem de chitchat pura (ex.: "obrigado, até mais").
2. Confirmar que ambas continuam respondendo normalmente, sem nenhuma linha `[CALENDAR_GUARDRAIL_REDIRECT]` no log e sem latência perceptível adicional (uma única invocação de LLM, como hoje).

## Cenário 3 — Logs de tools de calendário localizáveis

1. Execute um fluxo completo de agendamento pelo `operational_node` (consulta → criação) e depois um cancelamento.
2. No log da aplicação, rodar:
   ```bash
   grep -E "\[CALENDAR_(CREATE|QUERY|CANCEL)_" <arquivo_de_log_ou_docker_logs>
   ```
3. Confirmar que cada operação (consulta, criação, cancelamento) aparece com sua tag correspondente, tenant_id, e (quando aplicável) event_id — sem precisar ler o texto da conversa para entender o que aconteceu.

## Cenário 4 — Resumo de sessão não alucina resultado

1. Simular (ou aguardar naturalmente) a expiração de uma sessão em que o cliente recebeu uma resposta de confirmação de agenda **sem** nenhuma `ToolMessage` de sucesso correspondente no histórico (idealmente, isso não deve mais ocorrer após o Cenário 1 estar corrigido — mas o teste unitário de `_summarize_session` deve cobrir esse caso mesmo assim, como defesa em profundidade).
2. Verificar que o resumo gerado (`PREVIOUS SESSION SUMMARY` injetado na próxima conversa do mesmo cliente) não declara "Resultado anterior: Agendamento confirmado" nesse caso.

## Testes automatizados

```bash
pytest modules/ia/test_agent_graph.py -v
pytest modules/ia/test_ia_assistante_rag.py -v
pytest modules/agendamento/test_agente_atendimento.py -v
```

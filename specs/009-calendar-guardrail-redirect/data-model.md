# Phase 1 Data Model: Impedir confirmação de agendamento sem ação real no calendário

Esta feature não introduz nenhuma tabela, migration ou schema Pydantic novo — persistência local do agendamento foi explicitamente marcada como fora de escopo (ver spec.md > Assumptions). As "entidades" abaixo são conceituais, existindo apenas como estruturas de dados em memória (mensagens do LangGraph) e como formato de log — documentadas aqui porque o spec as define como Key Entities.

## Registro de ação de calendário (log, não persistido)

Representa uma chamada real a uma tool de calendário. Materializado como uma linha de log `print`, não como um registro de banco.

| Campo | Origem | Observação |
|---|---|---|
| tag | fixa por operação/resultado | `[CALENDAR_CREATE_OK]`, `[CALENDAR_CREATE_FAIL]`, `[CALENDAR_QUERY]`, `[CALENDAR_CANCEL_OK]`, `[CALENDAR_CANCEL_FAIL]` |
| tenant_id | parâmetro já injetado nas tools (`build_agendar_tool`, `build_consulta_tool`, etc.) | já disponível hoje, só precisa entrar na linha padronizada |
| google_calendar_id | já resolvido dentro de cada tool via `tenant_service.get_tenant_by_id` | já disponível hoje |
| event_id | retorno de `calendar_service.create_event`/`list_events` (quando aplicável) | ausente em falhas antes da criação, ou em consultas sem resultado |
| período/horário | `start_time`/`end_time` já recebidos pela tool | já disponível hoje |
| resultado | sucesso/erro, incluindo mensagem de erro quando aplicável | novo — hoje o resultado só aparece implícito no texto do print |

## Registro de interceptação de confirmação sem ação (log, não persistido)

Representa o momento em que `institutional_node`/`chitchat_node` gerou uma resposta com padrão de confirmação/consulta de agenda sem `tool_calls` reais, e o grafo redirecionou o turno para `operational_node`.

| Campo | Origem | Observação |
|---|---|---|
| tag | fixa | `[CALENDAR_GUARDRAIL_REDIRECT]` |
| tenant_id | `config["configurable"]["tenant_id"]`, já disponível em todos os nós | — |
| nó de origem | conhecido estaticamente (`institutional_node` ou `chitchat_node`) no ponto de emissão do log | — |
| thread_id | `config["configurable"]["thread_id"]` (padrão já usado no LangGraph deste projeto) | confirmar nome exato da chave em uso no `chat.py`/`agent_graph.py` durante a implementação |
| trecho interceptado | `resposta_ia.content` (truncado, mesmo padrão de `repr()` já usado nos prints de guardrail existentes) | evitar logar PII desnecessária além do já presente na resposta do próprio modelo |

## Resumo de sessão (já existente — campo `resultado` passa a exigir evidência)

Estrutura já produzida por `_summarize_session` (`modules/ia/thread_session.py`), sem mudança de schema — apenas a regra de preenchimento do campo `resultado` muda.

| Campo | Tipo | Regra nova |
|---|---|---|
| resumo | string curta | sem mudança |
| nome | string ou null | sem mudança |
| interesse | string ou null | sem mudança |
| objecao | string ou null | sem mudança |
| resultado | string ou null | só pode declarar um agendamento como confirmado/cancelado se houver uma `ToolMessage` de sucesso correspondente no histórico da sessão resumida; caso contrário, `null` ou uma descrição neutra, nunca uma confirmação não evidenciada |

## Sem mudança de estado no `AgentState`

`AgentState` (`modules/ia/agent_graph.py`) não ganha nenhum campo novo — o sinal de "confirmação sem lastro detectada" usado para decidir a aresta condicional é derivado no momento da checagem (chamando `_resposta_sem_lastro_de_tool` sobre a última `AIMessage` gerada), não precisa ser persistido no estado entre nós.

# Phase 0 Research: Impedir confirmação de agendamento sem ação real no calendário

Nenhum item do Technical Context ficou marcado como `NEEDS CLARIFICATION` — o código já existente no repositório resolve todas as decisões técnicas por precedente direto. Este documento registra as decisões e as alternativas descartadas.

## 1. Como interceptar e redirecionar `institutional_node`/`chitchat_node`

**Decision**: Reaproveitar a função de detecção já existente `_resposta_sem_lastro_de_tool` (`modules/ia/agent_graph.py:141`) — que já usa `BOOKING_CONFIRMATION_CLAIM_PATTERN` e `TOOL_CALL_MARKUP_LEAK_PATTERN` — chamando-a também logo após `llm.invoke(...)` dentro de `institutional_node` e `chitchat_node`. Se o guardrail disparar, em vez de retornar a `AIMessage` para `END`, o nó retorna um sinal (ex.: adicionar um `AIMessage` de controle equivalente ao `"Routing decision: ..."` já usado pelo `routing_agent`, ou reaproveitar `state["messages"]` com uma marca) que uma função de roteamento condicional lê para decidir entre `END` e `operational_node`. Trocar `builder.add_edge("institutional_node", END)` e `builder.add_edge("chitchat_node", END)` por `builder.add_conditional_edges(node, <função>, {"redirect": "operational_node", "end": END})`.

**Rationale**: É o mesmo mecanismo (`add_conditional_edges`) já usado pelo grafo para o roteamento inicial (`routing_agent` → `institutional_node`/`operational_node`/`chitchat_node`) e para `tools_condition` (`operational_node` → `tools`/`END`). Não introduz um conceito novo no grafo, apenas estende um padrão já revisado e testado. Reaproveitar `_resposta_sem_lastro_de_tool` evita duplicar a lógica de detecção de "confirmação sem lastro" em três lugares.

**Alternatives considered**:
- *Vincular as tools de calendário diretamente a `institutional_node`/`chitchat_node`* — rejeitado: duplicaria as regras de negócio (múltiplos agendamentos, privacidade, horário de funcionamento, `SESSION CONTACT MEMORY`, retry com `tool_choice="required"`) que hoje só existem no `operational_node`, criando dois lugares para manter a mesma regra.
- *Criar um nó guardrail intermediário único que todos os nós passam antes de `END`* — rejeitado como escopo desta feature por ser uma refatoração maior do grafo (mudaria a topologia de todos os nós, não só dos dois afetados); pode ser considerado numa iteração futura, mas não é necessário para resolver o EDI-61.

## 2. Onde a `operational_node` retoma o processamento após o redirecionamento

**Decision**: `operational_node` já é reentrante por design — ele sempre relê `state["messages"]` (incluindo o filtro de `"Routing decision:"` já existente) e busca a última mensagem `human` para RAG/contexto. Nenhuma mudança estrutural é necessária em `operational_node`: o redirecionamento simplesmente adiciona uma aresta de entrada nova (vinda de `institutional_node`/`chitchat_node`) para um nó que já sabe processar o estado corrente do zero a cada invocação.

**Rationale**: Evita qualquer nova lógica de "retomada parcial" — o grafo LangGraph já trata cada nó como uma função pura sobre o `state` acumulado; reentrar em `operational_node` com o histórico atualizado (incluindo a resposta interceptada do nó anterior, se for mantida no estado) é exatamente o comportamento que os edges condicionais existentes (`tools` → `operational_node`) já exercitam.

**Alternatives considered**: Criar uma cópia simplificada da lógica de agendamento dentro de `institutional_node`/`chitchat_node` — descartado pelo mesmo motivo do item 1 (duplicação de regras de negócio).

## 3. Prompt do `routing_agent`: alinhar `CONTINUATION` à instrução de saída

**Decision**: Adicionar `'CONTINUATION'` à lista de saídas válidas na instrução final do prompt (`"Reply with EXACTLY ONE word: ..."`), e imediatamente após a classificação, se a saída for `CONTINUATION`, substituir programaticamente pela `intencao_anterior` (já computada em `_intencao_anterior_nao_chitchat`) antes de decidir a aresta condicional — o comportamento pretendido pela regra 4 do prompt já existe na função Python, só falta a saída do LLM conseguir expressá-lo.

**Rationale**: Mínima mudança possível que resolve a contradição sem alterar a lógica de negócio já implementada (`intencao_anterior` já é calculada e já está disponível no prompt como `PREVIOUS TURN INTENT`).

**Alternatives considered**: Remover a classe `CONTINUATION` do prompt e confiar inteiramente no `PREVIOUS TURN INTENT` como contexto — rejeitado porque isso é exatamente o comportamento atual (contraditório) que já demonstrou aumentar erro de classificação nas mensagens curtas de continuação observadas no incidente.

## 4. Blindagem do resumidor de sessão (`_summarize_session`)

**Decision**: Alterar o filtro de mensagens em `_summarize_session` (`modules/ia/thread_session.py`) para não descartar `ToolMessage`, e ajustar o prompt do resumidor para instruir explicitamente: só declarar `resultado` como "agendamento confirmado" (ou similar) se houver evidência de uma `ToolMessage` de sucesso de uma tool de calendário no histórico correspondente; caso contrário, usar `null` ou uma descrição neutra ("cliente demonstrou interesse, sem confirmação registrada").

**Rationale**: Resolve a causa raiz #3 do ticket (resumidor não distingue confirmação real de alucinada) sem exigir uma nova tabela ou pipeline — é um ajuste local na função já existente, reaproveitando dados (`ToolMessage`) que já estão no checkpoint do LangGraph.

**Alternatives considered**: Persistir o resultado real do agendamento numa tabela própria e usar essa tabela como fonte de verdade do resumidor — é a melhoria estrutural registrada como fora de escopo no ticket EDI-61 e no spec (Assumptions); mais robusta a longo prazo, mas desproporcional para esta correção pontual.

## 5. Padronização de tags de log

**Decision**: Usar tags de texto fixas entre colchetes, no mesmo estilo já usado no código (`" -> [TOOL: agendar_horario] ..."`, `" -> 🛡️ [GUARDRAIL] ..."`), adicionando uma tag adicional dedicada por evento em cada `print`: `[CALENDAR_CREATE_OK]` / `[CALENDAR_CREATE_FAIL]` em `agenda_tool.py`, `[CALENDAR_QUERY]` em `consulta_agenda_tool.py`, `[CALENDAR_CANCEL_OK]` / `[CALENDAR_CANCEL_FAIL]` em `delete_agenda_tool.py`, e `[CALENDAR_GUARDRAIL_REDIRECT]` no ponto de interceptação do item 1.

**Rationale**: O projeto não usa um sistema de logging estruturado (JSON) hoje — todo o `agent_graph.py` e as tools de calendário usam `print(...)` com prefixos textuais legíveis, capturados pelo `docker logs`/stdout (visível no incidente original). Introduzir `logging` estruturado ou um novo pipeline de observabilidade é desproporcional ao escopo deste bug fix; tags fixas e `grep`-áveis resolvem o requisito do usuário ("localizar com um grep simples") com o menor risco e sem mudar a infraestrutura de logging do projeto.

**Alternatives considered**: Adotar `logging` com `extra={}` estruturado ou JSON logs — descartado nesta feature por ser uma mudança de infraestrutura transversal a todo o projeto (todos os outros módulos usam `print`), fora do escopo do EDI-61; pode ser proposto como feature própria no futuro.

## 6. Estratégia de testes

**Decision**: Seguir o padrão já existente em `modules/ia/test_agent_graph.py` (que já testa `_resposta_sem_lastro_de_tool` isoladamente, sem subir o grafo completo) para os novos casos: (a) detecção de confirmação sem tool em contexto de `institutional_node`/`chitchat_node`, (b) função de roteamento condicional decidindo `operational_node` vs `END`, (c) `_summarize_session` não declarando resultado confirmado sem `ToolMessage`. Para as tools de calendário, seguir `modules/agendamento/test_agente_atendimento.py`, adicionando asserções sobre o conteúdo/tag do log emitido (via `capsys`/`caplog` do pytest) para cada cenário de sucesso/falha.

**Rationale**: Reaproveita fixtures, mocks de `calendar_service`/`tenant_service` e estilo de teste já estabelecidos nesses arquivos — consistente com Principle VI da constituição sem exigir infraestrutura de teste nova.

**Alternatives considered**: Subir o `StateGraph` completo compilado em teste de integração ponta a ponta — considerado como teste complementar de alto valor (cobre a topologia real do grafo), mas não substitui os testes unitários direcionados; ambos serão detalhados na Fase 2 (tasks).

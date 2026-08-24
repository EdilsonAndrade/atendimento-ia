# Research: Rastreamento de custo de token por conversa e tenant

## 1. Como capturar o uso de token "nativamente" (sem estimativa manual)

**Decisão**: usar o atributo `usage_metadata` que o `langchain_openai.ChatOpenAI` já popula em toda `AIMessage` de resposta (`response.usage_metadata = {"input_tokens": int, "output_tokens": int, "total_tokens": int}`), quando o provedor devolve informação de uso — a API da DeepSeek (compatível com OpenAI) devolve isso normalmente. Nenhuma chamada extra, nenhuma biblioteca de contagem de tokens (`tiktoken` e afins) é necessária.

**Por que**: é exatamente o mecanismo "correto do LangGraph/LangChain" pedido no ticket — dado real devolvido pelo provedor, não estimativa local (que diverge de tokenizador para tokenizador).

**Risco conhecido**: `usage_metadata` pode vir ausente/incompleto em alguma resposta (edge case da spec). O ponto de captura trata isso sem lançar exceção — ver §3.

## 2. Onde plugar a captura, dado que há 4 pontos de chamada ao LLM

**Decisão**: um único helper `record_llm_usage(response, tenant_id, base_thread_id, thread_id, node_type)` em `modules/ia/agent_graph.py`, chamado logo após cada um dos `.invoke()` existentes: `routing_agent` (linha ~378), `institutional_node` (~471), `operational_node` (~564 e ~579, a chamada de retry com `tool_choice="required"`), `chitchat_node` (~673). O helper delega para o caso de uso da Application layer do novo módulo `modules/token_usage/`.

**Alternativas rejeitadas**:
- Um `Callback Handler` global do LangChain (`BaseCallbackHandler.on_llm_end`) registrado uma vez no `builder.compile(...)`: capturaria todas as chamadas automaticamente sem tocar em cada nó, mas o callback não tem acesso direto e confiável ao `node_type`/`tenant_id`/`base_thread_id` de forma simples (dependeria de propagar isso via `RunnableConfig.metadata`, uma refatoração maior em todos os nós). Chamada explícita por nó é mais direta e não exige mudar a assinatura de nada existente.

**Por que**: é a menor mudança que cobre 100% dos pontos de chamada hoje (SC-001), com acesso direto a `tenant_id`/`base_thread_id`/`node_type` que cada nó já tem em escopo.

## 3. Falha ao registrar custo não pode afetar a resposta ao cliente (FR-006)

**Decisão**: `record_llm_usage` (e o caso de uso/repositório por trás dele) captura qualquer exceção internamente e apenas loga — nunca propaga. Mesmo padrão já usado em `util/tool_error_handling.py` (EDI-59): falha de infraestrutura secundária não pode derrubar o caminho principal da conversa.

## 4. Estrutura do módulo novo (Clean Architecture, Princípio III)

**Decisão**: `modules/token_usage/` com Domain (entidade `TokenUsageRecord` + função pura de cálculo de custo), Application (`RecordTokenUsageUseCase`, dependendo de um `Protocol TokenUsageRepository`), Infrastructure (`PostgresTokenUsageRepository` implementando o Protocol). `modules/ia/agent_graph.py` (módulo legado) só importa e chama o caso de uso da Application layer — nunca a Infrastructure diretamente — consistente com a política de módulos legados dependerem de interfaces públicas de outros módulos, e com a exigência da constituição de que módulos NOVOS sigam Clean Architecture desde o primeiro commit.

**Por que não reaproveitar o padrão "SQL direto" do EDI-59**: o EDI-59 alterou apenas módulos legados já existentes (`ia`, `agendamento`), grandfathered pela Legacy Migration Policy. O EDI-60 cria um módulo inteiramente novo — a constituição é explícita: "Net-new modules and features ... MUST comply with Principles III and VI from their first commit; there is no grace period for new code."

## 5. Preço por token

**Decisão**: duas variáveis de ambiente, `LLM_PRICE_PER_1K_INPUT_TOKENS_USD` e `LLM_PRICE_PER_1K_OUTPUT_TOKENS_USD`, com um default conservador documentado no `.env.example`/README como PLACEHOLDER a ser ajustado pelo usuário conforme o plano contratado com a DeepSeek — este projeto não tem acesso à tabela de preços vigente do provedor nem tenta mantê-la sincronizada automaticamente.

**Por que**: preço por token muda por provedor/plano/momento; hardcodar um valor "chutado" seria pior que deixá-lo explicitamente configurável e documentado como responsabilidade do operador do sistema.

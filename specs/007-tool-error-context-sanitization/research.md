# Research: Sanitização do contexto de conversa enviado ao LLM

## 1. Como sanitizar o erro nas tools sem duplicar try/except em cada arquivo

**Decisão**: um decorator único `@safe_tool_result` em `util/tool_error_handling.py`, aplicado por cima de `@tool` em cada função (`@tool(...) \n @safe_tool_result(fallback="...") \n def minha_tool(...): ...`). O decorator:
1. Executa a função original dentro de um `try/except Exception`.
2. Em caso de exceção, chama `logging.getLogger(__name__).error(...)` com a mensagem original, o tipo da exceção e (quando presentes nos kwargs da chamada) `tenant_id`/identificador de thread.
3. Devolve a string de `fallback` passada na decoração (uma por tool, curta e específica ao contexto daquela tool) em vez de propagar a exceção.

**Alternativas rejeitadas**:
- Editar cada `except Exception` manualmente em cada um dos 7 arquivos: mais rápido a curto prazo, mas reintroduz o mesmo bug no futuro assim que alguém adicionar uma tool nova sem lembrar da regra.
- Um middleware/interceptor no nível do LangGraph (`ToolNode` customizado): mais invasivo, exigiria substituir o `ToolNode` padrão do LangGraph já usado no grafo; desproporcional ao problema.

**Por que**: um decorator é a menor mudança que garante que toda tool nova daqui pra frente também fica protegida por padrão, sem exigir que quem escrever a tool lembre da regra.

## 2. Geração do resumo/fatos estruturados (US4) sem bloquear a resposta ao cliente

**Decisão**: `resolve_active_thread_id` (`modules/ia/thread_session.py`) tem HOJE dois call sites em camadas de transporte diferentes — `app/api/v1/endpoints/chat.py` (chat web, request HTTP síncrono/async) e `modules/webhook/whatsapp.py` (webhook do WhatsApp). Threading `FastAPI BackgroundTasks` pelos dois exigiria mudar a assinatura de `resolve_active_thread_id` (para devolver o `active_thread_id` expirado) E adaptar os dois pontos de chamada para aceitar/propagar um `BackgroundTasks`. Em vez disso, a própria `resolve_active_thread_id` dispara uma `threading.Thread(daemon=True)` executando `generate_and_store_session_summary(base_thread_id, expired_active_thread_id)` assim que detecta a expiração, ANTES de retornar — os dois call sites continuam recebendo só a string do `active_thread_id`, sem nenhuma mudança de assinatura ou de import.

**Alternativas rejeitadas**:
- `FastAPI BackgroundTasks`: exigiria duplicar a integração em `chat.py` e `whatsapp.py` (dois frameworks/pontos de entrada), além de mudar o retorno de `resolve_active_thread_id` — desproporcional ao ganho frente a uma thread daemon simples.
- Gerar o resumo de forma síncrona antes de responder: viola o Princípio V da constituição (trabalho de LLM não pode bloquear o ciclo request/response) e adicionaria latência perceptível à primeira mensagem de uma nova sessão.
- Um job/cron separado varrendo sessões expiradas periodicamente: mais robusto a longo prazo (sobrevive a reinício do processo antes da thread rodar), mas é infraestrutura nova (scheduler) desproporcional ao escopo deste ticket; fica como possível evolução futura, não bloqueia esta entrega.

**Por que**: uma thread daemon disparada dentro da própria `thread_session.py` é "um job assíncrono equivalente" ao `BackgroundTasks` (linguagem explícita do Princípio V da constituição), sem exigir que os dois pontos de entrada (chat web e webhook do WhatsApp) sejam adaptados individualmente — a resolução da sessão continua devolvendo só a `str` do `active_thread_id`, 100% compatível com o uso atual.

## 3. Onde persistir resumo/fatos estruturados

**Decisão**: nova tabela `chat_thread_summaries` (uma migration em `migrations/versions/`), com uma função de acesso dedicada em `modules/ia/thread_session.py` (mesmo arquivo que já concentra o SQL de sessão via psycopg direto, seguindo a convenção já estabelecida ali — não existe repositório formal para o módulo `ia`).

**Por que**: `thread_session.py` já é o único lugar do módulo `ia` que fala diretamente com o Postgres para controle de sessão; manter o SQL de resumo no mesmo arquivo evita espalhar acesso a banco por múltiplos arquivos do módulo, consistente com a Legacy Migration Policy (item 2: não abrir novo canal de acesso a banco fora do já existente no módulo).

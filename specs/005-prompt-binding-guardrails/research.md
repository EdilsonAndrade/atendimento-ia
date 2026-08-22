# Phase 0 — Research: Vínculo explícito de prompt e guardrails globais

**Feature**: 005-prompt-binding-guardrails · **Plan**: [plan.md](./plan.md)

Nenhum `NEEDS CLARIFICATION` pendente. As três ambiguidades de escopo (quais nós exigem vínculo, o que o cadastro exige, como migrar) foram resolvidas com o solicitante antes do specify e estão registradas em Assumptions da spec e no comentário de refinamento do EDI-43.

---

## R1 — Distinguir "erro de configuração" de "banco indisponível"

**Decisão**: introduzir `PromptConfigurationError` (exceção de domínio) em `prompts/prompt_resolver.py`, capturada e tratada separadamente do `except Exception` genérico que hoje faz o fallback local.

**Rationale**: esta é a causa-raiz do defeito, e é o ponto onde a feature inteira se apoia. Hoje `carregar_operacional_prompt` (`load_prompt.py:143-189`) envolve tudo num único `try/except Exception` cujo `except` faz `_carregar_fallback_local(...)`. Se qualquer coisa der errado — banco fora do ar, mas também tenant sem vínculo, ou um erro de programação — o resultado é o mesmo: conteúdo genérico entregue silenciosamente.

Os dois casos exigem comportamentos **opostos** (FR-004 diz falhar e alertar; FR-007 diz continuar atendendo), então precisam ser tipos distintos. A ordem dos `except` importa: `PromptConfigurationError` primeiro, `Exception` depois. Se a ordem inverter, o bug volta silenciosamente — vale um teste dedicado.

**Alternatives considered**:
- *Sentinela de retorno (`None` / tupla `(conteudo, origem)`)*: obriga cada um dos quatro chamadores a lembrar de checar, e um esquecimento reintroduz o fail-open sem fazer barulho. Exceção falha alto por construção.
- *Flag booleana no retorno*: mesmo problema, com o agravante de o tipo de retorno virar heterogêneo.

---

## R2 — Onde centralizar a resolução

**Decisão**: novo módulo `prompts/prompt_resolver.py` com uma função de resolução parametrizada por `node_type` e por política de exigência de vínculo. `load_prompt.py` mantém as quatro funções públicas atuais, que passam a delegar, e **preserva** `_render_prompt`, `_montar_guardrails_str` e `_aplicar_guardrails`.

**Rationale**: os três helpers existentes carregam correções de bugs reais de produção, documentadas nos próprios docstrings — substituição em passada única (evita cascata quando um guardrail contém `{guardrails}`), dedupe por texto normalizado (FR-009), e anexação ao final quando o template não tem o placeholder (FR-010). Reescrevê-los seria reintroduzir três defeitos já resolvidos. A separação fica: **resolver** decide *o quê* (política, banco, erro); **load_prompt** decide *como renderizar* (helpers) e expõe a assinatura que os nós do agente já chamam.

Manter as assinaturas públicas também significa que nenhum chamador em `modules/ia/` precisa mudar.

**Alternatives considered**:
- *Refatorar tudo dentro de `load_prompt.py`*: o arquivo já tem ~265 linhas misturando política e renderização; a política nova (erro vs. contingência, globais em todo caminho) tornaria a leitura pior justamente no ponto mais sensível.
- *Uma classe `PromptResolver` com estado*: sem estado a manter entre chamadas; funções puras recebendo o service são mais simples de testar com fakes (Princípio VI).

---

## R3 — Guardrails globais no caminho de erro

**Decisão**: a resolução de guardrails é sempre executada e **independente** do sucesso da resolução do prompt. Quando não há prompt vinculado, usa `get_global_guardrails()`; quando há, usa `get_guardrails_by_prompt(prompt_id)`, que já inclui os globais via `WHERE g.is_global = TRUE OR pg.prompt_id = %s` (`prompt_manager_repository.py:142`).

**Rationale**: FR-005 é explícito — segurança não pode falhar junto com o prompt. Na prática isso significa resolver os guardrails **antes** de levantar `PromptConfigurationError`, e anexar o resultado à exceção, para que o tratador tenha a política de segurança disponível mesmo no caminho de falha.

Um detalhe que economiza uma query: `get_guardrails_by_prompt` já cobre "vinculados + globais" numa chamada só, então o caminho com vínculo continua com as mesmas 2 queries de hoje. O caminho sem vínculo também: 1 (prompt ativo, retorna vazio) + 1 (globais).

**Alternatives considered**:
- *Levantar o erro antes de resolver guardrails*: mais simples, mas viola FR-005 diretamente.
- *Chamar `get_global_guardrails()` sempre e unir em Python com os do prompt*: query redundante e reimplementa em Python o `OR is_global` que o SQL já faz — com risco de divergir dele.

---

## R4 — Corrigir a divergência do `/overview`

**Decisão**: alterar a query de guardrails de `get_tenant_prompt_details` (`prompt_manager_repository.py:315-320`) para incluir os globais, alinhando-a a `get_guardrails_by_prompt`.

**Rationale**: descoberta durante o levantamento e **não prevista na descrição do EDI-43**. A query atual faz `JOIN prompt_guardrails` puro, sem `OR g.is_global = TRUE`. O ticket afirmava que a divergência entre tela e runtime existia só para tenant sem vínculo; na verdade ela existe **também para tenant com vínculo** — a tela mostra menos guardrails do que o agente aplica.

Sem esta correção, FR-003 e SC-002 ("zero divergência") não são atingíveis, mesmo com todo o resto implementado.

**Alternatives considered**:
- *Fazer `get_tenant_prompt_details` reusar `get_guardrails_by_prompt`*: preferível em princípio (uma fonte de verdade), mas `get_tenant_prompt_details` faz as duas queries numa conexão só. Decisão para a implementação: reusar se couber sem abrir conexão extra; senão, replicar a cláusula com um comentário apontando para a outra. Reusar é o caminho preferido — duas queries com a mesma regra é exatamente como o bug nasceu.

---

## R5 — Ampliar o seed sem sobrescrever o admin

**Decisão**: `seed_missing_node_prompts` passa a receber o conteúdo dos quatro `.md` e a garantir (a) um prompt por `node_type` e (b) um guardrail `is_global=TRUE`, mantendo o padrão "cria só se não existir". `app/main.py` deixa de ter conteúdo hardcoded e passa a só ler os arquivos.

**Rationale**: a infra idempotente já existe e funciona (`prompt_manager_repository.py:213`); o trabalho é ampliar o alcance, não redesenhar. O critério de existência segue o já usado: `SELECT ... LIMIT 1` por `node_type` antes de inserir. Para o guardrail, o critério é a existência de qualquer `is_global = TRUE` — não o título, que o admin pode ter renomeado.

Dois pontos que precisam sobreviver à mudança:
1. O conteúdo é gravado **cru**, com `{guardrails}` intacto (FR-014). O comentário em `app/main.py:130-137` explica por quê: se o `.format()` for aplicado no seed, o texto congela e os guardrails deixam de ser injetados por atendimento.
2. A cópia operational→institutional que o seed já faz (`:240-286`) é comportamento do EDI-42 e continua valendo; a ampliação não pode quebrá-la.

**Alternatives considered**:
- *`ON CONFLICT DO NOTHING` por título*: o admin pode renomear o registro semeado, e aí o seed criaria um duplicado a cada boot.
- *Upsert do conteúdo*: viola FR-013 diretamente — sobrescreveria a edição do admin no próximo restart.
- *Seed via migration Alembic*: migration é para estrutura e backfill pontual; o seed precisa rodar em toda inicialização para cobrir instalação nova. São mecanismos distintos, mantidos distintos.

---

## R6 — Atomicidade de tenant + vínculo

**Decisão**: validar o prompt **antes** de qualquer escrita (existe? é `operational`?) e executar os dois `INSERT` — `tenants` e `tenant_prompts` — numa **única transação, na mesma conexão**, com um único `commit()`.

**Rationale**: FR-018 exige atomicidade porque tenant sem vínculo é precisamente o estado que a feature elimina. O obstáculo é de estilo, não de banco: `TenantRepository.__init__` (`tenant_repository.py:5`) guarda uma conexão viva com `commit()` explícito, enquanto `PromptManagerRepository` recebe a factory e usa `with self.get_connection()`. Como ambos apontam para o mesmo Postgres, basta que os dois `INSERT` compartilhem uma conexão e um commit.

Ordem de execução, que também melhora as mensagens de erro:
1. Validar o prompt (`404 PROMPT_NOT_FOUND` / `400 PROMPT_NODE_TYPE_INVALID`) — nenhuma escrita ocorreu ainda, então os erros comuns nunca deixam resíduo.
2. `INSERT INTO tenants` + `INSERT INTO tenant_prompts` na mesma transação.
3. Um `commit()`; qualquer exceção no meio → `rollback()`.

A escrita em `tenant_prompts` a partir de `TenantRepository` cruza a fronteira conceitual do módulo. A Legacy Migration Policy permite (é o repositório existente, não SQL novo em endpoint), mas o método deve documentar por que a transação precisa ser compartilhada — senão o próximo leitor "corrige" separando os dois e reabre a janela.

**Alternatives considered**:
- *Criar tenant, depois vincular, com `DELETE` compensatório na falha*: existe uma janela real em que o estado proibido está no banco, e a própria compensação pode falhar. Rejeitado por contrariar o objetivo da feature.
- *Vínculo assíncrono pós-criação*: piora — a janela vira indeterminada.

---

## R7 — Backfill e ativação no mesmo deploy

**Decisão**: uma revision Alembic nova (`0002_backfill_tenant_prompt_links`) associa todo tenant sem vínculo `operational` ativo ao prompt `is_default = TRUE` de `node_type = 'operational'`. Sem feature flag: a migration roda no startup do container, antes de a API atender.

**Rationale**: o `docker-entrypoint.sh` já aplica as migrations na subida (commit `e14941b`), então o backfill precede o primeiro atendimento no mesmo deploy — que é exatamente o que FR-029 pede. A ordem é a garantia; não é preciso coordenar duas implantações.

Dois casos de borda que a migration precisa tratar explicitamente:
- **Não existe prompt `is_default` operational** (banco novo, ou o admin desmarcou): não há a que vincular. A migration deve ser tolerante e não falhar o deploy — o seed do startup cria o prompt semente, e o admin vincula pela tela. Falhar aqui derrubaria a subida do container por um estado legítimo de instalação nova.
- **Múltiplos prompts `is_default`**: `get_default_prompt` já usa `LIMIT 1` sem `ORDER BY`. A migration deve escolher deterministicamente (por `created_at`) para que rodar de novo não produza resultado diferente.

O `downgrade` remove apenas os vínculos que a própria migration criou — não os vínculos que já existiam.

**Alternatives considered**:
- *Feature flag por env var, backfill manual, flag depois*: mais passos e mais chance de erro humano, e o solicitante escolheu explicitamente o caminho de deploy único.
- *Script manual fora do Alembic*: perde rastreabilidade e a garantia de ordenação em relação à subida da API.

---

## R8 — Formato do erro estruturado

**Decisão**: `HTTPException(status_code=..., detail={"code": str, "message": str, "blockers": list})`, com os `code` tipados como `Literal` num schema Pydantic para documentar no OpenAPI. O `422` do Pydantic mantém o formato de lista nativo.

**Rationale**: FR-027 exige código estável legível por máquina. Passar um `dict` como `detail` é suportado pelo FastAPI e serializa direto, sem exception handler customizado — mantém a mudança contida nos endpoints, sem tocar na montagem do app.

O `blockers` carrega os itens que impedem a ação (tenants ou prompts), o que permite à UI listar o caminho de saída em vez de só exibir "não é possível". Esse detalhe é o que diferencia um bloqueio útil de um bloqueio frustrante.

A assimetria do `422` é intencional e está documentada no contrato do EDI-44: validação de schema é responsabilidade do Pydantic e não deve ser reembrulhada só por simetria estética — o front trata os dois formatos.

**Alternatives considered**:
- *Exception handler global convertendo tudo para o envelope*: uniformizaria o `422` também, mas alteraria o formato de erro de **todos** os endpoints do projeto — mudança de contrato bem além do escopo desta feature, quebrando consumidores existentes.
- *`detail` como string com prefixo parseável (`"PROMPT_IN_USE: ..."`)*: obriga o front a parsear texto, que é exatamente o que FR-027 proíbe.

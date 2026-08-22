# Research: Exclusão segura de tenant com cascata de prompts e guardrails

## 1. Escopo da avaliação de "exclusividade": vínculos ativos apenas

**Decision**: Um prompt ou guardrail só é considerado "exclusivo do tenant sendo excluído" com base nos vínculos **ativos** (`tenant_prompts.is_active = TRUE`). Vínculos inativos (histórico) do tenant sendo excluído nunca disparam a exclusão de um prompt/guardrail — eles apenas desaparecem como efeito colateral da FK em cascata ao apagar o tenant, sem gerar nenhuma decisão de negócio própria.

**Rationale**: É exatamente a semântica que `get_tenants_by_prompt`/`get_tenants_blocking_prompt` (`modules/prompt_manager/prompt_manager_repository.py:186-207`) e `get_prompts_blocking_guardrail` (linhas 209-226) já usam para decidir se um prompt/guardrail pode ser excluído isoladamente (EDI-43): "vínculos inativos não entram: são histórico, não configuração vigente". Divergir dessa regra só para o fluxo de exclusão de tenant criaria duas definições incompatíveis de "em uso" no mesmo sistema.

**Alternatives considered**: Considerar também vínculos inativos do tenant sendo excluído para decidir exclusividade do prompt — rejeitado porque um prompt que o tenant usou no passado (vínculo hoje inativo) pode nunca ter sido "dele" de fato, e tratá-lo como exclusivo baseado em histórico inflaria o escopo da exclusão além do que o vínculo *vigente* justifica.

## 2. Integridade referencial: migration de FK

**Decision**: Nova migration Alembic (`0003_tenant_prompts_fk`, `Revises: 0002_backfill_tenant_links`) que:
1. Altera `tenant_prompts.tenant_id` de `varchar(100)` para `varchar(50)` (compatível com `tenants.id`).
2. Adiciona `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`.

**Rationale**: A migration `0001_baseline` documenta explicitamente essas duas inconsistências como "reproduzidas de propósito" e afirma que correções de schema "vão em migrações 0002+, que rodam de verdade em todos os ambientes" (ao contrário da 0001, que em produção é só `stamp`). Isso confirma que uma migration 0003 real é o caminho correto e será aplicada em produção via `docker-entrypoint.sh` no próximo deploy.

**Alternatives considered**: Impor a integridade só na camada de aplicação (sem FK) — rejeitado porque não impede escrita direta ou futura de outro código que esqueça a regra; a FK é a garantia que sobrevive a qualquer caminho de código.

## 3. Atomicidade: transação real apesar do autocommit

**Decision**: A orquestração de exclusão deve rodar dentro de um único `with conn.transaction():` (API de transação explícita do psycopg3), usando uma única conexão psycopg compartilhada por toda a operação (guardrails exclusivos → prompts exclusivos → tenant).

**Rationale**: `infrastructure/connection.py::get_db_connection()` abre conexões com `autocommit=True`. Isso significa que os `conn.commit()`/`conn.rollback()` manuais já presentes no código (ex.: `TenantRepository.create_tenant_with_prompt`) não desfazem nada em caso de falha parcial — cada `cur.execute()` já commitou sozinho antes de qualquer rollback ser chamado. É uma lacuna pré-existente, não introduzida por esta feature, mas o requisito FR-009 (atomicidade) desta feature não pode ser satisfeito por esse padrão. O psycopg3 permite blocos de transação explícitos (`conn.transaction()`) mesmo em conexões `autocommit=True` — é a forma correta de obter atomicidade real aqui sem alterar o padrão de conexão do resto do projeto.

**Alternatives considered**: Abrir uma conexão dedicada com `autocommit=False` só para esta operação — funcionaria, mas menos idiomático em psycopg3 e exigiria tratar `commit()`/`close()` manualmente; o bloco `transaction()` já cobre isso com rollback automático em exceção.

## 4. Reuso de repositórios entre módulos (prompt_manager ↔ tenant)

**Decision**: A operação precisa compartilhar UMA conexão entre chamadas que hoje vivem em `TenantRepository` (conexão própria, aberta no `__init__`) e `PromptManagerRepository` (recebe uma *função fábrica* de conexão no construtor, `get_connection_func`). Para reaproveitar os métodos públicos já existentes (`get_tenants_blocking_prompt`, `get_prompts_blocking_guardrail`, `delete_prompt`, `delete_guardrail`) sem duplicar SQL, o `get_connection_func` passado a uma instância de `PromptManagerRepository` criada especificamente para esta operação deve devolver a conexão já aberta (ex.: via `contextlib.nullcontext(conn)`) em vez de abrir uma nova a cada chamada — assim `with self.get_connection() as conn:` dentro dos métodos existentes reaproveita a mesma transação sem fechá-la prematuramente.

**Rationale**: A Legacy Migration Policy da constituição pede que lógica nova em módulo legado "dependa dos métodos públicos existentes do repositório/serviço" em vez de acessar `infrastructure.connection` ou internos de outro módulo diretamente. Essa técnica preserva 100% o reuso dos métodos já testados do EDI-43, sem precisar reescrever suas queries, e sem quebrar a fronteira entre módulos.

**Alternatives considered**: Duplicar as queries de bloqueio/exclusão dentro do módulo `tenant` — rejeitado por violar DRY e por já existir precedente (`TenantService` já importa `PromptManagerRepository` diretamente para `create_tenant`).

## 5. Autenticação administrativa — gap pré-existente, fora de escopo

**Finding**: Nenhum endpoint em `app/api/v1/endpoints/tenant.py` (incluindo o `DELETE` atual) exige credencial administrativa hoje, embora a Constituição (Princípio IV) exija isso para ações administrativas. Este gap é anterior a esta feature e afeta todos os endpoints de tenant, não só a exclusão.

**Decision**: Fora do escopo desta feature. Adicionar autenticação a todos os endpoints de tenant é uma mudança maior e transversal que merece sua própria feature/ticket, não deve ser misturada com a lógica de cascata de exclusão.

## 6. Consultas/queries adicionais necessárias

- `get_prompts_linked_to_tenant_active(tenant_id)`: lista de prompts com vínculo ATIVO ao tenant (uma linha por `node_type`, tipicamente). Não existe hoje como método reutilizável fora de `get_active_prompt_by_tenant` (que exige `node_type` como parâmetro e retorna só 1); precisa de uma variante que retorna todos os `node_type` de uma vez.
- `get_guardrail_links_for_prompt(prompt_id)`: guardrails vinculados a um prompt via `prompt_guardrails` (join direto, SEM misturar `is_global`), retornando também a própria flag `is_global` de cada guardrail — diferente de `get_guardrails_by_prompt`, que já mistura o `OR is_global = TRUE` (correto para runtime, errado para decidir o que apagar).

Essas duas consultas são pequenas adições ao `PromptManagerRepository` existente, seguindo o mesmo estilo (`dict_row`, SQL literal) dos métodos vizinhos.

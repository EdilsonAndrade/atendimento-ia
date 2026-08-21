# Phase 0 — Research: Migrations versionadas do schema PostgreSQL (EDI-37)

**Feature**: `specs/004-alembic-migrations/`
**Data**: 2026-08-21

Todas as incógnitas do Technical Context foram resolvidas. Nenhum `NEEDS CLARIFICATION` remanescente.

---

## R1 — Ferramenta de migração

**Decision**: Alembic (`alembic>=1.13`), adicionado ao `requirements.txt`.

**Rationale**: Decisão tomada com o usuário. O Alembic é o versionador de schema padrão do ecossistema Python/PostgreSQL e **não exige ORM** — uma migração pode ser SQL literal via `op.execute()`. A dependência pesada dele (SQLAlchemy) **já está instalada** no projeto (`sqlalchemy>=2.0.0`, versão real 2.0.45), então o custo real de adoção é uma única linha nova em `requirements.txt`.

**Alternatives considered**:
- *Manter DDL idempotente em runtime* (status quo): não versiona, não tem histórico, não recria o banco do zero e coloca `ALTER TABLE` no caminho quente. É exatamente o problema que o ticket abre.
- *Scripts `.sql` numerados + runner caseiro*: teria que reimplementar histórico, ordenação, transação e bloqueio de concorrência. Sem ganho sobre uma ferramenta madura já suportada pelas dependências existentes.
- *`yoyo-migrations` / `dbmate`*: viáveis, mas adicionam ferramenta e (no caso do `dbmate`) um binário externo à imagem, sem vantagem sobre o Alembic dado que SQLAlchemy já está no projeto.

---

## R2 — Driver na URL de conexão do Alembic (ponto crítico)

**Decision**: O `env.py` normaliza a URL lida de `POSTGRES_DATABASE_URI`, trocando o esquema `postgresql://` (ou `postgres://`) por **`postgresql+psycopg://`** antes de entregá-la ao SQLAlchemy. A variável de ambiente **não muda**.

**Rationale**: Para o esquema `postgresql://`, o dialeto padrão do SQLAlchemy é **psycopg2**, não psycopg 3. O `requirements.txt` declara `psycopg[binary]` (v3) e **não** declara `psycopg2` — logo, dentro do contêiner de produção o Alembic falharia no boot com `ModuleNotFoundError: No module named 'psycopg2'`, quebrando o deploy inteiro. (Na máquina de desenvolvimento o `psycopg2` 2.9.10 existe por acaso, arrastado por outra dependência — o que mascararia o erro nos testes locais e o faria aparecer só em produção.) A normalização é feita **apenas dentro do `env.py`** porque `psycopg.connect()`, usado por todo o resto do projeto em `infrastructure/connection.py`, **não aceita** o sufixo `+psycopg` na URL.

**Alternatives considered**:
- *Alterar `POSTGRES_DATABASE_URI` no `.env` para `postgresql+psycopg://`*: quebraria `infrastructure/connection.py` e todos os `psycopg.connect(DB_URI)` espalhados pelo projeto.
- *Adicionar `psycopg2-binary` ao `requirements.txt`*: instala um segundo driver PostgreSQL na imagem só para o Alembic, aumentando build e superfície de manutenção, e deixando dois drivers concorrentes no projeto.
- *Fixar a URL no `alembic.ini`*: colocaria a senha do banco no repositório, violando a restrição de segredos da constituição.

---

## R3 — Como escrever a migração de baseline

**Decision**: A `0001` usa `op.execute()` com o DDL **literal** extraído do dump de produção, em vez da API `op.create_table()`.

**Rationale**: O critério de aceite é fidelidade exata a produção (FR-003, SC-002), e o schema real usa construções que a API declarativa do Alembic ou não cobre, ou traduz com risco de divergência sutil:

| Construção em produção | Problema com a API declarativa |
|---|---|
| Função `update_timestamp_column()` e 3 gatilhos | Não há API — teria que ser `op.execute()` de qualquer forma |
| Índice único **parcial** `prompts_one_default_per_node ... WHERE is_default = true` | Exige `postgresql_where`, fácil de divergir |
| `allowed_domains text[] DEFAULT '{}'::text[]` | Tipo array com default literal, propenso a tradução incorreta |
| Mistura deliberada de `timestamp without time zone` (`agendamentos`) e `timestamp with time zone` (demais) | Uma tradução equivocada mudaria semântica de fuso horário |
| Defaults de UUID divergentes: `uuid_generate_v4()` vs `gen_random_uuid()` | Precisa ser preservada exatamente como está |

Com SQL literal, a baseline é uma cópia verificável linha a linha contra o dump. Migrações **futuras** ficam livres para usar a API do Alembic quando for mais simples.

**Alternatives considered**:
- *`op.create_table()` / `op.bulk_insert()`*: mais idiomático, mas reintroduz a camada de tradução exatamente onde a exigência é fidelidade byte a byte.
- *Baseline vazia + migrações incrementais reconstruindo a história*: a história real não existe (tabelas criadas na mão, sem registro). Seria ficção.

---

## R4 — Autogenerate e exclusão das tabelas de terceiros

**Decision**: `target_metadata = None` e o `alembic revision --autogenerate` **não é usado** neste projeto — migrações são criadas com `alembic revision -m "..."` e escritas à mão. Ainda assim, o `env.py` define `include_object` com a lista de exclusão das 6 tabelas de terceiros e da extensão de vetores, como salvaguarda documentada.

**Rationale**: Sem modelos SQLAlchemy no projeto (decisão de manter `psycopg`), não existe metadata para comparar — um `--autogenerate` rodado por engano com `target_metadata = None` proporia **remover todas as tabelas do banco**. O `include_object` sozinho não evita isso; a proteção real é a convenção documentada + o teste-guarda (R9). O `include_object` fica configurado porque (a) registra formalmente a fronteira exigida por FR-011/FR-012 e (b) passa a valer automaticamente caso um ticket futuro introduza modelos SQLAlchemy.

**Tabelas excluídas** — criadas e evoluídas pelas próprias bibliotecas:

| Tabela | Dona |
|---|---|
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | `langgraph-checkpoint-postgres` |
| `langchain_pg_collection`, `langchain_pg_embedding` | `langchain-postgres` |
| extensão `vector` | criada pelo `langchain-postgres` na primeira conexão |

A extensão `uuid-ossp` fica **dentro** do controle: os `DEFAULT uuid_generate_v4()` de `prompts`, `guardrails` e `tenant_prompts` dependem dela, e nenhuma biblioteca a cria.

**Alternatives considered**:
- *Versionar tudo, inclusive as tabelas das bibliotecas*: garantiria réplica exata do banco, mas quebra na primeira atualização em que a biblioteca alterar o próprio schema — passariam a existir duas fontes de verdade disputando as mesmas tabelas.

---

## R5 — Proteção do `downgrade` da baseline

**Decision**: O `downgrade()` da `0001` levanta `RuntimeError` por padrão, e só executa os `DROP` se a variável de ambiente `ALEMBIC_ALLOW_BASELINE_DOWNGRADE=1` estiver definida.

**Rationale**: A baseline descreve **todo** o banco. Um `alembic downgrade base` executado por engano apontando para produção apagaria as 9 tabelas com todos os dados de clientes. O ticket é explícito: *"lembre-se que criamos na mão as tabelas, não podemos apagar"*. A trava transforma um comando catastrófico de uma linha em um ato deliberado de duas etapas, e continua permitindo o uso legítimo (descartar um banco de teste local).

**Alternatives considered**:
- *`downgrade()` com os `DROP` normais*: é o padrão do Alembic, mas aqui o risco é perda total de dados de produção.
- *`downgrade()` vazio (`pass`)*: silencioso e mentiroso — o histórico voltaria para `base` deixando as tabelas de pé, e o próximo `upgrade` falharia com "já existe".

---

## R6 — Concorrência entre instâncias no deploy

**Decision**: O `env.py` adquire um **advisory lock transacional** (`SELECT pg_advisory_xact_lock(<chave fixa>)`) antes de executar as migrações.

**Rationale**: Se dois contêineres subirem ao mesmo tempo (restart, escala, redeploy), ambos rodam `alembic upgrade head`. Sem coordenação explícita, os dois podem ler `alembic_version` como desatualizada e tentar aplicar a mesma migração — a segunda falha no meio, deixando o deploy vermelho sem motivo real. O advisory lock é liberado automaticamente no fim da transação (inclusive em caso de erro ou queda do processo), não deixa estado preso, e o custo quando não há disputa é desprezível.

**Alternatives considered**:
- *Confiar no DDL transacional do PostgreSQL*: protege contra corrupção, mas não contra a segunda instância abortar com erro — o deploy falharia de forma confusa.
- *Aplicar migrações só manualmente*: já descartado na decisão de deploy automático (FR-007).

---

## R7 — Ponto de execução no deploy

**Decision**: Um `docker-entrypoint.sh` declarado como `ENTRYPOINT` no `Dockerfile` roda `alembic upgrade head` com `set -e` e depois `exec "$@"`.

**Rationale**: Isto resolve um problema concreto já existente no repositório: o `docker-compose.yml` de produção define `command: ["uvicorn", "app.main:app", ...]`, e no Docker o `command` do Compose **substitui o `CMD` da imagem, mas não o `ENTRYPOINT`**. Ou seja, o `start.sh` atual (referenciado no `CMD`) **não é executado em produção hoje**. Colocar a migração no `ENTRYPOINT` faz com que ela rode independentemente de quem define o comando final. O `set -e` garante FR-009: se a migração falhar, o `exec` nunca acontece e o contêiner morre com log de erro, em vez de servir requisições contra um banco inconsistente.

**Alternatives considered**:
- *`start.sh`*: não roda em produção (a causa raiz descrita acima).
- *Evento `startup` do FastAPI*: a aplicação já subiu quando o handler roda; com múltiplos workers, cada um tentaria migrar; e uma falha ali hoje é engolida por `try/except` (padrão do `app/main.py`), justamente o oposto de FR-009.
- *Passo no GitHub Actions*: o runner de deploy não necessariamente alcança o banco, e a migração deixaria de acompanhar a imagem — um rollback de imagem não teria a migração correspondente.

---

## R8 — Configuração e segredos

**Decision**: `alembic.ini` na raiz do repositório com `sqlalchemy.url` **vazio**; o `env.py` lê `POSTGRES_DATABASE_URI` do ambiente (via `load_dotenv()`, mesmo padrão de `infrastructure/connection.py`) e falha com mensagem clara se a variável não existir. Script em `migrations/`, revisões em `migrations/versions/`.

**Rationale**: A constituição exige que segredos não sejam versionados. O projeto inteiro já resolve conexão por `POSTGRES_DATABASE_URI`; reaproveitar a mesma variável evita uma segunda fonte de verdade de credencial. Diretório `migrations/` (em vez do `alembic/` default) porque o nome descreve o conteúdo e não se confunde com o pacote da biblioteca.

**Nota**: `infrastructure/connection.py` hoje tem um fallback com senha literal (`postgresql://postgres:2765581@localhost:5432/simplificando`). O `env.py` **não** replica esse fallback — sem variável definida, falha explicitamente.

---

## R9 — Estratégia de testes

**Decision**: dois níveis, alinhados ao que o CI já executa (`pytest tests/unit` no workflow de deploy).

**Testes unitários** (`tests/unit/`, sem banco, rodam no CI):
1. Normalização de URL: `postgresql://…` e `postgres://…` → `postgresql+psycopg://…`; URL que já tem driver explícito é preservada; ausência da variável levanta erro.
2. **Teste-guarda anti-regressão**: varre o código-fonte da aplicação (excluindo `migrations/`, `specs/` e `tests/`) e falha se encontrar `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX` ou `DROP TABLE`. É o que garante FR-013 de forma duradoura, e não apenas no dia da entrega.
3. Integridade da cadeia de revisões: existe exatamente uma revisão com `down_revision is None`, e nenhum `revision` duplicado.

**Testes de integração** (`tests/integration/`, exigem PostgreSQL, rodam localmente):
4. `upgrade head` num banco vazio cria as 9 tabelas, os 3 gatilhos, a função, a extensão `uuid-ossp`, o índice parcial e a restrição de `node_type`.
5. Idempotência: rodar `upgrade head` de novo não altera nada.
6. Gatilho funcional: `UPDATE` numa linha de `prompts` altera `updated_at`.

**Rationale**: O workflow de deploy roda apenas `tests/unit`, então nenhum teste que dependa de banco pode entrar nesse caminho sob pena de quebrar o CI. A cobertura de banco fica em `tests/integration/`, como o projeto já faz. O teste-guarda é o item mais valioso do conjunto: é barato, roda no CI e impede que o DDL em runtime volte a aparecer meses depois.

**Alternatives considered**:
- *Subir PostgreSQL como serviço no GitHub Actions*: daria cobertura completa no CI, mas muda o workflow de deploy — fora do escopo acordado.
- *`pytest-alembic`*: traz um conjunto pronto de testes de migração, mas adiciona dependência para cobrir pouco além do que os três testes unitários acima já cobrem neste caso.

---

## R10 — Numeração das revisões

**Decision**: identificadores sequenciais legíveis (`0001_baseline`, `0002_...`) via `file_template` no `alembic.ini` **mais** a passagem explícita de `--rev-id` ao criar revisões, em vez do hash aleatório padrão.

**Rationale**: A ordem de aplicação fica óbvia ao listar o diretório, e o nome do arquivo aparece de forma legível em revisões de código e no histórico do Git. A cadeia continua sendo garantida pelo `down_revision`, não pelo nome.

**Correção após validação prática**: `file_template` sozinho **não** produz numeração sequencial — ele apenas formata o nome do arquivo a partir do id, e o id continua sendo um hash aleatório (verificado: `alembic revision -m "teste"` gerou `f161187115f0_teste.py`). Manter a convenção exige `alembic revision -m "..." --rev-id 0002`. Documentado no `alembic.ini` e no [quickstart.md](./quickstart.md) Cenário 3.

---

## R11 — Impacto em isolamento multi-tenant (exigência da constituição)

**Decision**: Nenhuma mudança no particionamento por tenant.

**Rationale**: O *Development Workflow & Quality Gates* da constituição exige que toda mudança de schema documente explicitamente o impacto no isolamento multi-tenant. Aqui o impacto é **nulo por construção**: a baseline reproduz exatamente a estrutura já em produção — todas as colunas `tenant_id` (`agendamentos`, `tenant_prompts`, `whatsapp_instances`, `tenant_knowledge_base`) e a chave `tenants.id` permanecem idênticas em tipo, restrição e índice. Não são criadas, removidas ou alteradas colunas de escopo de tenant, nem alterada a granularidade de nenhum índice de lookup por tenant (`idx_tenant_prompts_lookup`, `idx_whatsapp_instances_tenant`). O armazenamento vetorial por tenant fica fora do controle do Alembic (R4) e segue intocado, assim como os diretórios `db/<tenant_id>/knowledge_db/`.

A remoção do DDL em runtime também não afeta isolamento: as rotinas removidas criavam estrutura global, nunca dados ou estrutura por tenant.

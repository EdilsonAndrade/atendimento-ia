# Quickstart — Migrations do projeto (EDI-37)

Guia prático dos três cenários que importam: adotar em produção, subir um ambiente do zero e criar uma migração nova.

**Pré-requisito comum**: `POSTGRES_DATABASE_URI` definida no `.env` ou no ambiente. Os comandos rodam a partir da raiz do repositório.

> Se `alembic` não estiver no PATH (comum no Git Bash do Windows), troque `alembic ...` por `python -m alembic ...` em todos os comandos abaixo. É o que o entrypoint do contêiner faz.

---

## Cenário 1 — Adotar o versionamento em PRODUÇÃO (uma única vez)

O banco já existe com dados reais. **Nenhum DDL é executado.**

> **Problema do ovo e da galinha na primeira adoção**: o `alembic` só entra na imagem
> depois do rebuild com o `requirements.txt` novo — mas o `stamp` precisa acontecer
> **antes** do primeiro deploy (senão o `ENTRYPOINT` roda `upgrade head` num banco não
> marcado e falha com `relation "tenants" already exists`). Use o **caminho A** abaixo,
> que não depende de imagem nova. Depois da primeira adoção, o caminho B vale sempre.

### Caminho A — stamp via SQL (recomendado para a primeira adoção)

`alembic stamp` não faz mágica: ele apenas cria a tabela `alembic_version` e grava uma
linha. Verificado na prática — em um banco vazio, depois do `stamp`, existe exatamente
**uma** tabela. O equivalente exato em SQL:

```bash
docker exec -i NOME_DO_CONTAINER_DB psql -U postgres -d NOME_DO_BANCO <<'SQL'
CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num character varying(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO public.alembic_version (version_num) VALUES ('0001_baseline');
SQL
```

Conferência:

```bash
docker exec NOME_DO_CONTAINER_DB psql -U postgres -d NOME_DO_BANCO \
  -c "SELECT version_num FROM alembic_version;"
# deve imprimir: 0001_baseline
```

Feito isso, o deploy da imagem nova roda `alembic upgrade head`, encontra o banco já em
`0001_baseline` e não executa nada.

### Caminho B — stamp via Alembic (depois que a imagem nova estiver em produção)

```bash
# 1. Backup. Não pule.
pg_dump "$POSTGRES_DATABASE_URI" > backup-pre-alembic-$(date +%F).dump

# 2. Confirme que o banco ainda não está sob controle (saída deve ser vazia)
alembic current

# 3. Confira que a estrutura real bate com a baseline ANTES de marcar.
#    Compare este dump com specs/004-alembic-migrations/data-model.md
pg_dump --schema-only --no-owner --no-privileges "$POSTGRES_DATABASE_URI"

# 4. Marque a baseline como já aplicada — NÃO executa DDL, apenas registra
alembic stamp 0001_baseline

# 5. Verifique
alembic current          # deve imprimir 0001_baseline
alembic upgrade head     # deve não fazer nada e sair com sucesso
```

**Verificação de segurança** — as contagens devem ser idênticas às de antes:

```sql
SELECT 'tenants' t, count(*) FROM tenants
UNION ALL SELECT 'prompts', count(*) FROM prompts
UNION ALL SELECT 'guardrails', count(*) FROM guardrails
UNION ALL SELECT 'prompt_guardrails', count(*) FROM prompt_guardrails
UNION ALL SELECT 'tenant_prompts', count(*) FROM tenant_prompts
UNION ALL SELECT 'whatsapp_instances', count(*) FROM whatsapp_instances
UNION ALL SELECT 'agendamentos', count(*) FROM agendamentos
UNION ALL SELECT 'chat_thread_sessions', count(*) FROM chat_thread_sessions
UNION ALL SELECT 'tenant_knowledge_base', count(*) FROM tenant_knowledge_base;
```

> **Se o passo 3 revelar divergência** entre produção e a baseline: **pare**. Não marque. A baseline precisa ser corrigida para refletir a realidade antes de qualquer `stamp` — senão o histórico passa a mentir sobre o estado do banco.

---

## Cenário 2 — Subir um ambiente novo do zero

Banco vazio (desenvolvedor novo, outra cloud, ambiente de teste).

```bash
# 1. Crie o banco vazio
createdb simplificando          # ou equivalente na sua cloud

# 2. Aplique tudo
alembic upgrade head

# 3. Confirme
alembic current                 # deve imprimir a última revisão
```

Isso cria as 9 tabelas, a extensão `uuid-ossp`, a função `update_timestamp_column()`, os 3 gatilhos, todos os índices (incluindo o parcial `prompts_one_default_per_node`) e as 3 chaves estrangeiras.

**As tabelas de bibliotecas de terceiros não são criadas aqui** — a memória de conversa (LangGraph) e o armazenamento de vetores (LangChain, com a extensão `vector`) são criadas pelas próprias bibliotecas na primeira vez que a aplicação as usa. O usuário do banco precisa ter permissão para criar extensão nesse primeiro uso.

Depois disso, suba a aplicação normalmente.

---

## Cenário 3 — Criar uma migração nova

```bash
# 1. Gere o arquivo (NÃO use --autogenerate, ver nota abaixo)
#    O --rev-id é o que mantém a numeração sequencial: sem ele o Alembic gera um
#    hash aleatório (ex: f161187115f0_adiciona_fk...). Use o próximo número livre.
alembic revision -m "adiciona fk de tenant_id em agendamentos" --rev-id 0002

# 2. Edite o arquivo criado em migrations/versions/ preenchendo upgrade() e downgrade()

# 3. Teste em banco local
alembic upgrade head
alembic downgrade -1     # confirme que a reversão funciona
alembic upgrade head

# 4. Commit do arquivo de migração junto com o código que depende dele
```

> **Nunca use `alembic revision --autogenerate` neste projeto.** Não existem modelos SQLAlchemy (as consultas usam `psycopg` direto), então `target_metadata` é `None` e o autogenerate proporia **remover todas as tabelas do banco**.

**Regras para escrever a migração**:
- `upgrade()` e `downgrade()` devem ser simétricos; teste os dois.
- Não misture estrutura e dados no mesmo arquivo sem necessidade.
- Não altere as tabelas de terceiros (`checkpoint*`, `langchain_pg_*`).
- Toda mudança de schema precisa documentar o impacto no isolamento multi-tenant (exigência da constituição do projeto).

---

## Cenário 4 — Deploy

Nada a fazer manualmente. O `ENTRYPOINT` da imagem roda `alembic upgrade head` antes de iniciar a aplicação.

```bash
# Acompanhar a aplicação das migrações no deploy
docker logs -f chatatendimento-api
```

Se uma migração falhar, o contêiner **não sobe** e o erro aparece no log — comportamento intencional, para nunca servir requisições contra um banco em estado inconsistente.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Can't load plugin: sqlalchemy.dialects:postgresql.psycopg2` | A normalização de URL do `env.py` não foi aplicada | Confirme que o `env.py` converte o esquema para `postgresql+psycopg://` |
| `POSTGRES_DATABASE_URI não definida` | Variável ausente no ambiente/`.env` | Defina a variável. O `env.py` não tem fallback, de propósito |
| `relation "prompts" already exists` no `upgrade` | Banco já tinha a estrutura mas não foi marcado | Use `alembic stamp 0001_baseline` (Cenário 1), não `upgrade` |
| `Target database is not up to date` | Existe migração pendente | Rode `alembic upgrade head` |
| Contêiner reinicia em laço no deploy | Migração falhando | `docker logs` do contêiner; corrija a migração ou o acesso ao banco |
| `downgrade` da baseline recusado | Trava proposital contra perda de dados | Só em banco descartável: `ALEMBIC_ALLOW_BASELINE_DOWNGRADE=1 alembic downgrade base` |

---

## Comandos de teste

```bash
# Testes unitários (sem banco — mesmo conjunto que o CI de deploy executa)
pytest tests/unit -v

# Testes de integração das migrations (exigem PostgreSQL acessível)
pytest tests/integration -v

# Suíte completa
pytest tests/ -v
```

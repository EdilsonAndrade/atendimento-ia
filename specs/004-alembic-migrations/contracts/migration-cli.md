# Contrato operacional — comandos de migração (EDI-37)

Esta feature não expõe endpoint HTTP. A interface que ela entrega é **operacional**: comandos de linha para operadores e um contrato de inicialização do contêiner. Este documento define esse contrato — o que cada comando garante e o que ele nunca faz.

---

## 1. Comandos de operador

Todos são executados a partir da raiz do repositório, com `POSTGRES_DATABASE_URI` definida no ambiente (ou no `.env`).

### `alembic current`

**Faz**: imprime a revisão aplicada no banco apontado.
**Garante**: somente leitura. Nunca altera estrutura nem dados.
**Saída em banco nunca migrado**: vazia (a tabela `alembic_version` ainda não existe).

### `alembic history`

**Faz**: lista as migrações conhecidas pelo repositório, em ordem.
**Garante**: somente leitura, nem sequer conecta ao banco.

### `alembic upgrade head`

**Faz**: aplica todas as migrações pendentes, em ordem, cada uma em sua própria transação.
**Garante**:
- Adquire um advisory lock antes de aplicar; instâncias concorrentes esperam em vez de colidir.
- Num banco já atualizado, não executa nada e retorna código de saída `0`.
- Falha de migração → transação revertida e código de saída **diferente de zero**.

### `alembic stamp 0001_baseline`

**Faz**: grava `0001_baseline` em `alembic_version` **sem executar nenhum DDL**.
**Garante**: nenhuma tabela, coluna, índice, restrição, função, gatilho ou linha é criada, alterada ou removida.
**Uso**: exclusivamente na adoção inicial em um banco que **já possui** a estrutura (produção). Ver `quickstart.md`.

### `alembic revision -m "descricao"`

**Faz**: cria um arquivo de migração vazio em `migrations/versions/`, já encadeado na revisão atual.
**Garante**: não toca no banco.
**Restrição do projeto**: `--autogenerate` **não é usado** aqui. Sem modelos SQLAlchemy, ele proporia remover todas as tabelas do banco. Migrações são escritas à mão.

### `alembic downgrade <revisao>`

**Faz**: reverte migrações.
**Restrição do projeto**: o `downgrade` da `0001_baseline` está **travado**. Sem a variável de ambiente `ALEMBIC_ALLOW_BASELINE_DOWNGRADE=1`, ele levanta erro e não executa nada. A trava existe porque reverter a baseline significa apagar as 9 tabelas com todos os dados de clientes.

---

## 2. Contrato de inicialização do contêiner

```text
ENTRYPOINT ["/app/docker-entrypoint.sh"]   ← sempre executa; o Compose NÃO substitui
CMD        ["/app/start.sh"]               ← substituído pelo `command:` do docker-compose.yml
```

`docker-entrypoint.sh` garante, nesta ordem:

1. Executa `alembic upgrade head`.
2. **Se falhar** → não inicia a aplicação; sai com código diferente de zero e a mensagem de erro fica no log do contêiner.
3. **Se tiver sucesso** → `exec "$@"`, entregando o processo ao comando final (o `uvicorn` do Compose em produção, o `CMD` da imagem em outros contextos).

**Por que no `ENTRYPOINT` e não no `CMD`**: o `docker-compose.yml` de produção define `command: ["uvicorn", ...]`, que substitui o `CMD` da imagem. Qualquer coisa colocada no `CMD`/`start.sh` **não roda em produção** — é o caso hoje.

**Invariante**: a aplicação nunca começa a atender requisições com migrações pendentes ou com uma migração que falhou.

---

## 3. Contrato interno do `env.py`

| Item | Contrato |
|---|---|
| Origem da URL | Variável de ambiente `POSTGRES_DATABASE_URI` (via `load_dotenv()`) |
| Ausência da variável | Erro explícito na inicialização. **Sem** fallback para credencial local |
| Normalização | `postgresql://` e `postgres://` → `postgresql+psycopg://`. URL com driver já explícito é preservada |
| `target_metadata` | `None` — não há modelos SQLAlchemy no projeto |
| `include_object` | Exclui `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `langchain_pg_collection`, `langchain_pg_embedding` |
| Bloqueio | `pg_advisory_xact_lock` adquirido antes de aplicar as migrações; liberado ao fim da transação |
| Segredos | `alembic.ini` mantém `sqlalchemy.url` vazio — nenhuma credencial versionada |

---

## 4. O que este contrato explicitamente **não** oferece

- **Migração de dados**: a `0001` cria estrutura, nunca insere linhas. O *seed* de prompts (`seed_missing_node_prompts`, EDI-42) continua onde está, no evento de inicialização do FastAPI — é dado, não estrutura.
- **Reversão segura em produção**: reverter a baseline é destrutivo por natureza e está travado de propósito.
- **Gestão das tabelas de terceiros**: memória de conversa (LangGraph) e armazenamento de vetores (LangChain) continuam sendo criadas e evoluídas pelas próprias bibliotecas.

"""Ambiente de execução do Alembic (EDI-37).

Três responsabilidades além do padrão gerado pelo Alembic:

1. **Driver correto**: a URL vem de `POSTGRES_DATABASE_URI` e é normalizada para
   psycopg 3 por `infrastructure/db_url.py` (o psycopg2, default do SQLAlchemy para
   `postgresql://`, não é dependência deste projeto).
2. **Fronteira com bibliotecas de terceiros**: `include_object()` exclui as tabelas
   criadas e evoluídas pelo langgraph-checkpoint-postgres e pelo langchain-postgres.
3. **Bloqueio entre instâncias**: um advisory lock transacional impede que dois
   contêineres subindo ao mesmo tempo tentem aplicar a mesma migração.

ATENÇÃO: `alembic revision --autogenerate` NÃO deve ser usado neste projeto. Como as
consultas usam psycopg puro, não existem modelos SQLAlchemy e `target_metadata` é
`None` — o autogenerate proporia REMOVER todas as tabelas do banco. Migrações são
criadas com `alembic revision -m "..."` e escritas à mão.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from infrastructure.db_url import build_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sem modelos SQLAlchemy no projeto — ver aviso sobre autogenerate no docstring.
target_metadata = None

# Tabelas de bibliotecas de terceiros: criadas e migradas pelas próprias libs.
# Versioná-las aqui criaria duas fontes de verdade disputando os mesmos objetos,
# quebrando na primeira atualização em que a lib alterasse o próprio schema.
THIRD_PARTY_TABLES = frozenset(
    {
        # langgraph-checkpoint-postgres (memória de conversa do agente)
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        # langchain-postgres (armazenamento de vetores da busca semântica)
        "langchain_pg_collection",
        "langchain_pg_embedding",
    }
)

# Chave arbitrária, porém FIXA, do advisory lock. Precisa ser a mesma em todas as
# instâncias para que elas de fato disputem o mesmo lock.
MIGRATION_LOCK_KEY = 4837721


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    """Mantém as tabelas de terceiros fora do alcance do Alembic."""
    if type_ == "table" and name in THIRD_PARTY_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Gera o SQL das migrações sem conectar ao banco (`alembic upgrade --sql`)."""
    context.configure(
        url=build_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrações conectando ao banco."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = build_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            # Serializa instâncias concorrentes (restart, redeploy, escala): a segunda
            # espera aqui em vez de tentar aplicar a mesma migração e falhar no meio.
            # Sendo transacional, o lock é liberado sozinho no commit/rollback — não
            # deixa estado preso nem se o processo morrer.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": MIGRATION_LOCK_KEY},
            )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

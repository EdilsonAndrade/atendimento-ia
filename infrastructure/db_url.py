"""Resolve a URL de conexão do PostgreSQL para o SQLAlchemy/Alembic.

Por que este módulo existe (EDI-37): o projeto inteiro usa `psycopg.connect(DB_URI)`
com uma URL no formato `postgresql://...` (ver `infrastructure/connection.py`). O
Alembic, porém, conecta através do SQLAlchemy — e para o esquema `postgresql://` o
dialeto PADRÃO do SQLAlchemy é o **psycopg2**, que NÃO é dependência deste projeto
(o `requirements.txt` declara `psycopg[binary]`, ou seja, psycopg **3**).

Sem a normalização feita aqui, o Alembic falharia dentro do contêiner de produção com
`ModuleNotFoundError: No module named 'psycopg2'`, derrubando o deploy inteiro. Pior:
em máquinas de desenvolvimento o psycopg2 costuma existir por acaso, arrastado por
outra dependência — o erro passaria despercebido localmente e só apareceria em produção.

A conversão vive isolada aqui (e não dentro de `migrations/env.py`) para poder ser
testada sem carregar o contexto do Alembic — ver `tests/unit/test_alembic_env_url.py`.

IMPORTANTE: a variável de ambiente `POSTGRES_DATABASE_URI` NÃO muda de formato. O
sufixo `+psycopg` é aplicado apenas na entrega ao SQLAlchemy, porque
`psycopg.connect()` — usado por todo o resto do projeto — não o aceita.
"""
import os

from dotenv import load_dotenv

# Esquemas que o SQLAlchemy resolveria para psycopg2 e que precisam ser redirecionados.
_SCHEMES_TO_NORMALIZE = ("postgresql://", "postgres://")

_PSYCOPG3_SCHEME = "postgresql+psycopg://"

ENV_VAR_NAME = "POSTGRES_DATABASE_URI"


class DatabaseUrlNotConfiguredError(RuntimeError):
    """Levantada quando POSTGRES_DATABASE_URI não está definida no ambiente."""


def normalize_driver(url: str) -> str:
    """Garante que o SQLAlchemy use o driver psycopg 3.

    - `postgresql://user:pw@host/db`  -> `postgresql+psycopg://user:pw@host/db`
    - `postgres://user:pw@host/db`    -> `postgresql+psycopg://user:pw@host/db`
    - `postgresql+psycopg://...`      -> preservada (já explícita)
    - `postgresql+asyncpg://...`      -> preservada (driver escolhido de propósito)
    """
    for scheme in _SCHEMES_TO_NORMALIZE:
        if url.startswith(scheme):
            return _PSYCOPG3_SCHEME + url[len(scheme):]
    return url


def build_database_url() -> str:
    """Lê POSTGRES_DATABASE_URI do ambiente e devolve a URL pronta para o SQLAlchemy.

    Diferente de `infrastructure/connection.py`, aqui NÃO existe fallback para uma
    credencial local: uma migração apontando para o banco errado por causa de um
    default silencioso é pior do que uma falha explícita no boot.
    """
    load_dotenv()
    raw_url = os.getenv(ENV_VAR_NAME)
    if not raw_url:
        raise DatabaseUrlNotConfiguredError(
            f"{ENV_VAR_NAME} não definida. O Alembic precisa dela para saber em qual "
            "banco aplicar as migrations — não há valor padrão por segurança."
        )
    return normalize_driver(raw_url)

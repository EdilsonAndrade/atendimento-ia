"""Normalização da URL de conexão entregue ao SQLAlchemy/Alembic (EDI-37).

Por que este teste importa: o SQLAlchemy resolve `postgresql://` para **psycopg2**,
que não é dependência deste projeto (usamos `psycopg[binary]`, ou seja, psycopg 3).
Sem a normalização, o Alembic quebra no boot do contêiner de produção com
`ModuleNotFoundError: No module named 'psycopg2'` e derruba o deploy inteiro.

Em máquinas de desenvolvimento o psycopg2 às vezes existe por acaso (arrastado por
outra dependência), então o erro passaria despercebido localmente. Este teste roda
no CI e fecha essa porta.
"""
import pytest

from infrastructure.db_url import (
    DatabaseUrlNotConfiguredError,
    ENV_VAR_NAME,
    build_database_url,
    normalize_driver,
)


@pytest.fixture(autouse=True)
def _sem_dotenv(monkeypatch):
    """Neutraliza o load_dotenv() para o teste não depender do .env da máquina.

    Sem isso, o cenário "variável ausente" falharia sempre que existisse um .env
    local definindo POSTGRES_DATABASE_URI.
    """
    monkeypatch.setattr("infrastructure.db_url.load_dotenv", lambda *a, **k: False)


# --- normalize_driver ---------------------------------------------------------


def test_normaliza_esquema_postgresql_para_psycopg3():
    resultado = normalize_driver("postgresql://user:pw@localhost:5432/simplificando")

    assert resultado == "postgresql+psycopg://user:pw@localhost:5432/simplificando"


def test_normaliza_esquema_curto_postgres_para_psycopg3():
    resultado = normalize_driver("postgres://user:pw@localhost:5432/simplificando")

    assert resultado == "postgresql+psycopg://user:pw@localhost:5432/simplificando"


def test_preserva_url_que_ja_traz_driver_explicito():
    url = "postgresql+psycopg://user:pw@localhost:5432/simplificando"

    assert normalize_driver(url) == url


def test_preserva_driver_diferente_escolhido_de_proposito():
    url = "postgresql+asyncpg://user:pw@localhost:5432/simplificando"

    assert normalize_driver(url) == url


def test_preserva_query_string_e_credencial_com_caracteres_especiais():
    url = "postgresql://user:p%40ss@host:5432/db?sslmode=require"

    assert normalize_driver(url) == (
        "postgresql+psycopg://user:p%40ss@host:5432/db?sslmode=require"
    )


# --- build_database_url -------------------------------------------------------


def test_le_a_variavel_de_ambiente_e_normaliza(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "postgresql://user:pw@db:5432/simplificando")

    assert build_database_url() == "postgresql+psycopg://user:pw@db:5432/simplificando"


def test_erro_explicito_quando_a_variavel_nao_existe(monkeypatch):
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)

    with pytest.raises(DatabaseUrlNotConfiguredError) as excinfo:
        build_database_url()

    assert ENV_VAR_NAME in str(excinfo.value)


def test_erro_explicito_quando_a_variavel_esta_vazia(monkeypatch):
    monkeypatch.setenv(ENV_VAR_NAME, "")

    with pytest.raises(DatabaseUrlNotConfiguredError):
        build_database_url()


def test_nao_ha_fallback_para_credencial_local(monkeypatch):
    """Diferente de infrastructure/connection.py, aqui não existe default.

    Um default silencioso faria uma migração rodar contra o banco errado — falha
    barulhenta é preferível.
    """
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)

    with pytest.raises(DatabaseUrlNotConfiguredError):
        build_database_url()

"""Migração de baseline aplicada num banco realmente vazio (EDI-37).

Reproduz o Cenário 2 do quickstart: cria um banco temporário, roda
`alembic upgrade head` e confere que a estrutura resultante é a de produção.

Exige um PostgreSQL acessível via POSTGRES_DATABASE_URI, com permissão de
CREATE DATABASE. Se não houver, os testes são pulados (o CI de deploy roda apenas
`pytest tests/unit`).
"""
import os
import uuid

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TABELAS_ESPERADAS = {
    "tenants",
    "prompts",
    "guardrails",
    "prompt_guardrails",
    "tenant_prompts",
    "whatsapp_instances",
    "agendamentos",
    "chat_thread_sessions",
    "tenant_knowledge_base",
}

GATILHOS_ESPERADOS = {
    "update_prompts_modtime",
    "update_guardrails_modtime",
    "update_tenant_prompts_modtime",
}


def _admin_url():
    url = os.getenv("POSTGRES_DATABASE_URI")
    if not url:
        pytest.skip("POSTGRES_DATABASE_URI não definida")
    return url


def _trocar_banco_na_url(url: str, novo_banco: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{novo_banco}"


@pytest.fixture(scope="module")
def banco_temporario():
    """Cria um banco vazio só para este módulo e o remove ao final."""
    admin_url = _admin_url()
    nome = f"test_alembic_{uuid.uuid4().hex[:12]}"

    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    except psycopg.Error as e:
        pytest.skip(f"Sem PostgreSQL acessível ou sem permissão de CREATE DATABASE: {e}")

    url_teste = _trocar_banco_na_url(admin_url, nome)
    try:
        yield url_teste
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(nome)
                )
            )


@pytest.fixture(scope="module")
def banco_migrado(banco_temporario, monkeypatch_module):
    """Aplica `alembic upgrade head` no banco temporário."""
    monkeypatch_module.setenv("POSTGRES_DATABASE_URI", banco_temporario)

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")

    return banco_temporario


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _consultar(url, query, params=None):
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()


# --- estrutura criada ---------------------------------------------------------


def test_cria_as_nove_tabelas_do_projeto(banco_migrado):
    linhas = _consultar(
        banco_migrado,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
    )
    tabelas = {linha[0] for linha in linhas}

    assert TABELAS_ESPERADAS <= tabelas, (
        f"Faltando: {TABELAS_ESPERADAS - tabelas}"
    )


def test_nao_cria_tabelas_de_bibliotecas_de_terceiros(banco_migrado):
    """checkpoint*/langchain_pg_* são criadas pelas próprias libs, não pelo Alembic."""
    linhas = _consultar(
        banco_migrado,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
    )
    tabelas = {linha[0] for linha in linhas}

    terceiros = {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "langchain_pg_collection",
        "langchain_pg_embedding",
    }

    assert not (tabelas & terceiros)


def test_cria_a_extensao_uuid_ossp(banco_migrado):
    linhas = _consultar(
        banco_migrado, "SELECT extname FROM pg_extension WHERE extname = 'uuid-ossp'"
    )

    assert linhas, "uuid-ossp é necessária pelos DEFAULT uuid_generate_v4()"


def test_cria_a_funcao_e_os_tres_gatilhos_de_updated_at(banco_migrado):
    funcoes = _consultar(
        banco_migrado,
        "SELECT proname FROM pg_proc WHERE proname = 'update_timestamp_column'",
    )
    assert funcoes

    linhas = _consultar(
        banco_migrado,
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal",
    )
    gatilhos = {linha[0] for linha in linhas}

    assert GATILHOS_ESPERADOS <= gatilhos


def test_cria_o_indice_unico_parcial_de_prompt_padrao_por_node_type(banco_migrado):
    linhas = _consultar(
        banco_migrado,
        "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
        ("prompts_one_default_per_node",),
    )

    assert linhas, "índice parcial prompts_one_default_per_node ausente"
    definicao = linhas[0][0].lower()
    assert "unique" in definicao
    assert "where" in definicao and "is_default" in definicao


def test_cria_a_restricao_de_valores_de_node_type(banco_migrado):
    linhas = _consultar(
        banco_migrado,
        "SELECT conname FROM pg_constraint WHERE conname = 'prompts_node_type_check'",
    )

    assert linhas


def test_cria_as_tres_chaves_estrangeiras(banco_migrado):
    linhas = _consultar(
        banco_migrado,
        "SELECT conname FROM pg_constraint WHERE contype = 'f'",
    )
    fks = {linha[0] for linha in linhas}

    assert {
        "prompt_guardrails_prompt_id_fkey",
        "prompt_guardrails_guardrail_id_fkey",
        "tenant_prompts_prompt_id_fkey",
    } <= fks


def test_agendamentos_usa_timestamp_sem_fuso(banco_migrado):
    """Divergência real de produção que precisa ser preservada exatamente."""
    linhas = _consultar(
        banco_migrado,
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'agendamentos' AND column_name IN ('created_at', 'deleted_at')
        """,
    )
    tipos = dict(linhas)

    assert tipos["created_at"] == "timestamp without time zone"
    assert tipos["deleted_at"] == "timestamp without time zone"


# --- comportamento ------------------------------------------------------------


def test_gatilho_de_updated_at_funciona(banco_migrado):
    with psycopg.connect(banco_migrado, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prompts (titulo, conteudo) VALUES (%s, %s) "
                "RETURNING id, updated_at",
                ("teste gatilho", "conteudo"),
            )
            prompt_id, updated_antes = cur.fetchone()

            cur.execute(
                "UPDATE prompts SET conteudo = %s WHERE id = %s RETURNING updated_at",
                ("conteudo alterado", prompt_id),
            )
            (updated_depois,) = cur.fetchone()

            cur.execute("DELETE FROM prompts WHERE id = %s", (prompt_id,))

    assert updated_depois > updated_antes


def test_indice_parcial_impede_dois_prompts_padrao_no_mesmo_node_type(banco_migrado):
    with psycopg.connect(banco_migrado, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prompts (titulo, conteudo, is_default, node_type) "
                "VALUES (%s, %s, TRUE, 'chitchat') RETURNING id",
                ("padrao 1", "c"),
            )
            (primeiro_id,) = cur.fetchone()

            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute(
                    "INSERT INTO prompts (titulo, conteudo, is_default, node_type) "
                    "VALUES (%s, %s, TRUE, 'chitchat')",
                    ("padrao 2", "c"),
                )

    with psycopg.connect(banco_migrado, autocommit=True) as conn:
        conn.execute("DELETE FROM prompts WHERE id = %s", (primeiro_id,))


def test_upgrade_rodado_de_novo_e_inofensivo(banco_migrado, monkeypatch_module):
    """Segunda execução de `upgrade head` não altera nada e sai com sucesso."""
    monkeypatch_module.setenv("POSTGRES_DATABASE_URI", banco_migrado)

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")

    linhas = _consultar(banco_migrado, "SELECT version_num FROM alembic_version")

    # A versão gravada é a head ATUAL, resolvida do próprio diretório de
    # migrações. Antes isto era comparado com "0001_baseline" fixo, o que só
    # valia enquanto a baseline era a única revisão — o teste quebrava a cada
    # migração nova, sem que nada de errado tivesse acontecido. O que ele
    # verifica de fato é que rodar `upgrade head` de novo é inofensivo.
    head = ScriptDirectory.from_config(config).get_current_head()

    assert linhas == [(head,)]

"""Migração de backfill dos vínculos tenant→prompt (EDI-43 / FR-028, FR-029, SC-010).

Roda contra bancos temporários de verdade, seguindo o padrão de
`test_migrations_baseline.py`. O que está sendo verificado é o contrato de
implantação: nenhum tenant existente pode ficar em estado de erro depois do
deploy que ativa a obrigatoriedade de vínculo.

Exige POSTGRES_DATABASE_URI com permissão de CREATE DATABASE; sem isso, pula.
"""

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "0001_baseline"
BACKFILL = "0002_backfill_tenant_links"


def _admin_url():
    url = os.getenv("POSTGRES_DATABASE_URI")
    if not url:
        pytest.skip("POSTGRES_DATABASE_URI não definida")
    return url


def _trocar_banco_na_url(url: str, novo_banco: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{novo_banco}"


@pytest.fixture
def banco_na_baseline(monkeypatch):
    """Banco temporário migrado ATÉ a baseline (antes do backfill), para que cada
    teste monte seu próprio cenário e então aplique o 0002."""
    admin_url = _admin_url()
    nome = f"test_edi43_backfill_{uuid.uuid4().hex[:10]}"

    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    except psycopg.Error as e:
        pytest.skip(f"Sem PostgreSQL acessível ou sem permissão de CREATE DATABASE: {e}")

    url_teste = _trocar_banco_na_url(admin_url, nome)
    monkeypatch.setenv("POSTGRES_DATABASE_URI", url_teste)

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, BASELINE)

    try:
        yield url_teste, config
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


def _executar(url, query, params=None):
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())


def _consultar(url, query, params=None):
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()


def _criar_tenant(url, tenant_id):
    _executar(
        url,
        """
        INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (tenant_id, f"Tenant {tenant_id}", "cal@test", []),
    )


def _criar_prompt_padrao(url, titulo="Operacional Padrão"):
    _executar(
        url,
        """
        INSERT INTO prompts (titulo, conteudo, is_default, node_type)
        VALUES (%s, %s, TRUE, 'operational')
        """,
        (titulo, "conteudo padrao {guardrails}"),
    )


def _vinculos_ativos(url, tenant_id):
    return _consultar(
        url,
        """
        SELECT tp.prompt_id
        FROM tenant_prompts tp
        JOIN prompts p ON p.id = tp.prompt_id
        WHERE tp.tenant_id = %s AND tp.is_active = TRUE AND p.node_type = 'operational'
        """,
        (tenant_id,),
    )


def test_tenant_sem_vinculo_passa_a_ter_vinculo(banco_na_baseline):
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    _criar_tenant(url, "tenant-orfao")

    assert _vinculos_ativos(url, "tenant-orfao") == []

    command.upgrade(config, BACKFILL)

    assert len(_vinculos_ativos(url, "tenant-orfao")) == 1


def test_nenhum_tenant_fica_sem_vinculo_apos_o_backfill(banco_na_baseline):
    """SC-010: zero tenants em estado de erro depois da implantação."""
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    for i in range(3):
        _criar_tenant(url, f"tenant-{i}")

    command.upgrade(config, BACKFILL)

    sem_vinculo = _consultar(
        url,
        """
        SELECT t.id FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM tenant_prompts tp
            JOIN prompts p ON p.id = tp.prompt_id
            WHERE tp.tenant_id = t.id AND tp.is_active = TRUE AND p.node_type = 'operational'
        )
        """,
    )
    assert sem_vinculo == []


def test_nao_altera_vinculo_ja_existente(banco_na_baseline):
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    _executar(
        url,
        "INSERT INTO prompts (titulo, conteudo, is_default, node_type) VALUES (%s, %s, FALSE, 'operational')",
        ("Prompt Próprio", "conteudo proprio"),
    )
    proprio_id = _consultar(url, "SELECT id FROM prompts WHERE titulo = 'Prompt Próprio'")[0][0]
    _criar_tenant(url, "tenant-configurado")
    _executar(
        url,
        "INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active) VALUES (%s, %s, TRUE)",
        ("tenant-configurado", proprio_id),
    )

    command.upgrade(config, BACKFILL)

    vinculos = _vinculos_ativos(url, "tenant-configurado")
    assert len(vinculos) == 1 and vinculos[0][0] == proprio_id


def test_instalacao_nova_sem_tenants_nao_falha(banco_na_baseline):
    """Banco vazio: nada a fazer, e falhar aqui derrubaria a subida do container."""
    url, config = banco_na_baseline

    command.upgrade(config, BACKFILL)  # não deve levantar

    assert _consultar(url, "SELECT COUNT(*) FROM tenant_prompts")[0][0] == 0


def test_tenant_orfao_sem_prompt_is_default_usa_prompt_operacional_existente(banco_na_baseline):
    """Caso que a primeira versão desta migração deixava passar.

    Havia tenant órfão e nenhum prompt is_default operational (o admin desmarcou,
    ou o default só existia para chitchat). A migração retornava sem fazer nada e
    justamente os tenants que ela deveria resgatar quebravam no atendimento.
    """
    url, config = banco_na_baseline
    _executar(
        url,
        "INSERT INTO prompts (titulo, conteudo, is_default, node_type) VALUES (%s, %s, FALSE, 'operational')",
        ("Operacional Sem Default", "conteudo {guardrails}"),
    )
    _criar_tenant(url, "tenant-sem-default")

    command.upgrade(config, BACKFILL)

    assert len(_vinculos_ativos(url, "tenant-sem-default")) == 1


def test_tenant_orfao_sem_nenhum_prompt_operacional_recebe_prompt_semente(banco_na_baseline):
    """Último recurso: há tenant órfão e nenhum prompt operacional no banco. A
    migração cria o semente a partir do .md, porque o seed do startup só rodaria
    depois — tarde demais para esses tenants."""
    url, config = banco_na_baseline
    _criar_tenant(url, "tenant-sem-nada")

    command.upgrade(config, BACKFILL)

    assert len(_vinculos_ativos(url, "tenant-sem-nada")) == 1
    conteudo = _consultar(
        url, "SELECT conteudo FROM prompts WHERE node_type = 'operational' LIMIT 1"
    )[0][0]
    assert "{guardrails}" in conteudo, "o semente precisa preservar o placeholder cru"


def test_backfill_nao_grava_marcador_no_conteudo_do_prompt(banco_na_baseline):
    """custom_content_override é o CONTEÚDO do prompt daquele tenant, não um campo
    de metadados: o runtime faz COALESCE(custom_content_override, conteudo). Um
    marcador ali seria entregue ao modelo como se fosse o prompt do cliente."""
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    _criar_tenant(url, "tenant-conteudo")

    command.upgrade(config, BACKFILL)

    overrides = _consultar(
        url,
        "SELECT custom_content_override FROM tenant_prompts WHERE tenant_id = %s",
        ("tenant-conteudo",),
    )
    assert all(o[0] is None for o in overrides)


def test_downgrade_remove_apenas_os_vinculos_criados_pelo_backfill(banco_na_baseline):
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    _executar(
        url,
        "INSERT INTO prompts (titulo, conteudo, is_default, node_type) VALUES (%s, %s, FALSE, 'operational')",
        ("Prompt Manual", "conteudo manual"),
    )
    manual_id = _consultar(url, "SELECT id FROM prompts WHERE titulo = 'Prompt Manual'")[0][0]

    _criar_tenant(url, "tenant-manual")
    _executar(
        url,
        "INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active) VALUES (%s, %s, TRUE)",
        ("tenant-manual", manual_id),
    )
    _criar_tenant(url, "tenant-backfill")

    command.upgrade(config, BACKFILL)
    command.downgrade(config, BASELINE)

    assert _vinculos_ativos(url, "tenant-backfill") == []
    assert len(_vinculos_ativos(url, "tenant-manual")) == 1


def test_upgrade_e_idempotente(banco_na_baseline):
    url, config = banco_na_baseline
    _criar_prompt_padrao(url)
    _criar_tenant(url, "tenant-idem")

    command.upgrade(config, BACKFILL)
    total_apos_primeira = _consultar(url, "SELECT COUNT(*) FROM tenant_prompts")[0][0]

    command.downgrade(config, BASELINE)
    command.upgrade(config, BACKFILL)

    assert _consultar(url, "SELECT COUNT(*) FROM tenant_prompts")[0][0] == total_apos_primeira

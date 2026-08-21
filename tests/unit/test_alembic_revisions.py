"""Integridade da cadeia de revisões do Alembic (EDI-37).

Não conecta ao banco: apenas carrega os arquivos de `migrations/versions/` e verifica
que a cadeia é linear e resolve até um único `head`. Uma cadeia quebrada (duas raízes,
duas pontas, revisão duplicada) só apareceria no deploy — este teste antecipa isso no CI.
"""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001_baseline"


@pytest.fixture(scope="module")
def script_directory():
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_existe_exatamente_uma_revisao_raiz(script_directory):
    raizes = [
        revision.revision
        for revision in script_directory.walk_revisions()
        if revision.down_revision is None
    ]

    assert raizes == [BASELINE_REVISION], (
        "Deve haver exatamente uma revisão raiz (a baseline). Encontradas: "
        f"{raizes}"
    )


def test_nao_ha_revisao_duplicada(script_directory):
    revisoes = [revision.revision for revision in script_directory.walk_revisions()]

    assert len(revisoes) == len(set(revisoes))


def test_cadeia_resolve_ate_um_unico_head(script_directory):
    heads = script_directory.get_heads()

    assert len(heads) == 1, f"Cadeia ramificada — heads encontrados: {heads}"


def test_a_baseline_esta_na_cadeia(script_directory):
    revisoes = {revision.revision for revision in script_directory.walk_revisions()}

    assert BASELINE_REVISION in revisoes

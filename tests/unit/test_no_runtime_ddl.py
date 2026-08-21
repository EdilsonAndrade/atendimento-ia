"""Teste-guarda: a aplicação não pode mais alterar a estrutura do banco (EDI-37).

Antes deste ticket, quatro rotinas executavam DDL em tempo de execução — uma delas
(`ensure_node_type_schema`) rodava `ALTER TABLE` em oito métodos do repositório de
prompts, ou seja, durante o atendimento normal de requisições.

Agora as migrations em `migrations/` são a única fonte de verdade do schema. Este teste
existe para que essa decisão sobreviva ao tempo: se alguém reintroduzir um
`CREATE TABLE IF NOT EXISTS` num repositório meses depois, o CI reprova na hora, em vez
de o projeto voltar silenciosamente a ter duas fontes de verdade disputando o schema.

Escopo: apenas o código-fonte da aplicação. `migrations/`, `tests/` e `specs/` ficam de
fora — é exatamente ali que DDL deve morar.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

DIRETORIOS_DA_APLICACAO = (
    "app",
    "modules",
    "infrastructure",
    "prompts",
    "protocols",
    "util",
)

PADRAO_DDL = re.compile(
    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|CREATE\s+(UNIQUE\s+)?INDEX|DROP\s+TABLE)\b",
    re.IGNORECASE,
)


def _arquivos_da_aplicacao():
    for diretorio in DIRETORIOS_DA_APLICACAO:
        base = REPO_ROOT / diretorio
        if not base.exists():
            continue
        for arquivo in base.rglob("*.py"):
            # testes colocados junto do código não são código de produção
            if arquivo.name.startswith("test_"):
                continue
            if "__pycache__" in arquivo.parts:
                continue
            yield arquivo


def test_nenhum_ddl_no_codigo_da_aplicacao():
    ocorrencias = []

    for arquivo in _arquivos_da_aplicacao():
        conteudo = arquivo.read_text(encoding="utf-8")
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if PADRAO_DDL.search(linha):
                relativo = arquivo.relative_to(REPO_ROOT).as_posix()
                ocorrencias.append(f"{relativo}:{numero}: {linha.strip()}")

    assert not ocorrencias, (
        "DDL encontrado no código da aplicação. A estrutura do banco é gerenciada "
        "exclusivamente por migrations/ (EDI-37) — mova esta alteração para uma nova "
        "migration com `alembic revision -m \"...\"`:\n  "
        + "\n  ".join(ocorrencias)
    )


@pytest.mark.parametrize(
    "caminho, simbolo",
    [
        ("modules/prompt_manager/prompt_manager_repository.py", "ensure_node_type_schema"),
        ("modules/ia/thread_session.py", "init_thread_sessions_table"),
        ("modules/agendamento/booking_tools.py", "init_booking_table"),
        ("modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py", "_ensure_table"),
        ("modules/knowledge_base/infrastructure/postgres_knowledge_base_repository.py", "_TABLE_DDL"),
    ],
)
def test_rotinas_de_ddl_removidas(caminho, simbolo):
    """As rotinas específicas removidas por este ticket não podem voltar.

    A verificação é feita sobre o texto-fonte, e não por import, de propósito: importar
    `booking_tools` puxaria o LangChain inteiro, tornando o teste refém de dependências
    pesadas que nada têm a ver com o que está sendo verificado.
    """
    conteudo = (REPO_ROOT / caminho).read_text(encoding="utf-8")

    assert simbolo not in conteudo, (
        f"{caminho} voltou a definir `{simbolo}` — removido pelo EDI-37. O schema agora "
        "é gerenciado exclusivamente por migrations/."
    )

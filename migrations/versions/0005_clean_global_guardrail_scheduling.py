"""guardrails: remove conteúdo de agendamento do guardrail global

Revision ID: 0005_clean_global_guardrail
Revises: 0004_scheduling_enabled
Create Date: 2026-08-22

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
O guardrail is_global=TRUE semeado a partir de prompts/guardrails.md misturava
regras genéricas de comportamento (piadas, palavrões, prompt injection) com
regras específicas de negócio de agendamento (privacidade de agenda, "um
agendamento por vez"). Por ser GLOBAL, esse texto ia para TODO tenant em TODO
nó (chitchat, institutional, operational) — inclusive tenants com
`scheduling_enabled = FALSE` (ex.: simplificandoai), que não têm agenda
nenhuma para proteger nem ferramenta de agendamento para restringir.

As regras de agendamento foram movidas para BOOKING_INTEGRITY_RULE
(modules/ia/agent_graph.py), injetada apenas quando o tenant tem tools de
agendamento ativas (mesmo padrão do EDI que tornou `scheduling_enabled`
explícito para tools). Esta migração atualiza o CONTEÚDO já gravado no banco
do(s) guardrail(s) is_global que ainda carregam o texto antigo — o seed do
startup (`seed_missing_node_prompts`) só INSERE quando nenhum is_global existe
ainda, então nunca corrigiria uma linha já existente.

SELEÇÃO DO ALVO
---------------
Não filtramos por título (o admin pode ter renomeado — o painel já mostra
"Guardrail Padrão - Segurança, Privacidade e Escopo", diferente do título do
seed) nem por conteúdo exatamente igual ao do arquivo atual (o texto no banco
já pode ter divergido do arquivo, ou sido levemente editado pelo admin).
Usamos uma marca inequívoca do texto antigo ("STRICT CALENDAR PRIVACY RULES")
para não tocar em outros guardrails globais sem relação com isso (ex.: um
guardrail "POLIGLOTA" também is_global=TRUE).
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0005_clean_global_guardrail"
down_revision: Union[str, None] = "0004_scheduling_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tabela de controle: guarda o conteúdo anterior de cada guardrail alterado,
# para que o downgrade restaure exatamente o que havia antes (e não apenas o
# arquivo .md da revisão atual, que pode já ter mudado de novo até lá).
TABELA_CONTROLE = "edi_clean_global_guardrail_backup"

# Presente apenas na versão antiga do texto (regra de privacidade de agenda).
# Uma coincidência acidental exigiria outro guardrail citando esse trecho
# exato em inglês, o que não é um risco realista nesta base.
MARCA_CONTEUDO_ANTIGO = "STRICT CALENDAR PRIVACY RULES"


def _conteudo_novo() -> str:
    caminho = Path(__file__).resolve().parents[2] / "prompts" / "guardrails.md"
    return caminho.read_text(encoding="utf-8")


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_CONTROLE} (
            guardrail_id UUID PRIMARY KEY,
            conteudo_anterior TEXT NOT NULL,
            aplicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    alvos = conn.exec_driver_sql(
        """
        SELECT id, conteudo FROM guardrails
        WHERE is_global = TRUE AND conteudo LIKE %(marca)s
        """,
        {"marca": f"%{MARCA_CONTEUDO_ANTIGO}%"},
    ).fetchall()

    if not alvos:
        print(
            "[GUARDRAIL-CLEAN] Nenhum guardrail global com conteúdo de agendamento "
            "encontrado; nada a fazer."
        )
        return

    conteudo_novo = _conteudo_novo()

    for guardrail_id, conteudo_atual in alvos:
        conn.exec_driver_sql(
            f"""
            INSERT INTO {TABELA_CONTROLE} (guardrail_id, conteudo_anterior)
            VALUES (%(id)s, %(conteudo)s)
            ON CONFLICT (guardrail_id) DO NOTHING
            """,
            {"id": guardrail_id, "conteudo": conteudo_atual},
        )
        conn.exec_driver_sql(
            """
            UPDATE guardrails SET conteudo = %(novo)s, updated_at = NOW()
            WHERE id = %(id)s
            """,
            {"novo": conteudo_novo, "id": guardrail_id},
        )

    print(
        f"[GUARDRAIL-CLEAN] Conteúdo de agendamento removido de {len(alvos)} "
        f"guardrail(s) global(is)."
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        f"""
        UPDATE guardrails g SET conteudo = c.conteudo_anterior, updated_at = NOW()
        FROM {TABELA_CONTROLE} c
        WHERE g.id = c.guardrail_id
        """
    )
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {TABELA_CONTROLE}")

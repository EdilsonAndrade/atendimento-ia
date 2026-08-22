"""backfill: vincula tenants sem prompt operacional ao prompt padrão (EDI-43)

Revision ID: 0002_backfill_tenant_links
Revises: 0001_baseline
Create Date: 2026-08-22

POR QUE ESTA MIGRAÇÃO EXISTE
----------------------------
O EDI-43 elimina o fallback implícito: a partir dele, um tenant sem prompt
'operational' vinculado deixa de receber o template genérico do projeto e passa a
gerar erro de configuração. Os tenants que hoje rodam sem vínculo — justamente os
que dependiam desse fallback — passariam a falhar no primeiro atendimento.

Esta migração associa cada um deles ao prompt que hoje serve como padrão
(`is_default = TRUE`, `node_type = 'operational'`), preservando na prática o
comportamento que eles já tinham, agora de forma explícita.

ORDEM É A GARANTIA
------------------
O `docker-entrypoint.sh` aplica as migrações na subida do container, antes de a
API atender qualquer requisição. Por isso o backfill precede o primeiro
atendimento no MESMO deploy que ativa a obrigatoriedade — não é preciso coordenar
duas implantações nem usar feature flag.

É uma migração de DADOS quanto ao efeito. A única estrutura criada é a tabela de
controle abaixo, usada exclusivamente para tornar o downgrade preciso.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_backfill_tenant_links"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabela de controle: registra QUAIS vínculos esta migração criou.
#
# Por que ela existe em vez de um marcador dentro da própria linha de
# tenant_prompts: o único campo livre ali seria `custom_content_override`, que
# NÃO é um campo de metadados — é o conteúdo do prompt daquele tenant. O runtime
# faz `COALESCE(tp.custom_content_override, p.conteudo)`, então escrever um
# marcador nele entregaria a string do marcador ao modelo como se fosse o prompt
# do cliente. Uma tabela separada custa pouco e não corrompe nada.
TABELA_CONTROLE = "edi43_backfill_tenant_prompts"

# Tenants sem nenhum vínculo operacional ativo. É esta consulta — e não a
# existência de um prompt padrão — que decide se o backfill tem trabalho a fazer.
SQL_TENANTS_ORFAOS = """
    SELECT COUNT(*) FROM tenants t
    WHERE NOT EXISTS (
        SELECT 1
        FROM tenant_prompts tp
        JOIN prompts p ON p.id = tp.prompt_id
        WHERE tp.tenant_id = t.id
          AND tp.is_active = TRUE
          AND p.node_type = 'operational'
    )
"""


def _resolver_prompt_para_backfill(conn):
    """Escolhe a que prompt vincular os tenants órfãos, em ordem de preferência.

    1. O prompt is_default operational — é o que esses tenants efetivamente
       recebiam pelo fallback, então preserva o comportamento atual deles.
    2. Qualquer prompt operational, o mais antigo. Não é o ideal, mas um prompt
       real do banco é melhor do que deixar o tenant sem atendimento.

    O ORDER BY é deliberado: `get_default_prompt` usa LIMIT 1 sem ordenação, e se
    houver mais de um is_default o resultado pode variar entre execuções. Uma
    migração não pode herdar essa indeterminação.
    """
    for filtro in ("is_default = TRUE AND node_type = 'operational'", "node_type = 'operational'"):
        linha = conn.exec_driver_sql(
            f"SELECT id FROM prompts WHERE {filtro} ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if linha is not None:
            return linha[0]
    return None


def _criar_prompt_semente(conn):
    """Cria o prompt operacional semente a partir do arquivo do projeto.

    Mesmo conteúdo que o seed do startup usaria — mas o seed roda DEPOIS das
    migrações, e aqui já há tenants órfãos esperando um vínculo. O conteúdo é
    gravado cru, com o placeholder {guardrails} intacto, para que os guardrails
    continuem sendo injetados a cada atendimento.
    """
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "prompts" / "operactional_prompt.md"
    conteudo = caminho.read_text(encoding="utf-8")

    return conn.exec_driver_sql(
        """
        INSERT INTO prompts (titulo, conteudo, is_default, node_type)
        VALUES (%(titulo)s, %(conteudo)s, TRUE, 'operational')
        RETURNING id
        """,
        {"titulo": "Operacional - Padrão", "conteudo": conteudo},
    ).fetchone()[0]


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_CONTROLE} (
            tenant_id VARCHAR(100) NOT NULL,
            prompt_id UUID NOT NULL,
            aplicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tenant_id, prompt_id)
        )
        """
    )

    # A decisão de pular ou não depende de EXISTIR TENANT ÓRFÃO, não da existência
    # de um prompt padrão.
    #
    # A versão anterior desta migração tratava "não há prompt is_default
    # operational" como se fosse sempre "instalação nova" e retornava. Isso é uma
    # suposição, não uma verificação: um banco de produção pode perfeitamente ter
    # tenants sem vínculo E nenhum prompt marcado como is_default operational (o
    # admin desmarcou, ou o default só foi definido para chitchat). Nesse caso o
    # backfill não fazia nada e justamente os tenants que ele deveria resgatar
    # quebravam no primeiro atendimento.
    orfaos = conn.exec_driver_sql(SQL_TENANTS_ORFAOS).scalar()

    if not orfaos:
        print("[EDI-43] Nenhum tenant sem vínculo operacional; backfill não é necessário.")
        return

    prompt_id = _resolver_prompt_para_backfill(conn)

    if prompt_id is None:
        # Só chega aqui se houver tenant órfão e NENHUM prompt operacional no banco.
        # Deixar assim quebraria esses tenants, então a migração cria o prompt
        # semente a partir do mesmo arquivo que o seed do startup usaria.
        prompt_id = _criar_prompt_semente(conn)
        print("[EDI-43] Nenhum prompt operational existia; prompt semente criado para o backfill.")

    # Registra antes de inserir, para que o downgrade saiba exatamente o que
    # remover mesmo se algo falhar no meio.
    conn.exec_driver_sql(
        f"""
        INSERT INTO {TABELA_CONTROLE} (tenant_id, prompt_id)
        SELECT t.id, %(prompt_id)s
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1
            FROM tenant_prompts tp
            JOIN prompts p ON p.id = tp.prompt_id
            WHERE tp.tenant_id = t.id
              AND tp.is_active = TRUE
              AND p.node_type = 'operational'
        )
        ON CONFLICT (tenant_id, prompt_id) DO NOTHING
        """,
        {"prompt_id": prompt_id},
    )

    resultado = conn.exec_driver_sql(
        """
        INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active)
        SELECT t.id, %(prompt_id)s, TRUE
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1
            FROM tenant_prompts tp
            JOIN prompts p ON p.id = tp.prompt_id
            WHERE tp.tenant_id = t.id
              AND tp.is_active = TRUE
              AND p.node_type = 'operational'
        )
        ON CONFLICT (tenant_id, prompt_id)
        DO UPDATE SET is_active = TRUE, updated_at = NOW()
        """,
        {"prompt_id": prompt_id},
    )

    print(f"[EDI-43] Backfill aplicado a {resultado.rowcount} tenant(s) sem vínculo operacional.")


def downgrade() -> None:
    # Remove SOMENTE os vínculos registrados na tabela de controle. Os vínculos
    # que já existiam antes — configurados pelo admin — permanecem intactos.
    conn = op.get_bind()

    conn.exec_driver_sql(
        f"""
        DELETE FROM tenant_prompts tp
        USING {TABELA_CONTROLE} c
        WHERE tp.tenant_id = c.tenant_id AND tp.prompt_id = c.prompt_id
        """
    )
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {TABELA_CONTROLE}")

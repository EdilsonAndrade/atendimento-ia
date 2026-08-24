"""
Integration test do EDI-60: PostgresTokenUsageRepository contra um Postgres real.

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a migration
0007_chat_token_usage já aplicada.

Rodar com: pytest tests/integration/test_postgres_token_usage_repository.py -v
"""
import uuid
from decimal import Decimal

import psycopg
import pytest

from infrastructure.connection import DB_URI
from modules.token_usage.domain.token_usage_record import TokenUsageRecord
from modules.token_usage.infrastructure.postgres_token_usage_repository import PostgresTokenUsageRepository


def _limpar_registros(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_token_usage WHERE tenant_id = %s", (tenant_id,))


def test_save_persiste_e_pode_ser_lido_de_volta():
    tenant_id = f"tenant_teste_edi60_{uuid.uuid4().hex[:8]}"
    base_thread_id = f"{tenant_id}:sessao_1"
    repository = PostgresTokenUsageRepository()

    try:
        repository.save(TokenUsageRecord(
            tenant_id=tenant_id,
            base_thread_id=base_thread_id,
            thread_id=f"{base_thread_id}#abc123",
            node_type="operational_node",
            input_tokens=120,
            output_tokens=45,
            total_tokens=165,
            estimated_cost_usd=Decimal("0.001234"),
        ))

        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id, base_thread_id, node_type, input_tokens, output_tokens,
                           total_tokens, estimated_cost_usd, created_at
                    FROM chat_token_usage WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()

        assert row is not None
        assert row[0] == tenant_id
        assert row[1] == base_thread_id
        assert row[2] == "operational_node"
        assert row[3] == 120
        assert row[4] == 45
        assert row[5] == 165
        assert row[6] == Decimal("0.001234")
        assert row[7] is not None  # created_at preenchido (US2)
    finally:
        _limpar_registros(tenant_id)


def test_soma_por_base_thread_id_e_por_tenant():
    tenant_a = f"tenant_teste_edi60_a_{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant_teste_edi60_b_{uuid.uuid4().hex[:8]}"
    conversa_a1 = f"{tenant_a}:sessao_1"
    repository = PostgresTokenUsageRepository()

    try:
        # Duas chamadas da mesma conversa (tenant A)
        repository.save(TokenUsageRecord(
            tenant_id=tenant_a, base_thread_id=conversa_a1, thread_id=None,
            node_type="routing_agent", input_tokens=10, output_tokens=2, total_tokens=12,
            estimated_cost_usd=Decimal("0.10"),
        ))
        repository.save(TokenUsageRecord(
            tenant_id=tenant_a, base_thread_id=conversa_a1, thread_id=None,
            node_type="operational_node", input_tokens=50, output_tokens=20, total_tokens=70,
            estimated_cost_usd=Decimal("0.20"),
        ))
        # Uma chamada de outro tenant
        repository.save(TokenUsageRecord(
            tenant_id=tenant_b, base_thread_id=f"{tenant_b}:sessao_1", thread_id=None,
            node_type="chitchat_node", input_tokens=5, output_tokens=5, total_tokens=10,
            estimated_cost_usd=Decimal("0.05"),
        ))

        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT SUM(estimated_cost_usd) FROM chat_token_usage WHERE base_thread_id = %s",
                    (conversa_a1,),
                )
                total_conversa_a1 = cur.fetchone()[0]

                cur.execute(
                    "SELECT SUM(estimated_cost_usd) FROM chat_token_usage WHERE tenant_id = %s",
                    (tenant_a,),
                )
                total_tenant_a = cur.fetchone()[0]

                cur.execute(
                    "SELECT SUM(estimated_cost_usd) FROM chat_token_usage WHERE tenant_id = %s",
                    (tenant_b,),
                )
                total_tenant_b = cur.fetchone()[0]

        assert total_conversa_a1 == Decimal("0.30")
        assert total_tenant_a == Decimal("0.30")
        assert total_tenant_b == Decimal("0.05")
    finally:
        _limpar_registros(tenant_a)
        _limpar_registros(tenant_b)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

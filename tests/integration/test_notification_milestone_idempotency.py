"""EDI-63: idempotência do claim de notificação de marco (`tenant_usage_notifications`).

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a migration
0008_tenant_message_limit já aplicada.

Rodar com: pytest tests/integration/test_notification_milestone_idempotency.py -v
"""
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from infrastructure.connection import DB_URI
from modules.tenant_limits.infrastructure.postgres_notification_claim import PostgresNotificationClaim


def _limpar_registros(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenant_usage_notifications WHERE tenant_id = %s", (tenant_id,))


def test_primeiro_claim_do_mes_ganha_e_segundo_perde():
    tenant_id = f"tenant_teste_edi63_{uuid.uuid4().hex[:8]}"
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    claim = PostgresNotificationClaim()

    try:
        assert claim.try_claim(tenant_id, year_month, 50) is True
        assert claim.try_claim(tenant_id, year_month, 50) is False  # já reclamado
        assert claim.try_claim(tenant_id, year_month, 80) is True  # marco diferente, claim próprio
    finally:
        _limpar_registros(tenant_id)


def test_claims_concorrentes_do_mesmo_marco_so_um_ganha():
    """Simula duas requisições concorrentes cruzando o mesmo marco — a constraint
    UNIQUE garante que só uma delas dispara o e-mail."""
    tenant_id = f"tenant_teste_edi63_concorrente_{uuid.uuid4().hex[:8]}"
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    claim_a = PostgresNotificationClaim()
    claim_b = PostgresNotificationClaim()

    try:
        resultado_a = claim_a.try_claim(tenant_id, year_month, 100)
        resultado_b = claim_b.try_claim(tenant_id, year_month, 100)

        assert {resultado_a, resultado_b} == {True, False}
    finally:
        _limpar_registros(tenant_id)


def test_mesmo_marco_em_meses_diferentes_sao_claims_independentes():
    tenant_id = f"tenant_teste_edi63_mes_{uuid.uuid4().hex[:8]}"
    claim = PostgresNotificationClaim()

    try:
        assert claim.try_claim(tenant_id, "2026-07", 100) is True
        assert claim.try_claim(tenant_id, "2026-08", 100) is True
    finally:
        _limpar_registros(tenant_id)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

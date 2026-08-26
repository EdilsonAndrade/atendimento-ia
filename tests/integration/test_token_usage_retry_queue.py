"""EDI-63: fila de retry de `chat_token_usage` (Redis Streams) + worker.

PRÉ-REQUISITO: Redis acessível via REDIS_URL (e Postgres real com a migration
0007_chat_token_usage aplicada, para o worker gravar de fato).

Rodar com: pytest tests/integration/test_token_usage_retry_queue.py -v
"""
import uuid
from decimal import Decimal

import psycopg
import pytest

from infrastructure.connection import DB_URI
from modules.token_usage.domain.token_usage_record import TokenUsageRecord
from modules.token_usage.infrastructure.postgres_token_usage_repository import PostgresTokenUsageRepository
from modules.token_usage.infrastructure.redis_retry_queue import (
    DEAD_LETTER_STREAM_NAME,
    STREAM_NAME,
    RedisStreamRetryQueue,
    get_redis_client,
)
from modules.token_usage.infrastructure.retry_worker import TokenUsageRetryWorker


def _limpar_streams(client):
    client.delete(STREAM_NAME)
    client.delete(DEAD_LETTER_STREAM_NAME)


def _limpar_chat_token_usage(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_token_usage WHERE tenant_id = %s", (tenant_id,))


def _record(tenant_id: str) -> TokenUsageRecord:
    return TokenUsageRecord(
        tenant_id=tenant_id,
        base_thread_id=f"{tenant_id}:sessao_1",
        thread_id=f"{tenant_id}:sessao_1#abc",
        node_type="operational_node",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        estimated_cost_usd=Decimal("0.001234"),
    )


def test_publish_e_worker_grava_no_postgres_e_confirma():
    client = get_redis_client()
    tenant_id = f"tenant_teste_edi63_retry_{uuid.uuid4().hex[:8]}"
    _limpar_streams(client)

    try:
        RedisStreamRetryQueue(client).publish(_record(tenant_id))

        worker = TokenUsageRetryWorker(client=client, repository=PostgresTokenUsageRepository())
        worker.run_once()

        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chat_token_usage WHERE tenant_id = %s", (tenant_id,))
                assert cur.fetchone()[0] == 1

        # Confirmado (XACK) — não deve haver pendências.
        pending = client.xpending(STREAM_NAME, "token_usage_retry_workers")
        assert pending["pending"] == 0
    finally:
        _limpar_chat_token_usage(tenant_id)
        _limpar_streams(client)


def test_falha_permanente_vai_para_dead_letter_apos_max_tentativas():
    client = get_redis_client()
    tenant_id = f"tenant_teste_edi63_deadletter_{uuid.uuid4().hex[:8]}"
    _limpar_streams(client)

    class _AlwaysFailingRepository:
        def save(self, record):
            raise RuntimeError("Postgres indisponível (simulado)")

    try:
        RedisStreamRetryQueue(client).publish(_record(tenant_id))

        worker = TokenUsageRetryWorker(
            client=client, repository=_AlwaysFailingRepository(), max_attempts=2, min_idle_ms=0,
        )
        # 2 tentativas dentro do limite; a 3ª deve mover para dead-letter.
        worker.run_once()
        worker.run_once()
        worker.run_once()

        dead_letter_entries = client.xrange(DEAD_LETTER_STREAM_NAME)
        matching = [e for e in dead_letter_entries if e[1]["tenant_id"] == tenant_id]
        assert len(matching) == 1
        assert matching[0][1]["thread_id"] == f"{tenant_id}:sessao_1#abc"

        pending = client.xpending(STREAM_NAME, "token_usage_retry_workers")
        assert pending["pending"] == 0  # XACK na entrada original ao mover pra dead-letter
    finally:
        _limpar_streams(client)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

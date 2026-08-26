"""Adapter Redis de `RetryQueuePort` — Infrastructure layer (EDI-63).

Usa Redis Streams (não uma List simples) para que o worker (retry_worker.py)
consiga usar consumer group + XACK: uma entrada só sai da fila depois de
confirmada a gravação no Postgres, e uma entrada pendente sobrevive a um
restart do worker (ver specs/010-tenant-message-limit/research.md).
"""
import os

import redis

from modules.token_usage.domain.token_usage_record import TokenUsageRecord

STREAM_NAME = "token_usage_retry"
DEAD_LETTER_STREAM_NAME = "token_usage_retry:dead_letter"
CONSUMER_GROUP = "token_usage_retry_workers"


def get_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/2")
    return redis.from_url(redis_url, decode_responses=True)


def record_to_fields(record: TokenUsageRecord) -> dict:
    return {
        "tenant_id": record.tenant_id,
        "base_thread_id": record.base_thread_id,
        "thread_id": record.thread_id or "",
        "node_type": record.node_type,
        "input_tokens": str(record.input_tokens),
        "output_tokens": str(record.output_tokens),
        "total_tokens": str(record.total_tokens),
        "estimated_cost_usd": str(record.estimated_cost_usd),
    }


def fields_to_record(fields: dict) -> TokenUsageRecord:
    from decimal import Decimal

    return TokenUsageRecord(
        tenant_id=fields["tenant_id"],
        base_thread_id=fields["base_thread_id"],
        thread_id=fields["thread_id"] or None,
        node_type=fields["node_type"],
        input_tokens=int(fields["input_tokens"]),
        output_tokens=int(fields["output_tokens"]),
        total_tokens=int(fields["total_tokens"]),
        estimated_cost_usd=Decimal(fields["estimated_cost_usd"]),
    )


class RedisStreamRetryQueue:
    def __init__(self, client: redis.Redis | None = None):
        self._client = client or get_redis_client()

    def publish(self, record: TokenUsageRecord) -> None:
        self._client.xadd(STREAM_NAME, record_to_fields(record))

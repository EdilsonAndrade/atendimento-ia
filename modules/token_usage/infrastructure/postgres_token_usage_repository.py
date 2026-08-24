"""Adapter Postgres do Protocol TokenUsageRepository — Infrastructure layer.

A tabela `chat_token_usage` é criada pela migration `0007_chat_token_usage`
(migrations/versions/).
"""
import psycopg

from infrastructure.connection import DB_URI
from modules.token_usage.domain.token_usage_record import TokenUsageRecord


class PostgresTokenUsageRepository:
    def save(self, record: TokenUsageRecord) -> None:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_token_usage
                        (tenant_id, base_thread_id, thread_id, node_type,
                         input_tokens, output_tokens, total_tokens, estimated_cost_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.tenant_id,
                        record.base_thread_id,
                        record.thread_id,
                        record.node_type,
                        record.input_tokens,
                        record.output_tokens,
                        record.total_tokens,
                        record.estimated_cost_usd,
                    ),
                )

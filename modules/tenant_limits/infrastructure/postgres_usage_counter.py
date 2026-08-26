"""Adapter Postgres de `UsageCounterPort` — Infrastructure layer.

Conta chamadas de LLM (linhas de `chat_token_usage`, EDI-60) do mês corrente por
tenant, usando o índice já existente `ix_chat_token_usage_tenant_created`.
"""
import psycopg

from infrastructure.connection import DB_URI


class PostgresUsageCounter:
    def count_current_month(self, tenant_id: str) -> int:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM chat_token_usage
                    WHERE tenant_id = %s AND created_at >= date_trunc('month', NOW())
                    """,
                    (tenant_id,),
                )
                return cur.fetchone()[0]

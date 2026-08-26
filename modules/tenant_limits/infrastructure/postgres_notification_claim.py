"""Adapter Postgres de `NotificationClaimPort` — Infrastructure layer.

O `UNIQUE (tenant_id, year_month, milestone)` de `tenant_usage_notifications`
(migration 0008) é o que torna este claim atômico sob concorrência — ver
specs/010-tenant-message-limit/research.md §3.
"""
import psycopg

from infrastructure.connection import DB_URI


class PostgresNotificationClaim:
    def try_claim(self, tenant_id: str, year_month: str, milestone: int) -> bool:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_usage_notifications (tenant_id, year_month, milestone)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id, year_month, milestone) DO NOTHING
                    RETURNING id
                    """,
                    (tenant_id, year_month, milestone),
                )
                return cur.fetchone() is not None

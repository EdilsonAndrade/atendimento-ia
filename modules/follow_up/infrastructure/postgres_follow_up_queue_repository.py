"""Adapter Postgres do Protocol FollowUpQueueRepository — Infrastructure layer.

A tabela `follow_up_queue` é criada pela migration `0009_conversation_followup`
(migrations/versions/). `UNIQUE (active_thread_id)` é o que torna `save()` um claim
idempotente (FR-004) via `ON CONFLICT DO NOTHING`.
"""
import psycopg

from infrastructure.connection import DB_URI
from modules.follow_up.domain.follow_up_entry import FollowUpEntry


class PostgresFollowUpQueueRepository:
    def save(self, entry: FollowUpEntry) -> bool:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO follow_up_queue
                        (tenant_id, base_thread_id, active_thread_id, outcome, summary,
                         draft_message, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (active_thread_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        entry.tenant_id,
                        entry.base_thread_id,
                        entry.active_thread_id,
                        entry.outcome.value,
                        entry.summary,
                        entry.draft_message,
                        entry.status.value,
                    ),
                )
                return cur.fetchone() is not None

    def list_by_tenant(
        self, tenant_id: str, status: str | None = None, outcome: str | None = None
    ) -> list[FollowUpEntry]:
        return self._list(tenant_id=tenant_id, status=status, outcome=outcome)

    def list_all(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
    ) -> list[FollowUpEntry]:
        return self._list(tenant_id=tenant_id, status=status, outcome=outcome)

    def _list(
        self,
        tenant_id: str | None,
        status: str | None,
        outcome: str | None,
    ) -> list[FollowUpEntry]:
        query = """
            SELECT tenant_id, base_thread_id, active_thread_id, outcome, summary,
                   draft_message, status, id, created_at
            FROM follow_up_queue
            WHERE 1 = 1
        """
        params: list = []
        if tenant_id is not None:
            query += " AND tenant_id = %s"
            params.append(tenant_id)
        if status is not None:
            query += " AND status = %s"
            params.append(status)
        if outcome is not None:
            query += " AND outcome = %s"
            params.append(outcome)
        query += " ORDER BY created_at DESC"

        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row) -> FollowUpEntry:
        return FollowUpEntry(
            tenant_id=row[0],
            base_thread_id=row[1],
            active_thread_id=row[2],
            outcome=row[3],
            summary=row[4],
            draft_message=row[5],
            status=row[6],
            id=row[7],
            created_at=row[8],
        )

    def update(
        self,
        tenant_id: str,
        entry_id: int,
        status: str | None = None,
        draft_message: str | None = None,
        approved_by: str | None = None,
    ) -> FollowUpEntry | None:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE follow_up_queue
                    SET status = COALESCE(%(status)s, status),
                        draft_message = COALESCE(%(draft_message)s, draft_message),
                        approved_by = COALESCE(%(approved_by)s, approved_by),
                        approved_at = CASE WHEN %(status)s = 'aprovado' THEN NOW() ELSE approved_at END
                    WHERE id = %(entry_id)s AND tenant_id = %(tenant_id)s
                    RETURNING tenant_id, base_thread_id, active_thread_id, outcome, summary,
                              draft_message, status, id, created_at
                    """,
                    {
                        "status": status,
                        "draft_message": draft_message,
                        "approved_by": approved_by,
                        "entry_id": entry_id,
                        "tenant_id": tenant_id,
                    },
                )
                row = cur.fetchone()

        if row is None:
            return None
        return self._row_to_entry(row)

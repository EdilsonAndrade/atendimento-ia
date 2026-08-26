"""Adapter Postgres de `GlobalRecipientsPort` + CRUD de `global_notification_recipients`
(EDI-63) — Infrastructure layer.
"""
import psycopg

from infrastructure.connection import DB_URI

FALLBACK_EMAIL = "contato@interasisai.com.br"


class PostgresGlobalRecipients:
    def list_active_emails(self) -> list[str]:
        rows = self.list_all(active_only=True)
        emails = [row["email"] for row in rows]
        return emails or [FALLBACK_EMAIL]

    def list_all(self, active_only: bool = False) -> list[dict]:
        query = "SELECT id, email, active, created_at FROM global_notification_recipients"
        if active_only:
            query += " WHERE active = TRUE"
        query += " ORDER BY email;"

        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()

        return [
            {"id": row[0], "email": row[1], "active": row[2], "created_at": row[3]}
            for row in rows
        ]

    def create(self, email: str) -> dict:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO global_notification_recipients (email)
                    VALUES (%s)
                    RETURNING id, email, active, created_at
                    """,
                    (email,),
                )
                row = cur.fetchone()

        return {"id": row[0], "email": row[1], "active": row[2], "created_at": row[3]}

    def update(self, recipient_id: int, active: bool) -> dict | None:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE global_notification_recipients
                    SET active = %s
                    WHERE id = %s
                    RETURNING id, email, active, created_at
                    """,
                    (active, recipient_id),
                )
                row = cur.fetchone()

        if row is None:
            return None
        return {"id": row[0], "email": row[1], "active": row[2], "created_at": row[3]}

    def delete(self, recipient_id: int) -> int | None:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM global_notification_recipients WHERE id = %s RETURNING id",
                    (recipient_id,),
                )
                row = cur.fetchone()

        return row[0] if row else None

    def email_exists(self, email: str) -> bool:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM global_notification_recipients WHERE email = %s",
                    (email,),
                )
                return cur.fetchone() is not None

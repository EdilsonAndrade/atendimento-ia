"""Adapter Postgres do Protocol ConversationMessageRepository — Infrastructure layer.

A tabela `conversation_messages` é criada pela migration
`0009_conversation_followup` (migrations/versions/).
"""
from datetime import datetime

import psycopg

from infrastructure.connection import DB_URI
from modules.conversation_history.domain.conversation_message import ConversationMessage


class PostgresConversationMessageRepository:
    def save_turn(self, human: ConversationMessage, ai: ConversationMessage) -> None:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO conversation_messages
                        (tenant_id, base_thread_id, active_thread_id, role, content)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (m.tenant_id, m.base_thread_id, m.active_thread_id, m.role, m.content)
                        for m in (human, ai)
                    ],
                )

    def list_by_thread(
        self,
        tenant_id: str,
        base_thread_id: str,
        limit: int = 200,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        query = """
            SELECT tenant_id, base_thread_id, active_thread_id, role, content, created_at
            FROM conversation_messages
            WHERE tenant_id = %s AND base_thread_id = %s
        """
        params: list = [tenant_id, base_thread_id]
        if before is not None:
            query += " AND created_at < %s"
            params.append(before)
        query += " ORDER BY created_at ASC LIMIT %s"
        params.append(limit)

        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        return [
            ConversationMessage(
                tenant_id=row[0],
                base_thread_id=row[1],
                active_thread_id=row[2],
                role=row[3],
                content=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def purge_older_than(self, tenant_id: str, retention_days: int) -> int:
        with psycopg.connect(DB_URI, autocommit=True, prepare_threshold=0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM conversation_messages
                    WHERE tenant_id = %s AND created_at < NOW() - (%s * INTERVAL '1 day')
                    """,
                    (tenant_id, retention_days),
                )
                return cur.rowcount

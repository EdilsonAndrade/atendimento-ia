from typing import Optional

from psycopg.rows import dict_row

from infrastructure.connection import get_db_connection
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS tenant_knowledge_base (
    tenant_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresKnowledgeBaseRepository:
    """Implementa KnowledgeBaseRepositoryPort sobre a tabela tenant_knowledge_base.

    A tabela é criada de forma idempotente (CREATE TABLE IF NOT EXISTS) na inicialização,
    seguindo o mesmo padrão já usado por modules/ia/thread_session.py para chat_thread_sessions
    — este projeto não tem um framework de migrations.
    """

    def __init__(self, get_connection_func=get_db_connection):
        self.get_connection = get_connection_func
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_TABLE_DDL)

    def get(self, tenant_id: str) -> Optional[KnowledgeBaseDocument]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT tenant_id, content, updated_at FROM tenant_knowledge_base WHERE tenant_id = %s",
                    (tenant_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return KnowledgeBaseDocument(**row)

    def upsert(self, tenant_id: str, content: str) -> KnowledgeBaseDocument:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_knowledge_base (tenant_id, content, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (tenant_id)
                    DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                    RETURNING tenant_id, content, updated_at
                    """,
                    (tenant_id, content),
                )
                row = cur.fetchone()
        return KnowledgeBaseDocument(**row)

    def delete(self, tenant_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tenant_knowledge_base WHERE tenant_id = %s", (tenant_id,))
                return cur.rowcount > 0

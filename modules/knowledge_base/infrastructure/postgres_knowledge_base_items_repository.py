from typing import List, Optional

from psycopg.rows import dict_row

from infrastructure.connection import get_db_connection
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem


class PostgresKnowledgeBaseItemsRepository:
    """Implementa KnowledgeBaseItemsRepositoryPort sobre a tabela tenant_knowledge_base_items
    (EDI-39). Toda operação de item único filtra por (tenant_id, id) juntos, para nunca
    vazar ou afetar um item de outro tenant (Constituição, Princípio I)."""

    def __init__(self, get_connection_func=get_db_connection):
        self.get_connection = get_connection_func

    def list_by_tenant(self, tenant_id: str) -> List[KnowledgeBaseItem]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                    FROM tenant_knowledge_base_items
                    WHERE tenant_id = %s
                    ORDER BY created_at
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return [KnowledgeBaseItem(**row) for row in rows]

    def get(self, tenant_id: str, item_id: str) -> Optional[KnowledgeBaseItem]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                    FROM tenant_knowledge_base_items
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (tenant_id, item_id),
                )
                row = cur.fetchone()
        return KnowledgeBaseItem(**row) if row else None

    def find_by_filename(self, tenant_id: str, filename: str) -> Optional[KnowledgeBaseItem]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                    FROM tenant_knowledge_base_items
                    WHERE tenant_id = %s AND filename = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (tenant_id, filename),
                )
                row = cur.fetchone()
        return KnowledgeBaseItem(**row) if row else None

    def create(
        self, tenant_id: str, source_type: str, filename: Optional[str], content: str
    ) -> KnowledgeBaseItem:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_knowledge_base_items (tenant_id, source_type, filename, content)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                    """,
                    (tenant_id, source_type, filename, content),
                )
                row = cur.fetchone()
        return KnowledgeBaseItem(**row)

    def update_content(
        self, tenant_id: str, item_id: str, content: str, filename: Optional[str] = None
    ) -> Optional[KnowledgeBaseItem]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if filename is not None:
                    cur.execute(
                        """
                        UPDATE tenant_knowledge_base_items
                        SET content = %s, filename = %s, updated_at = NOW()
                        WHERE tenant_id = %s AND id = %s
                        RETURNING id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                        """,
                        (content, filename, tenant_id, item_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE tenant_knowledge_base_items
                        SET content = %s, updated_at = NOW()
                        WHERE tenant_id = %s AND id = %s
                        RETURNING id::text AS id, tenant_id, source_type, filename, content, created_at, updated_at
                        """,
                        (content, tenant_id, item_id),
                    )
                row = cur.fetchone()
        return KnowledgeBaseItem(**row) if row else None

    def delete(self, tenant_id: str, item_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tenant_knowledge_base_items WHERE tenant_id = %s AND id = %s",
                    (tenant_id, item_id),
                )
                return cur.rowcount > 0

    def delete_all_by_tenant(self, tenant_id: str) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tenant_knowledge_base_items WHERE tenant_id = %s",
                    (tenant_id,),
                )

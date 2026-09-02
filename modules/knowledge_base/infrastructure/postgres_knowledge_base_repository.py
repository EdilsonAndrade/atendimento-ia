from typing import Optional

from psycopg.rows import dict_row

from infrastructure.connection import get_db_connection
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument

CONTENT_SEPARATOR = "\n\n"


class PostgresKnowledgeBaseRepository:
    """Implementa KnowledgeBaseRepositoryPort sobre a tabela tenant_knowledge_base_items
    (EDI-39) — o `content` agregado é a concatenação dos itens do tenant, em ordem de
    criação. Mantido para não quebrar o contrato de `GET/PUT/DELETE
    /tenants/{tenant_id}/knowledge-base` (feature 001): um `PUT` aqui equivale a
    substituir todos os itens do tenant por um único item de texto.

    A tabela é criada pelas migrations em `migrations/` (EDI-37/EDI-39) — este
    repositório assume que o schema já está correto quando a aplicação sobe.
    """

    def __init__(self, get_connection_func=get_db_connection):
        self.get_connection = get_connection_func

    def get(self, tenant_id: str) -> Optional[KnowledgeBaseDocument]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT content, updated_at FROM tenant_knowledge_base_items
                    WHERE tenant_id = %s
                    ORDER BY created_at
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()

        if not rows:
            return None

        content = CONTENT_SEPARATOR.join(row["content"] for row in rows)
        updated_at = max(row["updated_at"] for row in rows)
        return KnowledgeBaseDocument(tenant_id=tenant_id, content=content, updated_at=updated_at)

    def upsert(self, tenant_id: str, content: str) -> KnowledgeBaseDocument:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "DELETE FROM tenant_knowledge_base_items WHERE tenant_id = %s",
                    (tenant_id,),
                )
                cur.execute(
                    """
                    INSERT INTO tenant_knowledge_base_items (tenant_id, source_type, filename, content)
                    VALUES (%s, 'texto', NULL, %s)
                    RETURNING updated_at
                    """,
                    (tenant_id, content),
                )
                row = cur.fetchone()

        return KnowledgeBaseDocument(tenant_id=tenant_id, content=content, updated_at=row["updated_at"])

    def delete(self, tenant_id: str) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tenant_knowledge_base_items WHERE tenant_id = %s",
                    (tenant_id,),
                )
                return cur.rowcount > 0

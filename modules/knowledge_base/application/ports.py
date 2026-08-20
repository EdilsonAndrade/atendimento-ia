from typing import Optional, Protocol

from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument


class KnowledgeBaseRepositoryPort(Protocol):
    """Porta para persistência do texto (fonte da verdade) da base de conhecimento."""

    def get(self, tenant_id: str) -> Optional[KnowledgeBaseDocument]:
        ...

    def upsert(self, tenant_id: str, content: str) -> KnowledgeBaseDocument:
        ...

    def delete(self, tenant_id: str) -> bool:
        """Retorna True se havia um documento e foi removido, False se não havia nada."""
        ...


class VectorStorePort(Protocol):
    """Porta para o índice vetorial derivado (RAG) — sempre reconstruído a partir do texto."""

    def reindex(self, tenant_id: str, content: str) -> None:
        """Remove os vetores existentes do tenant e indexa o novo conteúdo (substitui, não acumula)."""
        ...

    def delete(self, tenant_id: str) -> None:
        """Remove todos os vetores do tenant."""
        ...

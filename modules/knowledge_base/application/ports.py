from typing import BinaryIO, List, Optional, Protocol

from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem


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

    def reindex_item(self, tenant_id: str, item_id: str, content: str) -> None:
        """Remove só os vetores daquele item e indexa o novo conteúdo — não afeta outros itens."""
        ...

    def delete_item(self, tenant_id: str, item_id: str) -> None:
        """Remove só os vetores daquele item."""
        ...


class KnowledgeBaseItemsRepositoryPort(Protocol):
    """Porta para persistência dos itens individuais (arquivo ou texto) da base de conhecimento."""

    def list_by_tenant(self, tenant_id: str) -> List[KnowledgeBaseItem]:
        ...

    def get(self, tenant_id: str, item_id: str) -> Optional[KnowledgeBaseItem]:
        ...

    def find_by_filename(self, tenant_id: str, filename: str) -> Optional[KnowledgeBaseItem]:
        ...

    def create(
        self, tenant_id: str, source_type: str, filename: Optional[str], content: str
    ) -> KnowledgeBaseItem:
        ...

    def update_content(
        self, tenant_id: str, item_id: str, content: str, filename: Optional[str] = None
    ) -> Optional[KnowledgeBaseItem]:
        """Atualiza o conteúdo (e opcionalmente o filename) de um item existente do tenant.
        Retorna None se o item não existir para aquele tenant."""
        ...

    def delete(self, tenant_id: str, item_id: str) -> bool:
        ...

    def delete_all_by_tenant(self, tenant_id: str) -> None:
        ...


class FileTextExtractorPort(Protocol):
    """Porta para extração de texto de um arquivo enviado (PDF, XLS, XLSX ou CSV)."""

    def extract(self, file: BinaryIO, filename: str) -> str:
        """Extrai e retorna o texto de `file`, decidindo o parser pela extensão de `filename`.
        Levanta UnsupportedFileTypeError se a extensão não for suportada."""
        ...

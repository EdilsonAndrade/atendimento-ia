from typing import Optional

from modules.knowledge_base.application.ports import KnowledgeBaseRepositoryPort, VectorStorePort
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument


class GetTenantKnowledgeBase:
    def __init__(self, repository: KnowledgeBaseRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str) -> Optional[KnowledgeBaseDocument]:
        return self.repository.get(tenant_id)


class UpsertTenantKnowledgeBase:
    def __init__(self, repository: KnowledgeBaseRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str, content: str) -> KnowledgeBaseDocument:
        # Valida antes de tocar o port — conteúdo vazio nunca chega ao repositório.
        KnowledgeBaseDocument.validate_content(content)
        return self.repository.upsert(tenant_id, content)


class DeleteTenantKnowledgeBase:
    def __init__(self, repository: KnowledgeBaseRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str) -> bool:
        """Retorna True se havia base de conhecimento e foi removida, False se não havia nada."""
        return self.repository.delete(tenant_id)


class ReindexTenantKnowledgeBase:
    """Disparado apenas em background (Constituição, Princípio V) — nunca no caminho síncrono
    da request, já que envolve geração de embeddings."""

    def __init__(self, vector_store: VectorStorePort):
        self.vector_store = vector_store

    def execute(self, tenant_id: str, content: str) -> None:
        self.vector_store.reindex(tenant_id, content)

    def execute_delete(self, tenant_id: str) -> None:
        self.vector_store.delete(tenant_id)

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from modules.knowledge_base.application.ports import (
    KnowledgeBaseItemsRepositoryPort,
    KnowledgeBaseRepositoryPort,
    VectorStorePort,
)
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem

IngestMode = Literal["append", "replace"]
DuplicateAction = Literal["replace", "keep_both"]


class ItemNotFoundError(LookupError):
    """Levantado quando um item não existe para o tenant informado."""


class DuplicateConflictError(ValueError):
    """Levantado quando há arquivos com nome já existente e sem resolução informada."""

    def __init__(self, conflicts: List[dict]):
        self.conflicts = conflicts
        super().__init__(f"{len(conflicts)} arquivo(s) já existem na base de conhecimento do tenant.")


@dataclass(frozen=True)
class NewItemInput:
    """Um novo item a ser ingerido: já com o texto extraído (arquivo) ou colado (texto)."""

    source_type: Literal["file", "texto"]
    content: str
    filename: Optional[str] = None


@dataclass(frozen=True)
class DuplicateResolution:
    filename: str
    action: DuplicateAction
    existing_item_id: Optional[str] = None


@dataclass(frozen=True)
class IngestResult:
    created: List[KnowledgeBaseItem] = field(default_factory=list)
    replaced: List[KnowledgeBaseItem] = field(default_factory=list)


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


class ReindexTenantKnowledgeBaseItem:
    """Reindexação escopada a um único item — nunca afeta os vetores dos demais itens do
    mesmo tenant. Disparado apenas em background (Princípio V)."""

    def __init__(self, vector_store: VectorStorePort):
        self.vector_store = vector_store

    def execute(self, tenant_id: str, item_id: str, content: str) -> None:
        self.vector_store.reindex_item(tenant_id, item_id, content)

    def execute_delete(self, tenant_id: str, item_id: str) -> None:
        self.vector_store.delete_item(tenant_id, item_id)


class ListTenantKnowledgeBaseItems:
    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str) -> List[KnowledgeBaseItem]:
        return self.repository.list_by_tenant(tenant_id)


class GetTenantKnowledgeBaseItem:
    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str, item_id: str) -> Optional[KnowledgeBaseItem]:
        return self.repository.get(tenant_id, item_id)


class IngestKnowledgeBaseItems:
    """Cria itens novos a partir de arquivos/textos já extraídos, no modo `append` ou `replace`.

    `append`: itens de arquivo cujo `filename` já existe no tenant e que não tenham uma
    `DuplicateResolution` correspondente fazem a operação inteira falhar com
    `DuplicateConflictError` (nada é persistido) — o chamador deve reenviar informando,
    por arquivo, se quer substituir o item existente ou manter ambos (duplicado).

    `replace`: apaga todos os itens existentes do tenant antes de criar os novos.
    """

    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(
        self,
        tenant_id: str,
        new_items: List[NewItemInput],
        mode: IngestMode,
        duplicate_resolutions: Optional[List[DuplicateResolution]] = None,
    ) -> IngestResult:
        for new_item in new_items:
            KnowledgeBaseItem.validate_content(new_item.content)

        if mode == "replace":
            self.repository.delete_all_by_tenant(tenant_id)
            created = [
                self.repository.create(tenant_id, item.source_type, item.filename, item.content)
                for item in new_items
            ]
            return IngestResult(created=created, replaced=[])

        return self._execute_append(tenant_id, new_items, duplicate_resolutions or [])

    def _execute_append(
        self,
        tenant_id: str,
        new_items: List[NewItemInput],
        duplicate_resolutions: List[DuplicateResolution],
    ) -> IngestResult:
        resolutions_by_filename = {resolution.filename: resolution for resolution in duplicate_resolutions}

        # Nomes repetidos DENTRO do próprio lote (2 arquivos novos com o mesmo filename)
        # também contam como conflito — nunca duplicar silenciosamente sem confirmação.
        seen_in_batch = set()
        conflicts = []
        for item in new_items:
            if not item.filename:
                continue
            existing = self.repository.find_by_filename(tenant_id, item.filename)
            is_conflict = existing is not None or item.filename in seen_in_batch
            if is_conflict and item.filename not in resolutions_by_filename:
                conflicts.append(
                    {"filename": item.filename, "existing_item_id": existing.id if existing else None}
                )
            seen_in_batch.add(item.filename)

        if conflicts:
            raise DuplicateConflictError(conflicts)

        created: List[KnowledgeBaseItem] = []
        replaced: List[KnowledgeBaseItem] = []
        for item in new_items:
            existing = self.repository.find_by_filename(tenant_id, item.filename) if item.filename else None
            resolution = resolutions_by_filename.get(item.filename) if item.filename else None

            if existing is not None and resolution is not None and resolution.action == "replace":
                updated = self.repository.update_content(
                    tenant_id, existing.id, item.content, filename=item.filename
                )
                replaced.append(updated)
                continue

            created.append(self.repository.create(tenant_id, item.source_type, item.filename, item.content))

        return IngestResult(created=created, replaced=replaced)


class UpdateTenantKnowledgeBaseItemContent:
    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str, item_id: str, content: str) -> KnowledgeBaseItem:
        KnowledgeBaseItem.validate_content(content)
        updated = self.repository.update_content(tenant_id, item_id, content)
        if updated is None:
            raise ItemNotFoundError(f"Item {item_id} não encontrado para o tenant {tenant_id}.")
        return updated


class ReplaceTenantKnowledgeBaseItemFile:
    """Recebe o texto já extraído pela Interface (mesma divisão de responsabilidade do
    `IngestKnowledgeBaseItems`) — a Application nunca toca pypdf/pandas diretamente."""

    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str, item_id: str, filename: str, content: str) -> KnowledgeBaseItem:
        KnowledgeBaseItem.validate_content(content)
        updated = self.repository.update_content(tenant_id, item_id, content, filename=filename)
        if updated is None:
            raise ItemNotFoundError(f"Item {item_id} não encontrado para o tenant {tenant_id}.")
        return updated


class DeleteTenantKnowledgeBaseItem:
    def __init__(self, repository: KnowledgeBaseItemsRepositoryPort):
        self.repository = repository

    def execute(self, tenant_id: str, item_id: str) -> bool:
        return self.repository.delete(tenant_id, item_id)

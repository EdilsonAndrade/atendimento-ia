import itertools
from datetime import datetime, timezone

import pytest

from modules.knowledge_base.application.use_cases import (
    DeleteTenantKnowledgeBaseItem,
    ItemNotFoundError,
    ReplaceTenantKnowledgeBaseItemFile,
    UpdateTenantKnowledgeBaseItemContent,
)
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem


class FakeKnowledgeBaseItemsRepository:
    def __init__(self):
        self.items = {}
        self._counter = itertools.count(1)

    def list_by_tenant(self, tenant_id):
        return [item for item in self.items.values() if item.tenant_id == tenant_id]

    def get(self, tenant_id, item_id):
        item = self.items.get(item_id)
        return item if item and item.tenant_id == tenant_id else None

    def find_by_filename(self, tenant_id, filename):
        return None

    def create(self, tenant_id, source_type, filename, content):
        item_id = str(next(self._counter))
        now = datetime.now(timezone.utc)
        item = KnowledgeBaseItem(
            id=item_id,
            tenant_id=tenant_id,
            source_type=source_type,
            filename=filename,
            content=content,
            created_at=now,
            updated_at=now,
        )
        self.items[item_id] = item
        return item

    def update_content(self, tenant_id, item_id, content, filename=None):
        existing = self.get(tenant_id, item_id)
        if existing is None:
            return None
        updated = KnowledgeBaseItem(
            id=existing.id,
            tenant_id=existing.tenant_id,
            source_type=existing.source_type,
            filename=filename if filename is not None else existing.filename,
            content=content,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.items[item_id] = updated
        return updated

    def delete(self, tenant_id, item_id):
        existing = self.get(tenant_id, item_id)
        if existing is None:
            return False
        del self.items[item_id]
        return True

    def delete_all_by_tenant(self, tenant_id):
        for item_id in [i for i, item in self.items.items() if item.tenant_id == tenant_id]:
            del self.items[item_id]


def test_update_content_edits_item_and_preserves_id():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("1234", "texto", None, "texto original")

    updated = UpdateTenantKnowledgeBaseItemContent(repo).execute("1234", item.id, "texto editado")

    assert updated.id == item.id
    assert updated.content == "texto editado"
    assert repo.get("1234", item.id).content == "texto editado"


def test_update_content_rejects_empty_content():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("1234", "texto", None, "texto original")

    with pytest.raises(ValueError):
        UpdateTenantKnowledgeBaseItemContent(repo).execute("1234", item.id, "   ")

    assert repo.get("1234", item.id).content == "texto original"


def test_update_content_raises_not_found_for_unknown_item():
    repo = FakeKnowledgeBaseItemsRepository()

    with pytest.raises(ItemNotFoundError):
        UpdateTenantKnowledgeBaseItemContent(repo).execute("1234", "inexistente", "novo texto")


def test_update_content_does_not_affect_item_from_another_tenant():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("5678", "texto", None, "conteudo do outro tenant")

    with pytest.raises(ItemNotFoundError):
        UpdateTenantKnowledgeBaseItemContent(repo).execute("1234", item.id, "tentativa de invasao")

    assert repo.get("5678", item.id).content == "conteudo do outro tenant"


def test_replace_item_file_updates_content_and_filename_keeping_id():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("1234", "file", "precos_v1.xlsx", "conteudo antigo")

    updated = ReplaceTenantKnowledgeBaseItemFile(repo).execute(
        "1234", item.id, "precos_v2.xlsx", "conteudo novo extraido"
    )

    assert updated.id == item.id
    assert updated.filename == "precos_v2.xlsx"
    assert updated.content == "conteudo novo extraido"


def test_replace_item_file_raises_not_found_for_unknown_item():
    repo = FakeKnowledgeBaseItemsRepository()

    with pytest.raises(ItemNotFoundError):
        ReplaceTenantKnowledgeBaseItemFile(repo).execute("1234", "inexistente", "novo.csv", "conteudo")


def test_replace_item_file_rejects_empty_extracted_content():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("1234", "file", "precos_v1.xlsx", "conteudo antigo")

    with pytest.raises(ValueError):
        ReplaceTenantKnowledgeBaseItemFile(repo).execute("1234", item.id, "precos_v2.xlsx", "   ")

    assert repo.get("1234", item.id).content == "conteudo antigo"


def test_delete_item_removes_only_the_target_item():
    repo = FakeKnowledgeBaseItemsRepository()
    keep = repo.create("1234", "texto", None, "mantem")
    remove = repo.create("1234", "texto", None, "remove")

    deleted = DeleteTenantKnowledgeBaseItem(repo).execute("1234", remove.id)

    assert deleted is True
    remaining = repo.list_by_tenant("1234")
    assert len(remaining) == 1
    assert remaining[0].id == keep.id


def test_delete_item_returns_false_when_item_does_not_belong_to_tenant():
    repo = FakeKnowledgeBaseItemsRepository()
    item = repo.create("5678", "texto", None, "conteudo do outro tenant")

    deleted = DeleteTenantKnowledgeBaseItem(repo).execute("1234", item.id)

    assert deleted is False
    assert repo.get("5678", item.id) is not None

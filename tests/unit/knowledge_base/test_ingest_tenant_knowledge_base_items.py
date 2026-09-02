import itertools
from datetime import datetime, timezone

import pytest

from modules.knowledge_base.application.use_cases import (
    DuplicateConflictError,
    DuplicateResolution,
    IngestKnowledgeBaseItems,
    NewItemInput,
)
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem


class FakeKnowledgeBaseItemsRepository:
    def __init__(self):
        self.items = {}
        self._counter = itertools.count(1)

    def list_by_tenant(self, tenant_id):
        return sorted(
            (item for item in self.items.values() if item.tenant_id == tenant_id),
            key=lambda item: item.created_at,
        )

    def get(self, tenant_id, item_id):
        item = self.items.get(item_id)
        return item if item and item.tenant_id == tenant_id else None

    def find_by_filename(self, tenant_id, filename):
        matches = [
            item
            for item in self.items.values()
            if item.tenant_id == tenant_id and item.filename == filename
        ]
        return matches[-1] if matches else None

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


def test_append_creates_one_item_per_file_and_text():
    repo = FakeKnowledgeBaseItemsRepository()

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234",
        [
            NewItemInput(source_type="file", content="conteudo do pdf", filename="regras.pdf"),
            NewItemInput(source_type="texto", content="texto colado direto"),
        ],
        mode="append",
    )

    assert len(result.created) == 2
    assert result.replaced == []
    assert len(repo.list_by_tenant("1234")) == 2


def test_append_preserves_items_from_other_tenants():
    repo = FakeKnowledgeBaseItemsRepository()
    repo.create("5678", "texto", None, "conteudo do outro tenant")

    IngestKnowledgeBaseItems(repo).execute(
        "1234", [NewItemInput(source_type="texto", content="conteudo novo")], mode="append"
    )

    assert len(repo.list_by_tenant("5678")) == 1
    assert len(repo.list_by_tenant("1234")) == 1


def test_append_raises_conflict_for_duplicate_filename_without_resolution():
    repo = FakeKnowledgeBaseItemsRepository()
    existing = repo.create("1234", "file", "precos.xlsx", "conteudo v1")

    with pytest.raises(DuplicateConflictError) as exc_info:
        IngestKnowledgeBaseItems(repo).execute(
            "1234",
            [NewItemInput(source_type="file", content="conteudo v2", filename="precos.xlsx")],
            mode="append",
        )

    assert exc_info.value.conflicts == [{"filename": "precos.xlsx", "existing_item_id": existing.id}]
    # nada foi persistido — o item original continua intacto, nenhum novo foi criado
    assert len(repo.list_by_tenant("1234")) == 1
    assert repo.list_by_tenant("1234")[0].content == "conteudo v1"


def test_append_with_replace_resolution_updates_existing_item_keeping_its_id():
    repo = FakeKnowledgeBaseItemsRepository()
    existing = repo.create("1234", "file", "precos.xlsx", "conteudo v1")

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234",
        [NewItemInput(source_type="file", content="conteudo v2", filename="precos.xlsx")],
        mode="append",
        duplicate_resolutions=[
            DuplicateResolution(filename="precos.xlsx", action="replace", existing_item_id=existing.id)
        ],
    )

    assert result.created == []
    assert len(result.replaced) == 1
    assert result.replaced[0].id == existing.id
    assert result.replaced[0].content == "conteudo v2"
    assert len(repo.list_by_tenant("1234")) == 1


def test_append_with_keep_both_resolution_creates_duplicate_item():
    repo = FakeKnowledgeBaseItemsRepository()
    existing = repo.create("1234", "file", "precos.xlsx", "conteudo v1")

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234",
        [NewItemInput(source_type="file", content="conteudo v2", filename="precos.xlsx")],
        mode="append",
        duplicate_resolutions=[DuplicateResolution(filename="precos.xlsx", action="keep_both")],
    )

    assert result.replaced == []
    assert len(result.created) == 1
    assert result.created[0].id != existing.id
    items = repo.list_by_tenant("1234")
    assert len(items) == 2
    assert {item.filename for item in items} == {"precos.xlsx"}


def test_append_never_deduplicates_pasted_text_items():
    repo = FakeKnowledgeBaseItemsRepository()
    IngestKnowledgeBaseItems(repo).execute(
        "1234", [NewItemInput(source_type="texto", content="mesmo texto")], mode="append"
    )

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234", [NewItemInput(source_type="texto", content="mesmo texto")], mode="append"
    )

    assert len(result.created) == 1
    assert len(repo.list_by_tenant("1234")) == 2


def test_replace_mode_deletes_previous_items_before_creating_new_ones():
    repo = FakeKnowledgeBaseItemsRepository()
    repo.create("1234", "texto", None, "conteudo antigo")

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234", [NewItemInput(source_type="file", content="conteudo novo", filename="a.csv")], mode="replace"
    )

    items = repo.list_by_tenant("1234")
    assert len(items) == 1
    assert items[0].content == "conteudo novo"
    assert len(result.created) == 1


def test_replace_mode_never_raises_conflict_even_with_repeated_filename():
    repo = FakeKnowledgeBaseItemsRepository()
    repo.create("1234", "file", "a.csv", "conteudo antigo")

    result = IngestKnowledgeBaseItems(repo).execute(
        "1234", [NewItemInput(source_type="file", content="conteudo novo", filename="a.csv")], mode="replace"
    )

    assert len(result.created) == 1
    assert len(repo.list_by_tenant("1234")) == 1


def test_ingest_rejects_empty_content_before_persisting_anything():
    repo = FakeKnowledgeBaseItemsRepository()
    repo.create("1234", "texto", None, "conteudo existente")

    with pytest.raises(ValueError):
        IngestKnowledgeBaseItems(repo).execute(
            "1234", [NewItemInput(source_type="texto", content="   ")], mode="append"
        )

    assert len(repo.list_by_tenant("1234")) == 1

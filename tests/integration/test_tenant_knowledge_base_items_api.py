import itertools
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import knowledge_base as knowledge_base_module
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem, UnsupportedFileTypeError
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self, tenants):
        self._tenants = tenants

    def get_tenant(self, tenant_id):
        return self._tenants.get(tenant_id)


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


class FakeVectorStore:
    def __init__(self):
        self.reindex_calls = []
        self.delete_calls = []
        self.reindex_item_calls = []
        self.delete_item_calls = []

    def reindex(self, tenant_id, content):
        self.reindex_calls.append((tenant_id, content))

    def delete(self, tenant_id):
        self.delete_calls.append(tenant_id)

    def reindex_item(self, tenant_id, item_id, content):
        self.reindex_item_calls.append((tenant_id, item_id, content))

    def delete_item(self, tenant_id, item_id):
        self.delete_item_calls.append((tenant_id, item_id))


class FakeFileTextExtractor:
    """Nunca toca pypdf/pandas de verdade — a extração real já é coberta por
    tests/unit/test_file_text_extractor_adapter.py; aqui só validamos a integração
    do endpoint com a porta (sucesso e extensão não suportada)."""

    def extract(self, file, filename):
        if filename.lower().endswith(".docx"):
            raise UnsupportedFileTypeError(f"Extensão de arquivo não suportada em '{filename}'.")
        return f"conteudo extraido de {filename}"


def make_client(tenants, items_repository=None, vector_store=None, extractor=None):
    items_repository = items_repository if items_repository is not None else FakeKnowledgeBaseItemsRepository()
    vector_store = vector_store if vector_store is not None else FakeVectorStore()
    extractor = extractor if extractor is not None else FakeFileTextExtractor()

    app = FastAPI()
    app.include_router(knowledge_base_module.router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: FakeTenantService(tenants)
    app.dependency_overrides[knowledge_base_module.get_knowledge_base_items_repository] = lambda: items_repository
    app.dependency_overrides[knowledge_base_module.get_vector_store] = lambda: vector_store
    app.dependency_overrides[knowledge_base_module.get_file_text_extractor] = lambda: extractor

    return TestClient(app), items_repository, vector_store


def test_list_items_is_empty_for_tenant_without_ingestion():
    client, _, _ = make_client(tenants={"1234": {"id": "1234"}})

    response = client.get("/api/v1/tenants/1234/knowledge-base/items")

    assert response.status_code == 200
    assert response.json() == []


def test_list_items_returns_404_for_unknown_tenant():
    client, _, _ = make_client(tenants={})

    response = client.get("/api/v1/tenants/9999/knowledge-base/items")

    assert response.status_code == 404


def test_ingest_append_creates_items_from_files_and_texts_and_schedules_reindex():
    client, repository, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    response = client.post(
        "/api/v1/tenants/1234/knowledge-base/items",
        data={"mode": "append", "texts": ["Regra colada direto"]},
        files=[("files", ("precos.csv", b"servico,preco\nCorte,30\n", "text/csv"))],
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["created"]) == 2
    assert body["replaced"] == []
    items = repository.list_by_tenant("1234")
    assert len(items) == 2
    assert {item.filename for item in items} == {None, "precos.csv"}
    assert len(vector_store.reindex_item_calls) == 2


def test_ingest_requires_at_least_one_file_or_text():
    client, _, _ = make_client(tenants={"1234": {"id": "1234"}})

    response = client.post("/api/v1/tenants/1234/knowledge-base/items", data={"mode": "append"})

    assert response.status_code == 422


def test_ingest_rejects_unsupported_file_extension():
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}})

    response = client.post(
        "/api/v1/tenants/1234/knowledge-base/items",
        data={"mode": "append"},
        files=[("files", ("documento.docx", b"conteudo", "application/octet-stream"))],
    )

    assert response.status_code == 422
    assert repository.list_by_tenant("1234") == []


def test_ingest_replace_mode_deletes_previous_items():
    repository = FakeKnowledgeBaseItemsRepository()
    repository.create("1234", "texto", None, "conteudo antigo")
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}}, items_repository=repository)

    response = client.post(
        "/api/v1/tenants/1234/knowledge-base/items",
        data={"mode": "replace", "texts": ["conteudo novo"]},
    )

    assert response.status_code == 201
    items = repository.list_by_tenant("1234")
    assert len(items) == 1
    assert items[0].content == "conteudo novo"


def test_ingest_append_with_duplicate_filename_returns_409_without_persisting():
    repository = FakeKnowledgeBaseItemsRepository()
    existing = repository.create("1234", "file", "precos.csv", "conteudo v1")
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}}, items_repository=repository)

    response = client.post(
        "/api/v1/tenants/1234/knowledge-base/items",
        data={"mode": "append"},
        files=[("files", ("precos.csv", b"novo,conteudo", "text/csv"))],
    )

    assert response.status_code == 409
    body = response.json()
    assert body["conflicts"] == [{"filename": "precos.csv", "existing_item_id": existing.id}]
    assert repository.get("1234", existing.id).content == "conteudo v1"
    assert len(repository.list_by_tenant("1234")) == 1


def test_ingest_append_with_duplicate_resolution_replace_updates_existing_item():
    repository = FakeKnowledgeBaseItemsRepository()
    existing = repository.create("1234", "file", "precos.csv", "conteudo v1")
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}}, items_repository=repository)

    response = client.post(
        "/api/v1/tenants/1234/knowledge-base/items",
        data={
            "mode": "append",
            "duplicate_resolutions": (
                f'[{{"filename": "precos.csv", "action": "replace", '
                f'"existing_item_id": "{existing.id}"}}]'
            ),
        },
        files=[("files", ("precos.csv", b"novo,conteudo", "text/csv"))],
    )

    assert response.status_code == 201
    assert response.json()["created"] == []
    assert len(response.json()["replaced"]) == 1
    assert repository.get("1234", existing.id).content == "conteudo extraido de precos.csv"
    assert len(repository.list_by_tenant("1234")) == 1


def test_get_item_detail_returns_full_content():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("1234", "texto", None, "x" * 5000)
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}}, items_repository=repository)

    response = client.get(f"/api/v1/tenants/1234/knowledge-base/items/{item.id}")

    assert response.status_code == 200
    assert len(response.json()["content"]) == 5000


def test_list_items_preview_is_limited_to_1000_characters():
    repository = FakeKnowledgeBaseItemsRepository()
    repository.create("1234", "texto", None, "x" * 5000)
    client, repository, _ = make_client(tenants={"1234": {"id": "1234"}}, items_repository=repository)

    response = client.get("/api/v1/tenants/1234/knowledge-base/items")

    body = response.json()
    assert len(body[0]["content_preview"]) == 1000
    assert body[0]["content_length"] == 5000


def test_get_item_detail_returns_404_when_item_belongs_to_another_tenant():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("5678", "texto", None, "conteudo do outro tenant")
    client, repository, _ = make_client(
        tenants={"1234": {"id": "1234"}, "5678": {"id": "5678"}}, items_repository=repository
    )

    response = client.get(f"/api/v1/tenants/1234/knowledge-base/items/{item.id}")

    assert response.status_code == 404


def test_update_item_content_edits_and_schedules_reindex():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("1234", "texto", None, "texto original")
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, items_repository=repository
    )

    response = client.put(
        f"/api/v1/tenants/1234/knowledge-base/items/{item.id}", json={"content": "texto editado"}
    )

    assert response.status_code == 200
    assert response.json()["content"] == "texto editado"
    assert repository.get("1234", item.id).content == "texto editado"
    assert vector_store.reindex_item_calls == [("1234", item.id, "texto editado")]


def test_update_item_content_rejects_empty_content_with_422():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("1234", "texto", None, "texto original")
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, items_repository=repository
    )

    response = client.put(f"/api/v1/tenants/1234/knowledge-base/items/{item.id}", json={"content": ""})

    assert response.status_code == 422
    assert vector_store.reindex_item_calls == []


def test_replace_item_file_updates_filename_and_content_keeping_id():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("1234", "file", "precos_v1.csv", "conteudo antigo")
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, items_repository=repository
    )

    response = client.put(
        f"/api/v1/tenants/1234/knowledge-base/items/{item.id}/file",
        files={"file": ("precos_v2.csv", b"novo,conteudo", "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == item.id
    assert body["filename"] == "precos_v2.csv"
    assert body["content"] == "conteudo extraido de precos_v2.csv"
    assert vector_store.reindex_item_calls == [("1234", item.id, "conteudo extraido de precos_v2.csv")]


def test_replace_item_file_returns_404_for_unknown_item():
    client, _, _ = make_client(tenants={"1234": {"id": "1234"}})

    response = client.put(
        "/api/v1/tenants/1234/knowledge-base/items/inexistente/file",
        files={"file": ("a.csv", b"conteudo", "text/csv")},
    )

    assert response.status_code == 404


def test_delete_item_removes_only_the_target_item():
    repository = FakeKnowledgeBaseItemsRepository()
    keep = repository.create("1234", "texto", None, "mantem")
    remove = repository.create("1234", "texto", None, "remove")
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, items_repository=repository
    )

    response = client.delete(f"/api/v1/tenants/1234/knowledge-base/items/{remove.id}")

    assert response.status_code == 204
    remaining = repository.list_by_tenant("1234")
    assert len(remaining) == 1
    assert remaining[0].id == keep.id
    assert vector_store.delete_item_calls == [("1234", remove.id)]


def test_delete_item_returns_404_when_item_belongs_to_another_tenant():
    repository = FakeKnowledgeBaseItemsRepository()
    item = repository.create("5678", "texto", None, "conteudo do outro tenant")
    client, repository, _ = make_client(
        tenants={"1234": {"id": "1234"}, "5678": {"id": "5678"}}, items_repository=repository
    )

    response = client.delete(f"/api/v1/tenants/1234/knowledge-base/items/{item.id}")

    assert response.status_code == 404
    assert repository.get("5678", item.id) is not None

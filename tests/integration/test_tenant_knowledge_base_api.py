from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import knowledge_base as knowledge_base_module
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self, tenants):
        self._tenants = tenants

    def get_tenant(self, tenant_id):
        return self._tenants.get(tenant_id)


class FakeKnowledgeBaseRepository:
    def __init__(self):
        self.store = {}

    def get(self, tenant_id):
        return self.store.get(tenant_id)

    def upsert(self, tenant_id, content):
        document = KnowledgeBaseDocument(
            tenant_id=tenant_id, content=content, updated_at=datetime.now(timezone.utc)
        )
        self.store[tenant_id] = document
        return document

    def delete(self, tenant_id):
        return self.store.pop(tenant_id, None) is not None


class FakeVectorStore:
    def __init__(self):
        self.reindex_calls = []
        self.delete_calls = []

    def reindex(self, tenant_id, content):
        self.reindex_calls.append((tenant_id, content))

    def delete(self, tenant_id):
        self.delete_calls.append(tenant_id)


def make_client(tenants, repository=None, vector_store=None):
    repository = repository if repository is not None else FakeKnowledgeBaseRepository()
    vector_store = vector_store if vector_store is not None else FakeVectorStore()

    app = FastAPI()
    app.include_router(knowledge_base_module.router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: FakeTenantService(tenants)
    app.dependency_overrides[knowledge_base_module.get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[knowledge_base_module.get_vector_store] = lambda: vector_store

    return TestClient(app), repository, vector_store


def test_get_returns_null_content_when_none_exists():
    client, _, _ = make_client(tenants={"1234": {"id": "1234"}})

    response = client.get("/api/v1/tenants/1234/knowledge-base")

    assert response.status_code == 200
    assert response.json() == {"tenant_id": "1234", "content": None, "updated_at": None}


def test_get_returns_404_for_unknown_tenant():
    client, _, _ = make_client(tenants={})

    response = client.get("/api/v1/tenants/9999/knowledge-base")

    assert response.status_code == 404


def test_put_creates_content_and_schedules_reindex():
    client, repository, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    response = client.put(
        "/api/v1/tenants/1234/knowledge-base",
        json={"content": "Regra: o barbeiro Lucas atende de terça a sábado."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Regra: o barbeiro Lucas atende de terça a sábado."
    assert repository.get("1234").content == body["content"]
    assert vector_store.reindex_calls == [("1234", "Regra: o barbeiro Lucas atende de terça a sábado.")]


def test_put_again_replaces_content_not_append():
    repository = FakeKnowledgeBaseRepository()
    vector_store = FakeVectorStore()
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, repository=repository, vector_store=vector_store
    )

    client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "versão 1"})
    response = client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "versão 2"})

    assert response.status_code == 200
    assert response.json()["content"] == "versão 2"
    assert repository.get("1234").content == "versão 2"
    # cada PUT dispara seu próprio reindex (delete-então-reindex no adapter real) — não acumula
    assert vector_store.reindex_calls == [("1234", "versão 1"), ("1234", "versão 2")]


def test_put_rejects_empty_content_with_422():
    client, repository, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    response = client.put("/api/v1/tenants/1234/knowledge-base", json={"content": ""})

    assert response.status_code == 422
    assert repository.get("1234") is None
    assert vector_store.reindex_calls == []


def test_put_rejects_whitespace_only_content_with_422():
    client, repository, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    response = client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "   "})

    assert response.status_code == 422
    assert vector_store.reindex_calls == []


def test_put_returns_404_for_unknown_tenant():
    client, _, _ = make_client(tenants={})

    response = client.put("/api/v1/tenants/9999/knowledge-base", json={"content": "algo"})

    assert response.status_code == 404


def test_put_for_tenant_without_prior_knowledge_base_creates_it():
    """US4: cadastrar nova base de conhecimento para um tenant que ainda não possui uma —
    mesmo endpoint PUT do US2 (upsert), sem código de produção adicional."""
    client, repository, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    before = client.get("/api/v1/tenants/1234/knowledge-base")
    assert before.json()["content"] is None

    response = client.put(
        "/api/v1/tenants/1234/knowledge-base",
        json={"content": "Primeira base de conhecimento deste tenant."},
    )
    after = client.get("/api/v1/tenants/1234/knowledge-base")

    assert response.status_code == 200
    assert after.json()["content"] == "Primeira base de conhecimento deste tenant."


def test_delete_removes_content_and_get_afterwards_shows_null():
    repository = FakeKnowledgeBaseRepository()
    vector_store = FakeVectorStore()
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}}, repository=repository, vector_store=vector_store
    )
    client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "conteudo a remover"})

    response = client.delete("/api/v1/tenants/1234/knowledge-base")

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "1234",
        "message": "Base de conhecimento removida com sucesso.",
    }
    assert vector_store.delete_calls == ["1234"]

    follow_up = client.get("/api/v1/tenants/1234/knowledge-base")
    assert follow_up.json() == {"tenant_id": "1234", "content": None, "updated_at": None}


def test_delete_returns_404_when_no_knowledge_base_to_delete():
    client, _, vector_store = make_client(tenants={"1234": {"id": "1234"}})

    response = client.delete("/api/v1/tenants/1234/knowledge-base")

    assert response.status_code == 404
    assert vector_store.delete_calls == []


def test_delete_returns_404_for_unknown_tenant():
    client, _, _ = make_client(tenants={})

    response = client.delete("/api/v1/tenants/9999/knowledge-base")

    assert response.status_code == 404


def test_delete_does_not_affect_other_tenant():
    repository = FakeKnowledgeBaseRepository()
    vector_store = FakeVectorStore()
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}, "5678": {"id": "5678"}},
        repository=repository,
        vector_store=vector_store,
    )
    client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "conteudo tenant 1234"})
    client.put("/api/v1/tenants/5678/knowledge-base", json={"content": "conteudo tenant 5678"})

    client.delete("/api/v1/tenants/1234/knowledge-base")

    assert vector_store.delete_calls == ["1234"]
    other_tenant = client.get("/api/v1/tenants/5678/knowledge-base")
    assert other_tenant.json()["content"] == "conteudo tenant 5678"


def test_put_isolation_between_two_tenants():
    """Princípio I da constituição: editar a base de um tenant nunca deve vazar para outro."""
    repository = FakeKnowledgeBaseRepository()
    vector_store = FakeVectorStore()
    client, repository, vector_store = make_client(
        tenants={"1234": {"id": "1234"}, "5678": {"id": "5678"}},
        repository=repository,
        vector_store=vector_store,
    )

    client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "regras do tenant 1234"})
    client.put("/api/v1/tenants/5678/knowledge-base", json={"content": "regras do tenant 5678"})
    client.put("/api/v1/tenants/1234/knowledge-base", json={"content": "regras atualizadas do tenant 1234"})

    tenant_1234 = client.get("/api/v1/tenants/1234/knowledge-base")
    tenant_5678 = client.get("/api/v1/tenants/5678/knowledge-base")

    assert tenant_1234.json()["content"] == "regras atualizadas do tenant 1234"
    assert tenant_5678.json()["content"] == "regras do tenant 5678"
    assert vector_store.reindex_calls == [
        ("1234", "regras do tenant 1234"),
        ("5678", "regras do tenant 5678"),
        ("1234", "regras atualizadas do tenant 1234"),
    ]

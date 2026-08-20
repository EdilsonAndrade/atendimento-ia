from datetime import datetime, timezone

import pytest

from modules.knowledge_base.application.use_cases import (
    GetTenantKnowledgeBase,
    UpsertTenantKnowledgeBase,
)
from modules.knowledge_base.domain.knowledge_base_document import (
    EmptyKnowledgeBaseContentError,
    KnowledgeBaseDocument,
)


class FakeKnowledgeBaseRepository:
    def __init__(self):
        self.store = {}
        self.upsert_calls = []

    def get(self, tenant_id):
        return self.store.get(tenant_id)

    def upsert(self, tenant_id, content):
        self.upsert_calls.append((tenant_id, content))
        document = KnowledgeBaseDocument(
            tenant_id=tenant_id, content=content, updated_at=datetime.now(timezone.utc)
        )
        self.store[tenant_id] = document
        return document

    def delete(self, tenant_id):
        return self.store.pop(tenant_id, None) is not None


def test_get_returns_none_when_no_document_exists():
    repo = FakeKnowledgeBaseRepository()

    result = GetTenantKnowledgeBase(repo).execute("1234")

    assert result is None


def test_get_returns_existing_document():
    repo = FakeKnowledgeBaseRepository()
    repo.upsert("1234", "conteudo existente")

    result = GetTenantKnowledgeBase(repo).execute("1234")

    assert result.content == "conteudo existente"


def test_upsert_persists_via_repository_port():
    repo = FakeKnowledgeBaseRepository()

    document = UpsertTenantKnowledgeBase(repo).execute("1234", "Regra: atende terça a sábado.")

    assert document.tenant_id == "1234"
    assert repo.upsert_calls == [("1234", "Regra: atende terça a sábado.")]
    assert repo.get("1234").content == "Regra: atende terça a sábado."


def test_upsert_replaces_existing_content_not_append():
    repo = FakeKnowledgeBaseRepository()
    UpsertTenantKnowledgeBase(repo).execute("1234", "conteudo v1")

    UpsertTenantKnowledgeBase(repo).execute("1234", "conteudo v2")

    assert repo.get("1234").content == "conteudo v2"
    assert len(repo.upsert_calls) == 2


def test_upsert_rejects_empty_content_before_touching_repository():
    repo = FakeKnowledgeBaseRepository()

    with pytest.raises(EmptyKnowledgeBaseContentError):
        UpsertTenantKnowledgeBase(repo).execute("1234", "   ")

    assert repo.upsert_calls == []

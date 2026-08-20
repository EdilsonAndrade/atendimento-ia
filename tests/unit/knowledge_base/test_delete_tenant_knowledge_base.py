from datetime import datetime, timezone

from modules.knowledge_base.application.use_cases import DeleteTenantKnowledgeBase
from modules.knowledge_base.domain.knowledge_base_document import KnowledgeBaseDocument


class FakeKnowledgeBaseRepository:
    def __init__(self):
        self.store = {}
        self.delete_calls = []

    def get(self, tenant_id):
        return self.store.get(tenant_id)

    def upsert(self, tenant_id, content):
        document = KnowledgeBaseDocument(
            tenant_id=tenant_id, content=content, updated_at=datetime.now(timezone.utc)
        )
        self.store[tenant_id] = document
        return document

    def delete(self, tenant_id):
        self.delete_calls.append(tenant_id)
        return self.store.pop(tenant_id, None) is not None


def test_delete_removes_existing_document_and_returns_true():
    repo = FakeKnowledgeBaseRepository()
    repo.upsert("1234", "conteudo")

    result = DeleteTenantKnowledgeBase(repo).execute("1234")

    assert result is True
    assert repo.get("1234") is None
    assert repo.delete_calls == ["1234"]


def test_delete_returns_false_when_nothing_to_delete():
    repo = FakeKnowledgeBaseRepository()

    result = DeleteTenantKnowledgeBase(repo).execute("sem-base")

    assert result is False
    assert repo.delete_calls == ["sem-base"]

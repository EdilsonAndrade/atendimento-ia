"""EDI-53: `GET /api/v1/tenants/{tenant_id}/conversation-history/{base_thread_id}` —
contrato HTTP com fake de repositório (mesmo padrão de test_tenant_usage_endpoint_api.py),
sem exigir Postgres real.
"""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.conversation_history import get_use_case, router as conversation_history_router
from modules.conversation_history.application.get_conversation_history import GetConversationHistoryUseCase
from modules.conversation_history.domain.conversation_message import ConversationMessage


class FakeConversationMessageRepository:
    def __init__(self, messages_by_key=None):
        self._messages_by_key = messages_by_key or {}

    def list_by_thread(self, tenant_id, base_thread_id, limit=200, before=None):
        return self._messages_by_key.get((tenant_id, base_thread_id), [])

    def save_turn(self, human, ai):
        raise NotImplementedError

    def purge_older_than(self, tenant_id, retention_days):
        raise NotImplementedError


def make_client(messages_by_key=None):
    app = FastAPI()
    app.include_router(conversation_history_router, prefix="/api/v1")
    fake_repo = FakeConversationMessageRepository(messages_by_key)
    app.dependency_overrides[get_use_case] = lambda: GetConversationHistoryUseCase(fake_repo)
    return TestClient(app)


def _msg(tenant_id, base_thread_id, role, content, when):
    return ConversationMessage(
        tenant_id=tenant_id,
        base_thread_id=base_thread_id,
        active_thread_id=f"{base_thread_id}#abc",
        role=role,
        content=content,
        created_at=when,
    )


def test_devolve_mensagens_em_ordem_cronologica():
    t0 = datetime(2026, 8, 26, 14, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 26, 14, 0, 3, tzinfo=timezone.utc)
    client = make_client(
        {
            ("acme", "acme:5511999998888"): [
                _msg("acme", "acme:5511999998888", "human", "Oi, quero agendar", t0),
                _msg("acme", "acme:5511999998888", "ai", "Claro! Qual serviço?", t1),
            ]
        }
    )

    response = client.get("/api/v1/tenants/acme/conversation-history/acme:5511999998888")

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "acme"
    assert body["base_thread_id"] == "acme:5511999998888"
    assert [m["role"] for m in body["messages"]] == ["human", "ai"]
    assert body["messages"][0]["content"] == "Oi, quero agendar"


def test_thread_sem_mensagens_devolve_lista_vazia():
    client = make_client()

    response = client.get("/api/v1/tenants/acme/conversation-history/acme:0000")

    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_isolamento_entre_tenants():
    t0 = datetime(2026, 8, 26, 14, 0, 0, tzinfo=timezone.utc)
    client = make_client(
        {
            ("acme", "acme:123"): [_msg("acme", "acme:123", "human", "só do acme", t0)],
            ("outra", "acme:123"): [_msg("outra", "acme:123", "human", "só da outra", t0)],
        }
    )

    response = client.get("/api/v1/tenants/acme/conversation-history/acme:123")

    body = response.json()
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"] == "só do acme"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

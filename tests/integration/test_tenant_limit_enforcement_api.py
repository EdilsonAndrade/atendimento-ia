"""EDI-63: enforcement do limite mensal em `POST /api/v1/chat` — mesmo padrão de
tests/test_chat_api.py (chama `chat_interaction` diretamente, monkeypatchando os
singletons do módulo em vez de subir um Postgres real).
"""
import asyncio
from types import SimpleNamespace

from langchain_core.messages import HumanMessage
from starlette.requests import Request

from app.api.v1.endpoints import chat as chat_module
from app.schemas.chat import MessageRequest


def make_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )


class _FakeCheckUseCase:
    def __init__(self, blocked_tenants: set[str]):
        self._blocked_tenants = blocked_tenants
        self.calls = []

    def execute(self, tenant_id, thread_id=None):
        self.calls.append(tenant_id)
        return tenant_id in self._blocked_tenants


class _FakeNotifyUseCase:
    def __init__(self):
        self.calls = []

    def execute(self, tenant_id):
        self.calls.append(tenant_id)


def test_tenant_bloqueado_nao_invoca_o_grafo_e_devolve_resposta_vazia(monkeypatch):
    invoked = []

    def fake_invoke(*args, **kwargs):
        invoked.append(True)
        return {"messages": [HumanMessage(content="não deveria chegar aqui")]}

    monkeypatch.setattr(chat_module, "graph_app", SimpleNamespace(invoke=fake_invoke))
    fake_check = _FakeCheckUseCase(blocked_tenants={"tenant-bloqueado"})
    fake_notify = _FakeNotifyUseCase()
    monkeypatch.setattr(chat_module, "check_tenant_limit_use_case", fake_check)
    monkeypatch.setattr(chat_module, "notify_usage_milestones_use_case", fake_notify)

    response = asyncio.run(
        chat_module.chat_interaction(
            make_request(),
            MessageRequest(message="Olá", tenant_id="tenant-bloqueado"),
            tenant_id=None,
        )
    )

    assert response.response == ""
    assert response.status == "success"
    assert invoked == []  # ZERO chamadas ao LLM/grafo
    assert fake_notify.calls == []  # não notifica marco numa mensagem bloqueada


def test_tenant_nao_bloqueado_invoca_o_grafo_e_notifica_marcos(monkeypatch):
    def fake_invoke(*args, **kwargs):
        return {"messages": [HumanMessage(content="Resposta normal")]}

    monkeypatch.setattr(chat_module, "graph_app", SimpleNamespace(invoke=fake_invoke))
    fake_check = _FakeCheckUseCase(blocked_tenants=set())
    fake_notify = _FakeNotifyUseCase()
    monkeypatch.setattr(chat_module, "check_tenant_limit_use_case", fake_check)
    monkeypatch.setattr(chat_module, "notify_usage_milestones_use_case", fake_notify)

    response = asyncio.run(
        chat_module.chat_interaction(
            make_request(),
            MessageRequest(message="Olá", tenant_id="tenant-normal"),
            tenant_id=None,
        )
    )

    assert response.response == "Resposta normal"
    assert fake_notify.calls == ["tenant-normal"]


def test_bloqueio_de_um_tenant_nao_afeta_outro_tenant(monkeypatch):
    """Isolamento multi-tenant (Princípio I): tenant A bloqueado, tenant B não."""

    def fake_invoke(*args, **kwargs):
        return {"messages": [HumanMessage(content="Resposta do tenant B")]}

    monkeypatch.setattr(chat_module, "graph_app", SimpleNamespace(invoke=fake_invoke))
    fake_check = _FakeCheckUseCase(blocked_tenants={"tenant-a"})
    fake_notify = _FakeNotifyUseCase()
    monkeypatch.setattr(chat_module, "check_tenant_limit_use_case", fake_check)
    monkeypatch.setattr(chat_module, "notify_usage_milestones_use_case", fake_notify)

    response_a = asyncio.run(
        chat_module.chat_interaction(
            make_request(), MessageRequest(message="Olá", tenant_id="tenant-a"), tenant_id=None,
        )
    )
    response_b = asyncio.run(
        chat_module.chat_interaction(
            make_request(), MessageRequest(message="Olá", tenant_id="tenant-b"), tenant_id=None,
        )
    )

    assert response_a.response == ""
    assert response_b.response == "Resposta do tenant B"
    assert fake_check.calls == ["tenant-a", "tenant-b"]

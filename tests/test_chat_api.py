import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def test_chat_accepts_tenant_in_body(monkeypatch):
    def fake_invoke(*args, **kwargs):
        return {"messages": [HumanMessage(content="Resposta do site")]}

    monkeypatch.setattr(chat_module, "graph_app", SimpleNamespace(invoke=fake_invoke))

    response = asyncio.run(
        chat_module.chat_interaction(
            make_request(),
            MessageRequest(message="Olá, quero agendar", tenant_id="site-tenant-123"),
            tenant_id=None,
        )
    )

    assert response.tenant_id == "site-tenant-123"
    assert response.response == "Resposta do site"


def test_chat_accepts_tenant_in_header(monkeypatch):
    def fake_invoke(*args, **kwargs):
        return {"messages": [HumanMessage(content="Resposta do header")]}

    monkeypatch.setattr(chat_module, "graph_app", SimpleNamespace(invoke=fake_invoke))

    response = asyncio.run(
        chat_module.chat_interaction(
            make_request(),
            MessageRequest(message="Olá, quero agendar"),
            tenant_id="header-tenant-456",
        )
    )

    assert response.tenant_id == "header-tenant-456"
    assert response.response == "Resposta do header"

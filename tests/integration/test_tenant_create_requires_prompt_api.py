"""Cadastro de tenant exige prompt operacional (EDI-43 / FR-016-018).

Testes de contrato HTTP com fakes do service: o objetivo aqui é fixar os códigos
e o formato do envelope que o EDI-44 consome, não o comportamento de banco (que
é coberto pelos testes de repositório).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import tenant as tenant_module
from modules.tenant.tenant_service import PromptNodeTypeInvalidError, PromptNotFoundError


PAYLOAD_VALIDO = {
    "tenant_id": "acme",
    "name": "Acme Ltda",
    "google_calendar_id": "acme@group.calendar.google.com",
    "allowed_domains": ["acme.com"],
    "prompt_id": "3f2a1b4c-0000-0000-0000-000000000001",
}


def make_client(error=None, resultado=None):
    class _FakeTenantService:
        def create_tenant(self, tenant_data):
            if error:
                raise error
            return resultado

    app = FastAPI()
    app.include_router(tenant_module.router, prefix="/api/v1")
    app.dependency_overrides[tenant_module.TenantService] = lambda: _FakeTenantService()
    return TestClient(app)


def test_sem_prompt_id_retorna_422_no_formato_de_lista_do_pydantic():
    """O 422 é a assimetria deliberada do contrato: validação de schema mantém o
    formato nativo, enquanto regra de negócio usa o envelope estruturado."""
    client = make_client()
    payload = {k: v for k, v in PAYLOAD_VALIDO.items() if k != "prompt_id"}

    response = client.post("/api/v1/tenants/", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_prompt_id_vazio_retorna_422():
    client = make_client()

    response = client.post("/api/v1/tenants/", json={**PAYLOAD_VALIDO, "prompt_id": ""})

    assert response.status_code == 422


def test_prompt_inexistente_retorna_404_com_envelope_estruturado():
    client = make_client(error=PromptNotFoundError("p-inexistente"))

    response = client.post("/api/v1/tenants/", json=PAYLOAD_VALIDO)

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "PROMPT_NOT_FOUND"
    assert detail["blockers"] == []
    assert detail["message"]


def test_node_type_errado_retorna_400_com_envelope_estruturado():
    client = make_client(error=PromptNodeTypeInvalidError("p1", "chitchat"))

    response = client.post("/api/v1/tenants/", json=PAYLOAD_VALIDO)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "PROMPT_NODE_TYPE_INVALID"
    assert "chitchat" in detail["message"]


def test_cadastro_valido_retorna_o_tenant():
    from datetime import datetime

    client = make_client(
        resultado={
            "id": "acme",
            "name": "Acme Ltda",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "scheduling_enabled": True,
            "created_at": datetime(2026, 8, 22, 10, 0, 0),
            "updated_at": None,
            "deleted_at": None,
        }
    )

    response = client.post("/api/v1/tenants/", json=PAYLOAD_VALIDO)

    assert response.status_code == 200
    assert response.json()["id"] == "acme"

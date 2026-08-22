"""Grid da tela de Tenants (EDI-46): `GET /api/v1/tenants/list`.

Endpoint separado de `GET /api/v1/tenants` (busca da Base de Conhecimento,
que continua devolvendo array puro e não pode ser tocada) — este devolve
`{items, total}` com as tags de prompt/guardrail já embutidas por tenant.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tenant import router as tenant_router
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self, result):
        self._result = result
        self.last_call = None

    def list_tenants(self, term=None, limit=20, offset=0):
        self.last_call = (term, limit, offset)
        return self._result


def make_client(fake_service):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: fake_service
    return TestClient(app)


def _item(tenant_id="1234", name="Barbearia Central"):
    return {
        "id": tenant_id,
        "name": name,
        "google_calendar_id": "cal@x",
        "allowed_domains": ["barbeariacentral.com.br"],
        "created_at": "2026-01-10T12:00:00Z",
        "updated_at": None,
        "prompts": [{"id": "p1", "titulo": "P1", "node_type": "operational"}],
        "guardrails": [{"id": "g1", "titulo": "G1", "is_global": True}],
    }


def test_list_sem_q_lista_tudo():
    fake = FakeTenantService({"items": [_item()], "total": 1})
    client = make_client(fake)

    response = client.get("/api/v1/tenants/list")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["prompts"][0]["node_type"] == "operational"
    assert body["items"][0]["guardrails"][0]["is_global"] is True
    assert fake.last_call == (None, 20, 0)


def test_list_com_q_filtra():
    fake = FakeTenantService({"items": [_item()], "total": 1})
    client = make_client(fake)

    response = client.get("/api/v1/tenants/list", params={"q": "barbearia"})

    assert response.status_code == 200
    assert fake.last_call == ("barbearia", 20, 0)


def test_list_retorna_vazio_sem_match():
    fake = FakeTenantService({"items": [], "total": 0})
    client = make_client(fake)

    response = client.get("/api/v1/tenants/list", params={"q": "inexistente"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_respeita_limit_e_offset():
    fake = FakeTenantService({"items": [], "total": 0})
    client = make_client(fake)

    client.get("/api/v1/tenants/list", params={"limit": 5, "offset": 40})

    assert fake.last_call == (None, 5, 40)


def test_list_rejeita_q_vazio_com_422():
    fake = FakeTenantService({"items": [], "total": 0})
    client = make_client(fake)

    response = client.get("/api/v1/tenants/list", params={"q": ""})

    assert response.status_code == 422

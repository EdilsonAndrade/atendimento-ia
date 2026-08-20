from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tenant import router as tenant_router
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self, results):
        self._results = results
        self.last_call = None

    def search_tenants(self, term, limit=20):
        self.last_call = (term, limit)
        return self._results


def make_client(fake_service):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: fake_service
    return TestClient(app)


def test_search_returns_matching_tenants():
    fake = FakeTenantService(
        [
            {
                "id": "1234",
                "name": "Barbearia Central",
                "google_calendar_id": "cal@x",
                "allowed_domains": ["barbeariacentral.com.br"],
                "created_at": "2026-01-10T12:00:00Z",
                "updated_at": None,
            }
        ]
    )
    client = make_client(fake)

    response = client.get("/api/v1/tenants", params={"q": "barbearia"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "1234"
    assert fake.last_call == ("barbearia", 20)


def test_search_returns_empty_list_when_no_match_not_404():
    fake = FakeTenantService([])
    client = make_client(fake)

    response = client.get("/api/v1/tenants", params={"q": "inexistente"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_rejects_empty_query_with_422():
    fake = FakeTenantService([])
    client = make_client(fake)

    response = client.get("/api/v1/tenants", params={"q": ""})

    assert response.status_code == 422


def test_search_respects_custom_limit():
    fake = FakeTenantService([])
    client = make_client(fake)

    client.get("/api/v1/tenants", params={"q": "abc", "limit": 5})

    assert fake.last_call == ("abc", 5)

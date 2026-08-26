"""EDI-53: `oferta_vigente_texto`/`oferta_vigente_validade`/`retention_days` via
POST/PUT/GET /tenants — mesmo padrão de test_tenant_message_limit_api.py (TestClient
+ FakeTenantService via dependency_overrides, sem exigir Postgres real).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tenant import router as tenant_router
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self):
        self.created = None
        self.updated = None

    def create_tenant(self, tenant_data):
        self.created = tenant_data
        return {
            "id": tenant_data["tenant_id"],
            "name": tenant_data["name"],
            "google_calendar_id": tenant_data["google_calendar_id"],
            "allowed_domains": tenant_data["allowed_domains"],
            "scheduling_enabled": tenant_data.get("scheduling_enabled", True),
            "monthly_message_limit": tenant_data.get("monthly_message_limit"),
            "notification_emails": tenant_data.get("notification_emails", []),
            "oferta_vigente_texto": tenant_data.get("oferta_vigente_texto"),
            "oferta_vigente_validade": tenant_data.get("oferta_vigente_validade"),
            "retention_days": tenant_data.get("retention_days"),
            "created_at": "2026-08-26T12:00:00Z",
        }

    def update_tenant(self, tenant_id, tenant_data):
        self.updated = (tenant_id, tenant_data)
        return {
            "id": tenant_id,
            "name": tenant_data["name"],
            "google_calendar_id": tenant_data["google_calendar_id"],
            "allowed_domains": tenant_data["allowed_domains"],
            "scheduling_enabled": tenant_data.get("scheduling_enabled", True),
            "monthly_message_limit": tenant_data.get("monthly_message_limit"),
            "notification_emails": tenant_data.get("notification_emails", []),
            "oferta_vigente_texto": tenant_data.get("oferta_vigente_texto"),
            "oferta_vigente_validade": tenant_data.get("oferta_vigente_validade"),
            "retention_days": tenant_data.get("retention_days"),
            "created_at": "2026-08-26T12:00:00Z",
            "updated_at": "2026-08-26T12:30:00Z",
        }

    def get_tenant(self, tenant_id):
        return {
            "id": tenant_id,
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "scheduling_enabled": True,
            "monthly_message_limit": None,
            "notification_emails": [],
            "oferta_vigente_texto": "10% na primeira sessão",
            "oferta_vigente_validade": "2026-12-31",
            "retention_days": 180,
            "created_at": "2026-08-26T12:00:00Z",
        }


def make_client(fake_service=None):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: (fake_service or FakeTenantService())
    return TestClient(app)


def test_create_tenant_persiste_oferta_e_retencao():
    fake = FakeTenantService()
    client = make_client(fake)

    response = client.post(
        "/api/v1/tenants/",
        json={
            "tenant_id": "acme",
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "prompt_id": "prompt-1",
            "oferta_vigente_texto": "10% na primeira sessão",
            "oferta_vigente_validade": "2026-12-31",
            "retention_days": 180,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["oferta_vigente_texto"] == "10% na primeira sessão"
    assert body["oferta_vigente_validade"] == "2026-12-31"
    assert body["retention_days"] == 180


def test_create_tenant_sem_oferta_fica_none():
    client = make_client()

    response = client.post(
        "/api/v1/tenants/",
        json={
            "tenant_id": "acme",
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "prompt_id": "prompt-1",
        },
    )

    body = response.json()
    assert body["oferta_vigente_texto"] is None
    assert body["oferta_vigente_validade"] is None
    assert body["retention_days"] is None


def test_update_tenant_altera_oferta_e_retencao():
    fake = FakeTenantService()
    client = make_client(fake)

    response = client.put(
        "/api/v1/tenants/acme",
        json={
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "oferta_vigente_texto": "20% no pacote anual",
            "oferta_vigente_validade": "2027-01-15",
            "retention_days": 90,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["oferta_vigente_texto"] == "20% no pacote anual"
    assert body["retention_days"] == 90


def test_get_tenant_devolve_oferta_e_retencao():
    client = make_client()

    response = client.get("/api/v1/tenants/acme")

    body = response.json()
    assert body["oferta_vigente_texto"] == "10% na primeira sessão"
    assert body["oferta_vigente_validade"] == "2026-12-31"
    assert body["retention_days"] == 180


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

"""EDI-63: `monthly_message_limit`/`notification_emails` via POST/PUT/GET /tenants.

Segue o mesmo padrão de tests/integration/test_tenant_list_grid_api.py — TestClient
+ FakeTenantService via dependency_overrides, sem exigir Postgres real (o contrato
HTTP é o que está sob teste aqui; a persistência real é coberta por
tests/integration/test_tenant_limit_enforcement_api.py e pelos testes já
existentes do módulo `tenant`).
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
            "created_at": "2026-08-25T12:00:00Z",
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
            "created_at": "2026-08-25T12:00:00Z",
            "updated_at": "2026-08-25T12:30:00Z",
        }


def make_client(fake_service):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: fake_service
    return TestClient(app)


def test_create_tenant_persiste_limite_e_emails():
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
            "monthly_message_limit": 3000,
            "notification_emails": ["gerente@acme.com", "responsavel@acme.com"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_message_limit"] == 3000
    assert body["notification_emails"] == ["gerente@acme.com", "responsavel@acme.com"]
    assert fake.created["monthly_message_limit"] == 3000


def test_create_tenant_sem_limite_fica_none():
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
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_message_limit"] is None
    assert body["notification_emails"] == []


def test_update_tenant_altera_limite_e_emails():
    fake = FakeTenantService()
    client = make_client(fake)

    response = client.put(
        "/api/v1/tenants/acme",
        json={
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "monthly_message_limit": 5000,
            "notification_emails": ["novo@acme.com"],
        },
    )

    assert response.status_code == 200
    assert response.json()["monthly_message_limit"] == 5000
    assert fake.updated == (
        "acme",
        {
            "name": "Acme",
            "google_calendar_id": "acme@group.calendar.google.com",
            "allowed_domains": ["acme.com"],
            "scheduling_enabled": True,
            "monthly_message_limit": 5000,
            "notification_emails": ["novo@acme.com"],
        },
    )


def test_create_tenant_com_email_invalido_devolve_422():
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
            "notification_emails": ["nao-e-um-email"],
        },
    )

    assert response.status_code == 422
    assert fake.created is None

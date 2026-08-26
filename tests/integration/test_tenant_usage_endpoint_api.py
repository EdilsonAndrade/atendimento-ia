"""EDI-63: `GET /api/v1/tenants/{tenant_id}/usage` — contrato HTTP com fakes
(mesmo padrão de test_tenant_list_grid_api.py), sem exigir Postgres real.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tenant import (
    get_tenant_limit_config,
    get_usage_counter,
    router as tenant_router,
)
from modules.tenant.tenant_service import TenantService


class FakeTenantService:
    def __init__(self, exists: bool = True):
        self._exists = exists

    def get_tenant(self, tenant_id):
        return {"id": tenant_id} if self._exists else None


class FakeTenantLimitConfig:
    def __init__(self, limit=None):
        self._limit = limit

    def get_limit_and_emails(self, tenant_id):
        return self._limit, []


class FakeUsageCounter:
    def __init__(self, count=0):
        self._count = count

    def count_current_month(self, tenant_id):
        return self._count


def make_client(tenant_exists=True, limit=None, count=0):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: FakeTenantService(tenant_exists)
    app.dependency_overrides[get_tenant_limit_config] = lambda: FakeTenantLimitConfig(limit)
    app.dependency_overrides[get_usage_counter] = lambda: FakeUsageCounter(count)
    return TestClient(app)


def test_tenant_sem_limite_percentage_e_none_e_nao_bloqueado():
    client = make_client(limit=None, count=9999)

    response = client.get("/api/v1/tenants/acme/usage")

    assert response.status_code == 200
    body = response.json()
    assert body["monthly_message_limit"] is None
    assert body["percentage_used"] is None
    assert body["blocked"] is False


def test_tenant_com_limite_parcial():
    client = make_client(limit=1000, count=310)

    response = client.get("/api/v1/tenants/acme/usage")

    body = response.json()
    assert body["current_month_calls"] == 310
    assert body["percentage_used"] == 31.0
    assert body["blocked"] is False


def test_tenant_no_limite_fica_bloqueado():
    client = make_client(limit=1000, count=1000)

    response = client.get("/api/v1/tenants/acme/usage")

    assert response.json()["blocked"] is True


def test_tenant_inexistente_devolve_404():
    client = make_client(tenant_exists=False)

    response = client.get("/api/v1/tenants/nao-existe/usage")

    assert response.status_code == 404


def test_message_limit_config_devolve_razoes(monkeypatch):
    monkeypatch.setenv("TENANT_LIMIT_WORST_CASE_CALLS_PER_MESSAGE", "3")
    monkeypatch.setenv("TENANT_LIMIT_AVERAGE_CALLS_PER_MESSAGE", "3")
    client = make_client()

    response = client.get("/api/v1/tenants/message-limit-config")

    assert response.status_code == 200
    assert response.json() == {"worst_case_calls_per_message": 3, "average_calls_per_message": 3.0}

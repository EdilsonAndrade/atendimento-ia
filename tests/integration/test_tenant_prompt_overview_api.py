from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import prompt_manager as prompt_manager_module
from modules.prompt_manager.prompt_manager_service import DefaultPromptNotConfiguredError


class FakeTenantService:
    def __init__(self, tenant=None):
        self._tenant = tenant

    def get_tenant(self, tenant_id):
        return self._tenant


def make_fake_prompt_manager_service(result=None, error=None):
    class _FakePromptManagerService:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_tenant_prompt_details(self, tenant_id):
            if error:
                raise error
            return result

    return _FakePromptManagerService


def make_client(monkeypatch, tenant=None, result=None, error=None):
    monkeypatch.setattr(prompt_manager_module, "TenantService", lambda: FakeTenantService(tenant))
    monkeypatch.setattr(
        prompt_manager_module,
        "PromptManagerService",
        make_fake_prompt_manager_service(result=result, error=error),
    )
    app = FastAPI()
    app.include_router(prompt_manager_module.router, prefix="/api/v1")
    return TestClient(app)


def test_returns_404_when_tenant_does_not_exist(monkeypatch):
    client = make_client(monkeypatch, tenant=None)

    response = client.get("/api/v1/prompt-manager/tenant/inexistente")

    assert response.status_code == 404


def test_returns_custom_prompt_overview_when_link_exists(monkeypatch):
    client = make_client(
        monkeypatch,
        tenant={"id": "1234"},
        result={
            "tenant_id": "1234",
            "prompt_id": "p1",
            "prompt_titulo": "Atendimento Barbearia",
            "prompt_conteudo": "conteudo custom",
            "custom_content_override": None,
            "is_default_prompt": False,
            "is_active": True,
            "guardrails_associados": [
                {"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": False}
            ],
        },
    )

    response = client.get("/api/v1/prompt-manager/tenant/1234")

    assert response.status_code == 200
    body = response.json()
    assert body["is_default_prompt"] is False
    assert body["is_active"] is True
    assert body["prompt_id"] == "p1"


def test_returns_default_prompt_fallback_when_no_link(monkeypatch):
    client = make_client(
        monkeypatch,
        tenant={"id": "5678"},
        result={
            "tenant_id": "5678",
            "prompt_id": "dP",
            "prompt_titulo": "Prompt Padrão",
            "prompt_conteudo": "conteudo padrão",
            "custom_content_override": None,
            "is_default_prompt": True,
            "is_active": True,
            "guardrails_associados": [
                {"id": "gG1", "titulo": "Guardrail Global 1", "conteudo": "...", "is_global": True}
            ],
        },
    )

    response = client.get("/api/v1/prompt-manager/tenant/5678")

    assert response.status_code == 200
    body = response.json()
    assert body["is_default_prompt"] is True
    assert body["is_active"] is True
    assert body["prompt_id"] == "dP"


def test_returns_500_when_no_default_prompt_configured(monkeypatch):
    client = make_client(
        monkeypatch,
        tenant={"id": "999"},
        error=DefaultPromptNotConfiguredError("sem prompt padrão configurado"),
    )

    response = client.get("/api/v1/prompt-manager/tenant/999")

    assert response.status_code == 500

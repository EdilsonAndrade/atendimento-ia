import pytest

from modules.prompt_manager.prompt_manager_service import (
    DefaultPromptNotConfiguredError,
    PromptManagerService,
)


class FakeRepo:
    def __init__(self, tenant_details=None, default_prompt=None, global_guardrails=None):
        self._tenant_details = tenant_details
        self._default_prompt = default_prompt
        self._global_guardrails = global_guardrails or []

    def get_tenant_prompt_details(self, tenant_id):
        return self._tenant_details

    def get_default_prompt(self):
        return self._default_prompt

    def get_global_guardrails(self):
        return self._global_guardrails


def make_service(**kwargs):
    service = PromptManagerService(lambda: None)
    service.repository = FakeRepo(**kwargs)
    return service


def test_returns_custom_prompt_when_active_link_exists():
    tenant_details = {
        "tenant_id": "1234",
        "prompt_id": "p1",
        "prompt_titulo": "Atendimento Barbearia",
        "prompt_conteudo_base": "conteudo custom",
        "custom_content_override": None,
        "guardrails_associados": [
            {"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": False}
        ],
    }
    service = make_service(tenant_details=tenant_details)

    result = service.get_tenant_prompt_details("1234")

    assert result["is_default_prompt"] is False
    assert result["prompt_id"] == "p1"
    assert result["prompt_conteudo"] == "conteudo custom"
    assert result["guardrails_associados"] == tenant_details["guardrails_associados"]


def test_falls_back_to_default_prompt_when_no_active_link():
    default_prompt = {"id": "dP", "titulo": "Prompt Padrão", "conteudo": "conteudo padrão"}
    global_guardrails = [{"id": "gG1", "titulo": "Guardrail Global 1", "conteudo": "...", "is_global": True}]
    service = make_service(tenant_details=None, default_prompt=default_prompt, global_guardrails=global_guardrails)

    result = service.get_tenant_prompt_details("5678")

    assert result["is_default_prompt"] is True
    assert result["prompt_id"] == "dP"
    assert result["prompt_conteudo"] == "conteudo padrão"
    assert result["custom_content_override"] is None
    assert result["guardrails_associados"] == global_guardrails


def test_raises_when_no_default_prompt_configured():
    service = make_service(tenant_details=None, default_prompt=None)

    with pytest.raises(DefaultPromptNotConfiguredError):
        service.get_tenant_prompt_details("no-default-configured")

import pytest

from modules.prompt_manager.prompt_manager_service import (
    DefaultPromptNotConfiguredError,
    PromptManagerService,
)


class FakeRepo:
    def __init__(self, tenant_details=None, default_prompt=None, global_guardrails=None,
                 tenant_details_by_node=None, default_prompt_by_node=None):
        # Compat com os testes antigos (só operational): tenant_details/default_prompt
        self._tenant_details_by_node = {"operational": tenant_details, **(tenant_details_by_node or {})}
        self._default_prompt_by_node = {"operational": default_prompt, **(default_prompt_by_node or {})}
        self._global_guardrails = global_guardrails or []

    def get_tenant_prompt_details(self, tenant_id, node_type="operational"):
        return self._tenant_details_by_node.get(node_type)

    def get_default_prompt(self, node_type="operational"):
        return self._default_prompt_by_node.get(node_type)

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
        "is_active": True,
        "guardrails_associados": [
            {"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": False}
        ],
    }
    service = make_service(tenant_details=tenant_details)

    result = service.get_tenant_prompt_details("1234")

    assert result["is_default_prompt"] is False
    assert result["is_active"] is True
    assert result["prompt_id"] == "p1"
    assert result["prompt_conteudo"] == "conteudo custom"
    assert result["guardrails_associados"] == tenant_details["guardrails_associados"]


def test_falls_back_to_default_prompt_when_no_active_link():
    default_prompt = {"id": "dP", "titulo": "Prompt Padrão", "conteudo": "conteudo padrão"}
    global_guardrails = [{"id": "gG1", "titulo": "Guardrail Global 1", "conteudo": "...", "is_global": True}]
    service = make_service(tenant_details=None, default_prompt=default_prompt, global_guardrails=global_guardrails)

    result = service.get_tenant_prompt_details("5678")

    assert result["is_default_prompt"] is True
    assert result["is_active"] is True
    assert result["prompt_id"] == "dP"
    assert result["prompt_conteudo"] == "conteudo padrão"
    assert result["custom_content_override"] is None
    assert result["guardrails_associados"] == global_guardrails


def test_raises_when_no_default_prompt_configured():
    service = make_service(tenant_details=None, default_prompt=None)

    with pytest.raises(DefaultPromptNotConfiguredError):
        service.get_tenant_prompt_details("no-default-configured")


def test_institutional_uses_own_link_when_present():
    institutional_details = {
        "tenant_id": "1234",
        "prompt_id": "pInst",
        "prompt_titulo": "Institucional - Barbearia",
        "prompt_conteudo_base": "conteudo institucional proprio",
        "custom_content_override": None,
        "is_active": True,
        "guardrails_associados": [{"id": "gInst", "titulo": "Regra institucional", "conteudo": "...", "is_global": False}],
    }
    service = make_service(tenant_details_by_node={"institutional": institutional_details})

    result = service.get_tenant_prompt_details("1234", node_type="institutional")

    assert result["node_type"] == "institutional"
    assert result["is_default_prompt"] is False
    assert result["prompt_id"] == "pInst"
    assert result["prompt_conteudo"] == "conteudo institucional proprio"


def test_institutional_falls_back_to_operational_when_no_own_link():
    operational_details = {
        "tenant_id": "1234",
        "prompt_id": "pOper",
        "prompt_titulo": "Atendimento Barbearia",
        "prompt_conteudo_base": "conteudo operacional",
        "custom_content_override": None,
        "is_active": True,
        "guardrails_associados": [{"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": False}],
    }
    service = make_service(tenant_details_by_node={"operational": operational_details})

    result = service.get_tenant_prompt_details("1234", node_type="institutional")

    # Mesmo prompt do operational, mas com node_type refletindo o nó pedido (FR-004)
    assert result["node_type"] == "institutional"
    assert result["prompt_id"] == "pOper"
    assert result["prompt_conteudo"] == "conteudo operacional"
    assert result["is_default_prompt"] is False


def test_chitchat_falls_back_to_its_own_default_prompt_when_no_link():
    chitchat_default = {"id": "dChit", "titulo": "Chitchat Padrão", "conteudo": "conteudo chitchat padrão"}
    global_guardrails = [{"id": "gG1", "titulo": "Guardrail Global 1", "conteudo": "...", "is_global": True}]
    service = make_service(default_prompt_by_node={"chitchat": chitchat_default}, global_guardrails=global_guardrails)

    result = service.get_tenant_prompt_details("5678", node_type="chitchat")

    assert result["node_type"] == "chitchat"
    assert result["is_default_prompt"] is True
    assert result["prompt_id"] == "dChit"
    assert result["prompt_conteudo"] == "conteudo chitchat padrão"
    assert result["guardrails_associados"] == global_guardrails


def test_chitchat_raises_when_no_link_and_no_default_configured():
    service = make_service()

    with pytest.raises(DefaultPromptNotConfiguredError):
        service.get_tenant_prompt_details("5678", node_type="chitchat")

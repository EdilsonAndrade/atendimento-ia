import pytest

from prompts.load_prompt import carregar_chitchat_prompt, carregar_guardrails


@pytest.fixture
def tenant_id():
    return "test-tenant-edi42-chitchat"


def test_chitchat_guardrail_does_not_leak_into_operational(repo, tenant_id, db_cleanup):
    operational_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Operational - EDI42", conteudo="Op {guardrails} fim", is_default=False, node_type="operational"
    ))
    chitchat_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Chitchat - EDI42", conteudo="Chit {guardrails} fim", is_default=False, node_type="chitchat"
    ))
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail(titulo="Sem piadas EDI42", conteudo="Nunca conte piadas EDI42.", is_global=False)
    )

    repo.sync_prompt_guardrails(chitchat_prompt["id"], [str(guardrail["id"])])
    db_cleanup.track_tenant(tenant_id)
    repo.sync_tenant_prompt(tenant_id, operational_prompt["id"])
    repo.sync_tenant_prompt(tenant_id, chitchat_prompt["id"])

    chitchat_resultado = carregar_chitchat_prompt(tenant_id)
    operational_guardrails = carregar_guardrails(tenant_id)

    assert "Nunca conte piadas EDI42." in chitchat_resultado
    assert "Nunca conte piadas EDI42." not in operational_guardrails


def test_tenant_without_any_chitchat_config_gets_local_fallback():
    resultado = carregar_chitchat_prompt("tenant-sem-config-edi42")

    assert "polite AI assistant for the business" in resultado

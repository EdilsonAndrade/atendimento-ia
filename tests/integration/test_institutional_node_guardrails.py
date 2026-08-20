import uuid

import pytest

from prompts.load_prompt import carregar_institutional_prompt, carregar_operacional_prompt


@pytest.fixture
def tenant_id():
    # Único por teste — evita que o vínculo institutional criado em um teste
    # vaze para outro teste que espera "sem vínculo institutional configurado"
    return f"test-tenant-edi42-institutional-{uuid.uuid4().hex[:8]}"


def _carregar_inst(tenant_id):
    return carregar_institutional_prompt(
        tenant_id, contexto_formatado="ctx", historico_texto="hist", pergunta_usuario="pergunta"
    )


def test_institutional_guardrail_is_isolated_from_operational_and_chitchat(repo, tenant_id, db_cleanup):
    operational_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Operational - EDI42 Inst", conteudo="Op {guardrails} {tenant_id} {tabela_calendario_str} {hora_atual_str} {data_hoje_iso} {contexto_formatado} fim",
        is_default=False, node_type="operational",
    ))
    institutional_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Institutional - EDI42", conteudo="Inst {guardrails} fim", is_default=False, node_type="institutional"
    ))
    chitchat_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Chitchat - EDI42 Inst", conteudo="Chit {guardrails} fim", is_default=False, node_type="chitchat"
    ))
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail(titulo="Regra Inst EDI42", conteudo="Regra institucional exclusiva EDI42.", is_global=False)
    )

    repo.sync_prompt_guardrails(institutional_prompt["id"], [str(guardrail["id"])])
    db_cleanup.track_tenant(tenant_id)
    repo.sync_tenant_prompt(tenant_id, operational_prompt["id"])
    repo.sync_tenant_prompt(tenant_id, institutional_prompt["id"])
    repo.sync_tenant_prompt(tenant_id, chitchat_prompt["id"])

    institutional_resultado = _carregar_inst(tenant_id)
    operational_resultado = carregar_operacional_prompt(
        tenant_id, tabela_calendario_str="tab", hora_atual_str="10:00", data_hoje_iso="2026-08-20", contexto_formatado="ctx"
    )

    assert "Regra institucional exclusiva EDI42." in institutional_resultado
    assert "Regra institucional exclusiva EDI42." not in operational_resultado


def test_institutional_without_own_link_applies_operational_guardrails(repo, tenant_id, db_cleanup):
    operational_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Operational - EDI42 Fallback",
        conteudo="Op {guardrails} {tenant_id} {tabela_calendario_str} {hora_atual_str} {data_hoje_iso} {contexto_formatado} fim",
        is_default=False, node_type="operational",
    ))
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail(titulo="Regra Op EDI42", conteudo="Regra do operational EDI42.", is_global=False)
    )
    repo.sync_prompt_guardrails(operational_prompt["id"], [str(guardrail["id"])])
    db_cleanup.track_tenant(tenant_id)
    repo.sync_tenant_prompt(tenant_id, operational_prompt["id"])

    # Sem nenhum vínculo institutional configurado para este tenant
    institutional_resultado = _carregar_inst(tenant_id)

    assert "Regra do operational EDI42." in institutional_resultado

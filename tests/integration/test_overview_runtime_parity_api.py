"""Paridade entre o que a tela mostra e o que o agente recebe (EDI-43, FR-003/SC-002).

O defeito original: `get_tenant_prompt_details` (usada pelo /overview) buscava
guardrails com um JOIN puro em prompt_guardrails, enquanto `get_guardrails_by_prompt`
(usada no runtime) incluía também os `is_global`. O admin via na tela um conjunto
menor do que o agente efetivamente aplicava — para o MESMO tenant, inclusive um
que já tinha vínculo.

Estes testes comparam os dois caminhos diretamente. Se voltarem a divergir, é
porque alguém alterou uma das duas queries sem alterar a outra.
"""

import pytest

from prompts.prompt_resolver import resolver_guardrails_list


TENANT_ID = "test-tenant-edi43-parity"


class _ServiceAdapter:
    """`resolver_guardrails_list` recebe um service; aqui basta expor o repositório."""

    def __init__(self, repo):
        self.repository = repo


@pytest.fixture
def cenario(repo, db_cleanup):
    """Um prompt vinculado ao tenant, com um guardrail próprio, mais um guardrail
    global que NÃO está associado a esse prompt em prompt_guardrails."""
    guardrail_proprio = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI43 Próprio", "regra especifica do prompt", is_global=False)
    )
    guardrail_global = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI43 Global", "regra global da plataforma", is_global=True)
    )

    prompt = db_cleanup.track_prompt(
        repo.create_prompt(titulo="EDI43 Prompt", conteudo="conteudo {guardrails}", is_default=False)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail_proprio["id"])])

    db_cleanup.track_tenant(TENANT_ID)
    repo.sync_tenant_prompt(TENANT_ID, prompt["id"])

    return {
        "prompt": prompt,
        "guardrail_proprio": guardrail_proprio,
        "guardrail_global": guardrail_global,
    }


def _ids(guardrails):
    return {str(g["id"]) for g in guardrails}


def test_overview_e_runtime_resolvem_o_mesmo_conjunto_com_vinculo(repo, cenario):
    """Este é o caso que o EDI-43 não previa: mesmo COM vínculo, os dois caminhos
    divergiam. A tela omitia os guardrails globais."""
    detalhes = repo.get_tenant_prompt_details(TENANT_ID, node_type="operational")
    do_overview = _ids(detalhes["guardrails_associados"])

    do_runtime = _ids(repo.get_guardrails_by_prompt(cenario["prompt"]["id"]))

    assert do_overview == do_runtime


def test_overview_com_vinculo_inclui_o_guardrail_global_nao_associado(repo, cenario):
    detalhes = repo.get_tenant_prompt_details(TENANT_ID, node_type="operational")
    ids = _ids(detalhes["guardrails_associados"])

    assert str(cenario["guardrail_proprio"]["id"]) in ids
    assert str(cenario["guardrail_global"]["id"]) in ids


def test_tenant_sem_vinculo_resolve_globais_no_runtime(repo, cenario):
    """FR-001: o caminho sem vínculo passa a consultar o banco em vez de devolver
    o arquivo guardrails.md."""
    service = _ServiceAdapter(repo)

    resolvidos = resolver_guardrails_list(service, "tenant-inexistente-edi43", prompt_id=None)

    assert str(cenario["guardrail_global"]["id"]) in _ids(resolvidos)
    assert str(cenario["guardrail_proprio"]["id"]) not in _ids(resolvidos)

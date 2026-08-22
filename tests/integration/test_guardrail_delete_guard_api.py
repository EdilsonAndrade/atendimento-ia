"""Bloqueio de exclusão de guardrail global ou em uso (EDI-43 / FR-023-025).

O ponto não óbvio: checar apenas "está associado a algum prompt" NÃO pega o
guardrail global. Ele não tem linha em prompt_guardrails — alcança os tenants
pela cláusula `WHERE g.is_global = TRUE`. Com um critério só de associação,
justamente o guardrail que protege todos seria o mais fácil de apagar.
"""

import uuid

import pytest

from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import (
    GuardrailInUseByTenantsError,
    GuardrailIsGlobalError,
    PromptManagerService,
)


@pytest.fixture
def service():
    return PromptManagerService(get_db_connection)


@pytest.fixture
def tenant_factory(repo, db_cleanup):
    criados = []

    def _factory(nome="Tenant Guardrail"):
        tenant_id = f"test-edi43-gdel-{uuid.uuid4().hex[:8]}"
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (tenant_id, nome, "cal@test", []),
                )
        db_cleanup.track_tenant(tenant_id)
        criados.append(tenant_id)
        return tenant_id

    yield _factory

    for tenant_id in criados:
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


def test_guardrail_global_nao_pode_ser_excluido(repo, service, db_cleanup):
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI43 Global Del", "regra global", is_global=True)
    )

    with pytest.raises(GuardrailIsGlobalError) as exc:
        service.delete_guardrail(str(guardrail["id"]))

    assert exc.value.code == "GUARDRAIL_IS_GLOBAL"
    assert exc.value.blockers == []
    assert repo.get_guardrail_by_id(str(guardrail["id"])) is not None


def test_guardrail_associado_a_prompt_com_tenant_ativo_nao_pode_ser_excluido(
    repo, service, db_cleanup, tenant_factory
):
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI43 Em Uso", "regra do prompt", is_global=False)
    )
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Prompt Guardrail", "conteudo", is_default=False)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_factory(), prompt["id"])

    with pytest.raises(GuardrailInUseByTenantsError) as exc:
        service.delete_guardrail(str(guardrail["id"]))

    assert exc.value.code == "GUARDRAIL_IN_USE_BY_TENANTS"
    bloqueador = exc.value.blockers[0]
    assert bloqueador["type"] == "prompt"
    assert bloqueador["id"] == str(prompt["id"])
    assert bloqueador["tenant_count"] == 1


def test_is_global_tem_precedencia_sobre_em_uso(repo, service, db_cleanup, tenant_factory):
    """FR-025: com as duas condições, o global vem primeiro — enquanto ele for
    global, desassociar dos prompts não muda nada."""
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI43 Global E Em Uso", "regra", is_global=True)
    )
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Prompt Ambos", "conteudo", is_default=False)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_factory(), prompt["id"])

    with pytest.raises(GuardrailIsGlobalError):
        service.delete_guardrail(str(guardrail["id"]))


def test_guardrail_associado_a_prompt_sem_tenant_ativo_pode_ser_excluido(repo, service, db_cleanup):
    """Sem tenant ativo não há proteção em vigor a perder."""
    guardrail = repo.create_guardrail("EDI43 Sem Tenant", "regra", is_global=False)
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Prompt Sem Tenant", "conteudo", is_default=False)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])

    assert service.delete_guardrail(str(guardrail["id"])) is True


def test_guardrail_sem_associacao_e_nao_global_pode_ser_excluido(repo, service):
    guardrail = repo.create_guardrail("EDI43 Livre", "regra", is_global=False)

    assert service.delete_guardrail(str(guardrail["id"])) is True
    assert repo.get_guardrail_by_id(str(guardrail["id"])) is None


def test_caminho_de_saida_desmarcar_global_e_entao_excluir(repo, service):
    """O bloqueio precisa ter uma saída, senão vira um beco sem fim para o admin."""
    guardrail = repo.create_guardrail("EDI43 Saida", "regra", is_global=True)

    with pytest.raises(GuardrailIsGlobalError):
        service.delete_guardrail(str(guardrail["id"]))

    repo.update_guardrail(str(guardrail["id"]), "EDI43 Saida", "regra", is_global=False)

    assert service.delete_guardrail(str(guardrail["id"])) is True

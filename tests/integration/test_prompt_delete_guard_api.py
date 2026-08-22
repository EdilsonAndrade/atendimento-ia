"""Bloqueio de exclusão de prompt em uso (EDI-43 / FR-022).

Antes, `delete_prompt` executava `DELETE FROM tenant_prompts WHERE prompt_id = %s`:
excluir um prompt usado por N tenants deixava os N órfãos, silenciosamente. Era o
que reabria o invariante fechado pelo cadastro obrigatório e pelo backfill.
"""

import uuid

import pytest

from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import (
    PromptInUseByTenantsError,
    PromptManagerService,
)


@pytest.fixture
def service():
    return PromptManagerService(get_db_connection)


def _criar_tenant(repo, tenant_id, nome):
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


def _apagar_tenant(repo, tenant_id):
    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


@pytest.fixture
def tenant_factory(repo, db_cleanup):
    criados = []

    def _factory(nome="Tenant Teste"):
        tenant_id = f"test-edi43-del-{uuid.uuid4().hex[:8]}"
        _criar_tenant(repo, tenant_id, nome)
        db_cleanup.track_tenant(tenant_id)
        criados.append(tenant_id)
        return tenant_id

    yield _factory

    for tenant_id in criados:
        _apagar_tenant(repo, tenant_id)


def test_prompt_com_vinculo_ativo_nao_pode_ser_excluido(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Del A", "conteudo {guardrails}", is_default=False)
    )
    tenant_id = tenant_factory("Acme Ltda")
    repo.sync_tenant_prompt(tenant_id, prompt["id"])

    with pytest.raises(PromptInUseByTenantsError) as exc:
        service.delete_prompt(str(prompt["id"]))

    ids_bloqueadores = {b["id"] for b in exc.value.blockers}
    assert tenant_id in ids_bloqueadores
    assert all(b["type"] == "tenant" for b in exc.value.blockers)
    assert all(b["name"] for b in exc.value.blockers), "blockers devem trazer o nome, não só o id"


def test_blockers_listam_todos_os_tenants_vinculados(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Del B", "conteudo", is_default=False)
    )
    tenants = [tenant_factory(f"Tenant {i}") for i in range(3)]
    for tenant_id in tenants:
        repo.sync_tenant_prompt(tenant_id, prompt["id"])

    with pytest.raises(PromptInUseByTenantsError) as exc:
        service.delete_prompt(str(prompt["id"]))

    assert {b["id"] for b in exc.value.blockers} == set(tenants)


def test_prompt_e_vinculos_permanecem_intactos_apos_a_recusa(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Del C", "conteudo", is_default=False)
    )
    tenant_id = tenant_factory()
    repo.sync_tenant_prompt(tenant_id, prompt["id"])

    with pytest.raises(PromptInUseByTenantsError):
        service.delete_prompt(str(prompt["id"]))

    assert repo.get_prompt_by_id(str(prompt["id"])) is not None
    assert repo.get_active_prompt_by_tenant(tenant_id) is not None


def test_prompt_sem_vinculo_pode_ser_excluido(repo, service, db_cleanup):
    prompt = repo.create_prompt("EDI43 Del D", "conteudo", is_default=False)

    assert service.delete_prompt(str(prompt["id"])) is True
    assert repo.get_prompt_by_id(str(prompt["id"])) is None


def test_prompt_apenas_com_vinculos_inativos_pode_ser_excluido(repo, service, db_cleanup, tenant_factory):
    """Vínculo inativo é histórico, não configuração vigente — não bloqueia."""
    prompt_antigo = repo.create_prompt("EDI43 Del E antigo", "conteudo", is_default=False)
    prompt_novo = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Del E novo", "conteudo", is_default=False)
    )
    tenant_id = tenant_factory()

    repo.sync_tenant_prompt(tenant_id, prompt_antigo["id"])
    # Vincular o novo desativa o vínculo do antigo (mesmo node_type)
    repo.sync_tenant_prompt(tenant_id, prompt_novo["id"])

    assert service.delete_prompt(str(prompt_antigo["id"])) is True

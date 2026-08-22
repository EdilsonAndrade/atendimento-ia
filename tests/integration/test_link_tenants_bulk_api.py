"""Associação em massa prompt → N tenants (EDI-43 / FR-019-021)."""

import uuid

import pytest

from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import (
    PromptManagerService,
    PromptNotFoundError,
    TenantsNotFoundError,
)


@pytest.fixture
def service():
    return PromptManagerService(get_db_connection)


@pytest.fixture
def tenant_factory(repo, db_cleanup):
    criados = []

    def _factory():
        tenant_id = f"test-edi43-bulk-{uuid.uuid4().hex[:8]}"
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (tenant_id, "Bulk Tenant", "cal@test", []),
                )
        db_cleanup.track_tenant(tenant_id)
        criados.append(tenant_id)
        return tenant_id

    yield _factory

    for tenant_id in criados:
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


def test_vincula_prompt_a_varios_tenants_numa_operacao(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Bulk A", "conteudo", is_default=False)
    )
    tenants = [tenant_factory() for _ in range(3)]

    resultado = service.link_tenants_bulk(str(prompt["id"]), tenants)

    assert resultado["linked_count"] == 3
    assert resultado["node_type"] == "operational"
    for tenant_id in tenants:
        ativo = repo.get_active_prompt_by_tenant(tenant_id)
        assert ativo is not None and str(ativo["id"]) == str(prompt["id"])


def test_all_or_nothing_quando_um_tenant_nao_existe(repo, service, db_cleanup, tenant_factory):
    """Estado parcial é pior que falha: o admin teria que auditar manualmente o
    que foi aplicado e o que não foi."""
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Bulk B", "conteudo", is_default=False)
    )
    validos = [tenant_factory() for _ in range(2)]
    inexistente = "tenant-que-nao-existe-edi43"

    with pytest.raises(TenantsNotFoundError) as exc:
        service.link_tenants_bulk(str(prompt["id"]), validos + [inexistente])

    assert {b["id"] for b in exc.value.blockers} == {inexistente}
    for tenant_id in validos:
        assert repo.get_active_prompt_by_tenant(tenant_id) is None, "nenhum vínculo deveria ter sido aplicado"


def test_prompt_inexistente(service):
    with pytest.raises(PromptNotFoundError):
        service.link_tenants_bulk(str(uuid.uuid4()), ["qualquer"])


def test_substitui_vinculo_anterior_do_mesmo_node_type(repo, service, db_cleanup, tenant_factory):
    antigo = db_cleanup.track_prompt(repo.create_prompt("EDI43 Bulk antigo", "c", is_default=False))
    novo = db_cleanup.track_prompt(repo.create_prompt("EDI43 Bulk novo", "c", is_default=False))
    tenant_id = tenant_factory()
    repo.sync_tenant_prompt(tenant_id, antigo["id"])

    service.link_tenants_bulk(str(novo["id"]), [tenant_id])

    ativo = repo.get_active_prompt_by_tenant(tenant_id)
    assert str(ativo["id"]) == str(novo["id"])


def test_preserva_vinculos_de_outros_node_types(repo, service, db_cleanup, tenant_factory):
    """FR-021: aplicar um prompt operational em massa não pode derrubar o
    vínculo de chitchat dos mesmos tenants."""
    operational = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Bulk op", "c", is_default=False, node_type="operational")
    )
    chitchat = db_cleanup.track_prompt(
        repo.create_prompt("EDI43 Bulk chit", "c", is_default=False, node_type="chitchat")
    )
    tenant_id = tenant_factory()
    repo.sync_tenant_prompt(tenant_id, chitchat["id"])

    service.link_tenants_bulk(str(operational["id"]), [tenant_id])

    ainda_ativo = repo.get_active_prompt_by_tenant(tenant_id, node_type="chitchat")
    assert ainda_ativo is not None and str(ainda_ativo["id"]) == str(chitchat["id"])


def test_reaplicar_a_mesma_operacao_e_idempotente(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(repo.create_prompt("EDI43 Bulk idem", "c", is_default=False))
    tenants = [tenant_factory() for _ in range(2)]

    service.link_tenants_bulk(str(prompt["id"]), tenants)
    service.link_tenants_bulk(str(prompt["id"]), tenants)

    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM tenant_prompts WHERE prompt_id = %s AND tenant_id = ANY(%s)",
                (prompt["id"], tenants),
            )
            assert cur.fetchone()[0] == 2


def test_custom_override_aplicado_a_todos(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(repo.create_prompt("EDI43 Bulk ovr", "base", is_default=False))
    tenants = [tenant_factory() for _ in range(2)]

    service.link_tenants_bulk(str(prompt["id"]), tenants, custom_override="conteudo sobrescrito")

    for tenant_id in tenants:
        ativo = repo.get_active_prompt_by_tenant(tenant_id)
        assert ativo["conteudo"] == "conteudo sobrescrito"


# --- GET /prompts/{id}/tenants (EDI-44) -------------------------------------


def test_lista_tenants_vinculados_a_um_prompt(repo, service, db_cleanup, tenant_factory):
    prompt = db_cleanup.track_prompt(repo.create_prompt("EDI44 Lista", "c", is_default=False))
    tenants = [tenant_factory() for _ in range(2)]
    service.link_tenants_bulk(str(prompt["id"]), tenants)

    resultado = service.list_tenants_by_prompt(str(prompt["id"]))

    assert resultado["tenant_count"] == 2
    assert {t["id"] for t in resultado["tenants"]} == set(tenants)
    assert resultado["node_type"] == "operational"
    assert resultado["prompt_titulo"] == "EDI44 Lista"


def test_prompt_sem_tenants_devolve_lista_vazia(repo, service, db_cleanup):
    prompt = db_cleanup.track_prompt(repo.create_prompt("EDI44 Vazio", "c", is_default=False))

    resultado = service.list_tenants_by_prompt(str(prompt["id"]))

    assert resultado["tenant_count"] == 0
    assert resultado["tenants"] == []


def test_lista_ignora_vinculos_inativos(repo, service, db_cleanup, tenant_factory):
    """Coerente com o bloqueio de exclusão: vínculo inativo é histórico."""
    antigo = db_cleanup.track_prompt(repo.create_prompt("EDI44 Antigo", "c", is_default=False))
    novo = db_cleanup.track_prompt(repo.create_prompt("EDI44 Novo", "c", is_default=False))
    tenant_id = tenant_factory()
    repo.sync_tenant_prompt(tenant_id, antigo["id"])
    repo.sync_tenant_prompt(tenant_id, novo["id"])  # desativa o vínculo do antigo

    assert service.list_tenants_by_prompt(str(antigo["id"]))["tenant_count"] == 0
    assert service.list_tenants_by_prompt(str(novo["id"]))["tenant_count"] == 1


def test_prompt_inexistente_na_listagem(service):
    with pytest.raises(PromptNotFoundError):
        service.list_tenants_by_prompt(str(uuid.uuid4()))

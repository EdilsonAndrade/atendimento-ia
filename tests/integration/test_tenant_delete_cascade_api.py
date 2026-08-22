"""Exclusão em cascata de tenant (EDI-45).

Duas camadas de teste, como já é convenção neste projeto:

1. Comportamento real contra o Postgres, chamando o `TenantService` diretamente
   (mesmo padrão de `test_prompt_delete_guard_api.py` / `test_guardrail_delete_guard_api.py`).
2. Contrato HTTP (status code, formato do corpo) via `TestClient` com um
   `TenantService` fake (mesmo padrão de `test_tenant_search_api.py`).
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.tenant import router as tenant_router
from infrastructure.connection import get_db_connection
from modules.tenant.tenant_service import TenantService


@pytest.fixture
def service():
    return TenantService()


def _criar_tenant(repo, tenant_id, nome="Tenant EDI-45"):
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


def _apagar_tenant_se_sobrou(repo, tenant_id):
    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


@pytest.fixture
def tenant_factory(repo, db_cleanup):
    criados = []

    def _factory(nome="Tenant EDI-45"):
        tenant_id = f"test-edi45-{uuid.uuid4().hex[:8]}"
        _criar_tenant(repo, tenant_id, nome)
        db_cleanup.track_tenant(tenant_id)
        criados.append(tenant_id)
        return tenant_id

    yield _factory

    # Exclusão em cascata já deve ter apagado a maioria — isto é só rede de
    # segurança para tenants que um teste não chegou a excluir.
    for tenant_id in criados:
        _apagar_tenant_se_sobrou(repo, tenant_id)


# --- Comportamento real (service + banco) -----------------------------------


def test_prompt_e_guardrail_exclusivos_sao_excluidos_com_o_tenant(
    repo, service, db_cleanup, tenant_factory
):
    tenant_id = tenant_factory()
    prompt = db_cleanup.track_prompt(repo.create_prompt("EDI45 Excl", "conteudo", is_default=False))
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI45 Excl Guardrail", "regra", is_global=False)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_id, prompt["id"])

    deleted_id = service.delete_tenant_cascade(tenant_id)

    assert deleted_id == tenant_id
    assert service.get_tenant(tenant_id) is None
    assert repo.get_prompt_by_id(str(prompt["id"])) is None
    assert repo.get_guardrail_by_id(str(guardrail["id"])) is None


def test_prompt_compartilhado_com_outro_tenant_e_preservado(
    repo, service, db_cleanup, tenant_factory
):
    tenant_a = tenant_factory("Tenant A")
    tenant_b = tenant_factory("Tenant B")
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI45 Compartilhado", "conteudo", is_default=False)
    )
    repo.sync_tenant_prompt(tenant_a, prompt["id"])
    repo.sync_tenant_prompt(tenant_b, prompt["id"])

    service.delete_tenant_cascade(tenant_a)

    assert repo.get_prompt_by_id(str(prompt["id"])) is not None
    ativo_b = repo.get_active_prompt_by_tenant(tenant_b)
    assert ativo_b is not None and str(ativo_b["id"]) == str(prompt["id"])


def test_guardrail_global_e_preservado_mesmo_com_prompt_exclusivo_excluido(
    repo, service, db_cleanup, tenant_factory
):
    tenant_id = tenant_factory()
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI45 Prompt Global", "conteudo", is_default=False)
    )
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI45 Guardrail Global", "regra", is_global=True)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_id, prompt["id"])

    service.delete_tenant_cascade(tenant_id)

    assert repo.get_prompt_by_id(str(prompt["id"])) is None
    assert repo.get_guardrail_by_id(str(guardrail["id"])) is not None


def test_tenant_sem_vinculo_e_excluido_sem_efeitos_colaterais(repo, service, tenant_factory):
    tenant_id = tenant_factory()

    deleted_id = service.delete_tenant_cascade(tenant_id)

    assert deleted_id == tenant_id


def test_tenant_inexistente_devolve_none_sem_efeito_colateral(service):
    assert service.delete_tenant_cascade("tenant-que-nao-existe-edi45") is None


def test_impacto_bate_com_o_resultado_real_da_exclusao(repo, service, db_cleanup, tenant_factory):
    tenant_id = tenant_factory()
    prompt = db_cleanup.track_prompt(
        repo.create_prompt("EDI45 Impacto", "conteudo", is_default=False)
    )
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail("EDI45 Impacto Guardrail Global", "regra", is_global=True)
    )
    repo.sync_prompt_guardrails(prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_id, prompt["id"])

    impacto = service.get_delete_impact(tenant_id)
    assert {p["id"] for p in impacto["prompts_to_delete"]} == {prompt["id"]}
    assert impacto["prompts_to_unlink_only"] == []
    assert {g["id"] for g in impacto["guardrails_to_unlink_only"]} == {guardrail["id"]}
    assert impacto["guardrails_to_delete"] == []

    service.delete_tenant_cascade(tenant_id)

    assert repo.get_prompt_by_id(str(prompt["id"])) is None
    assert repo.get_guardrail_by_id(str(guardrail["id"])) is not None


def test_impacto_de_tenant_inexistente_devolve_none(service):
    assert service.get_delete_impact("tenant-que-nao-existe-edi45") is None


# --- Contrato HTTP (status code / formato) ----------------------------------


class _FakeTenantServiceImpact:
    def __init__(self, impact=None, deleted_id=None):
        self._impact = impact
        self._deleted_id = deleted_id

    def get_delete_impact(self, tenant_id):
        return self._impact

    def delete_tenant_cascade(self, tenant_id):
        return self._deleted_id


def _make_client(fake_service):
    app = FastAPI()
    app.include_router(tenant_router, prefix="/api/v1")
    app.dependency_overrides[TenantService] = lambda: fake_service
    return TestClient(app)


def test_delete_impact_404_para_tenant_inexistente():
    client = _make_client(_FakeTenantServiceImpact(impact=None))

    response = client.get("/api/v1/tenants/nao-existe/delete-impact")

    assert response.status_code == 404


def test_delete_impact_200_com_o_formato_esperado():
    impacto = {
        "prompts_to_delete": [{"id": "p1", "titulo": "P1", "node_type": "operational"}],
        "prompts_to_unlink_only": [],
        "guardrails_to_delete": [],
        "guardrails_to_unlink_only": [{"id": "g1", "titulo": "G1", "is_global": True}],
    }
    client = _make_client(_FakeTenantServiceImpact(impact=impacto))

    response = client.get("/api/v1/tenants/acme/delete-impact")

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "acme"
    assert body["prompts_to_delete"][0]["id"] == "p1"
    assert body["guardrails_to_unlink_only"][0]["is_global"] is True


def test_delete_404_para_tenant_inexistente():
    client = _make_client(_FakeTenantServiceImpact(deleted_id=None))

    response = client.delete("/api/v1/tenants/nao-existe")

    assert response.status_code == 404


def test_delete_200_quando_bem_sucedido():
    client = _make_client(_FakeTenantServiceImpact(deleted_id="acme"))

    response = client.delete("/api/v1/tenants/acme")

    assert response.status_code == 200
    assert response.json()["id"] == "acme"

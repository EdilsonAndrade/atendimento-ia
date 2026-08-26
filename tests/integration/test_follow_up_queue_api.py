"""EDI-53: `GET /api/v1/tenants/{tenant_id}/follow-up-queue`, `PATCH .../{id}` e o
endpoint global `GET /api/v1/follow-up-queue` (pré-requisito de painel do EDI-65) —
contrato HTTP com fake de repositório, sem exigir Postgres real (mesmo padrão de
test_conversation_history_api.py).
"""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.follow_up_queue import (
    get_customer_name_lookup,
    get_global_use_case,
    get_update_use_case,
    get_use_case,
    global_router as follow_up_queue_global_router,
    router as follow_up_queue_router,
)
from modules.follow_up.application.get_follow_up_queue import GetFollowUpQueueUseCase
from modules.follow_up.application.get_global_follow_up_queue import GetGlobalFollowUpQueueUseCase
from modules.follow_up.application.update_follow_up_entry import UpdateFollowUpEntryUseCase
from modules.follow_up.domain.follow_up_entry import FollowUpEntry


class FakeFollowUpQueueRepository:
    def __init__(self, entries_by_tenant=None):
        self._entries_by_tenant = entries_by_tenant or {}

    def _all_entries(self):
        return [e for entries in self._entries_by_tenant.values() for e in entries]

    def list_by_tenant(self, tenant_id, status=None, outcome=None):
        return self._filter(self._entries_by_tenant.get(tenant_id, []), status, outcome)

    def list_all(self, tenant_id=None, status=None, outcome=None):
        entries = self._entries_by_tenant.get(tenant_id, []) if tenant_id else self._all_entries()
        return self._filter(entries, status, outcome)

    @staticmethod
    def _filter(entries, status, outcome):
        if status is not None:
            entries = [e for e in entries if e.status.value == status]
        if outcome is not None:
            entries = [e for e in entries if e.outcome.value == outcome]
        return entries

    def save(self, entry):
        raise NotImplementedError

    def update(self, tenant_id, entry_id, status=None, draft_message=None, approved_by=None):
        for entry in self._all_entries():
            if entry.id == entry_id and entry.tenant_id == tenant_id:
                if status is not None:
                    entry.status = status
                if draft_message is not None:
                    entry.draft_message = draft_message
                entry.__post_init__()
                return entry
        return None


def make_client(entries_by_tenant=None, customer_names=None):
    app = FastAPI()
    app.include_router(follow_up_queue_router, prefix="/api/v1")
    app.include_router(follow_up_queue_global_router, prefix="/api/v1")
    fake_repo = FakeFollowUpQueueRepository(entries_by_tenant)
    customer_names = customer_names or {}
    app.dependency_overrides[get_use_case] = lambda: GetFollowUpQueueUseCase(fake_repo)
    app.dependency_overrides[get_global_use_case] = lambda: GetGlobalFollowUpQueueUseCase(fake_repo)
    app.dependency_overrides[get_update_use_case] = lambda: UpdateFollowUpEntryUseCase(fake_repo)
    app.dependency_overrides[get_customer_name_lookup] = lambda: (
        lambda base_thread_id: customer_names.get(base_thread_id)
    )
    return TestClient(app)


def _entry(tenant_id, outcome, status, entry_id):
    return FollowUpEntry(
        tenant_id=tenant_id,
        base_thread_id=f"{tenant_id}:123",
        active_thread_id=f"{tenant_id}:123#abc",
        outcome=outcome,
        summary="resumo",
        draft_message=None,
        status=status,
        id=entry_id,
        created_at=datetime(2026, 8, 26, 20, 0, 0, tzinfo=timezone.utc),
    )


def test_filtra_por_status_e_isola_por_tenant():
    client = make_client({
        "acme": [
            _entry("acme", "sem_resposta", "pendente", 1),
            _entry("acme", "fechado", "enviado", 2),
        ],
        "outra": [_entry("outra", "sem_resposta", "pendente", 3)],
    })

    response = client.get("/api/v1/tenants/acme/follow-up-queue?status=pendente")

    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == 1
    assert body["entries"][0]["tenant_id"] == "acme"


def test_filtra_por_outcome():
    client = make_client({
        "acme": [
            _entry("acme", "sem_resposta", "pendente", 1),
            _entry("acme", "pensando", "pendente", 2),
        ],
    })

    response = client.get("/api/v1/tenants/acme/follow-up-queue?outcome=pensando")

    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == 2


def test_outcome_invalido_devolve_422():
    client = make_client()

    response = client.get("/api/v1/tenants/acme/follow-up-queue?outcome=nao_existe")

    assert response.status_code == 422


def test_entrada_traz_customer_name_quando_disponivel():
    client = make_client(
        {"acme": [_entry("acme", "sem_resposta", "pendente", 1)]},
        customer_names={"acme:123": "Maria"},
    )

    response = client.get("/api/v1/tenants/acme/follow-up-queue")

    assert response.json()["entries"][0]["customer_name"] == "Maria"


def test_entrada_traz_customer_name_none_quando_nao_extraido():
    client = make_client({"acme": [_entry("acme", "sem_resposta", "pendente", 1)]})

    response = client.get("/api/v1/tenants/acme/follow-up-queue")

    assert response.json()["entries"][0]["customer_name"] is None


def test_sem_filtro_devolve_todos_status_do_tenant():
    client = make_client({
        "acme": [
            _entry("acme", "sem_resposta", "pendente", 1),
            _entry("acme", "fechado", "enviado", 2),
        ]
    })

    response = client.get("/api/v1/tenants/acme/follow-up-queue")

    assert len(response.json()["entries"]) == 2


def test_status_invalido_devolve_422():
    client = make_client()

    response = client.get("/api/v1/tenants/acme/follow-up-queue?status=nao_existe")

    assert response.status_code == 422


def test_sem_registros_devolve_lista_vazia():
    client = make_client()

    response = client.get("/api/v1/tenants/acme/follow-up-queue")

    assert response.json()["entries"] == []


def test_patch_aprova_registro():
    client = make_client({"acme": [_entry("acme", "sem_resposta", "pendente", 1)]})

    response = client.patch("/api/v1/tenants/acme/follow-up-queue/1", json={"status": "aprovado"})

    assert response.status_code == 200
    assert response.json()["status"] == "aprovado"


def test_patch_edita_draft_message():
    client = make_client({"acme": [_entry("acme", "sem_resposta", "pendente", 1)]})

    response = client.patch(
        "/api/v1/tenants/acme/follow-up-queue/1", json={"draft_message": "texto revisado"}
    )

    assert response.status_code == 200
    assert response.json()["draft_message"] == "texto revisado"


def test_patch_registro_inexistente_devolve_404():
    client = make_client()

    response = client.patch("/api/v1/tenants/acme/follow-up-queue/999", json={"status": "aprovado"})

    assert response.status_code == 404


def test_patch_status_invalido_devolve_422():
    client = make_client({"acme": [_entry("acme", "sem_resposta", "pendente", 1)]})

    response = client.patch(
        "/api/v1/tenants/acme/follow-up-queue/1", json={"status": "nao_existe"}
    )

    assert response.status_code == 422


def test_patch_sem_campos_devolve_422():
    client = make_client({"acme": [_entry("acme", "sem_resposta", "pendente", 1)]})

    response = client.patch("/api/v1/tenants/acme/follow-up-queue/1", json={})

    assert response.status_code == 422


def test_patch_nao_atualiza_registro_de_outro_tenant():
    client = make_client({"outra": [_entry("outra", "sem_resposta", "pendente", 1)]})

    response = client.patch("/api/v1/tenants/acme/follow-up-queue/1", json={"status": "aprovado"})

    assert response.status_code == 404


def test_global_lista_de_todos_os_tenants():
    client = make_client({
        "acme": [_entry("acme", "sem_resposta", "pendente", 1)],
        "outra": [_entry("outra", "fechado", "enviado", 2)],
    })

    response = client.get("/api/v1/follow-up-queue")

    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 2
    tenant_ids = {e["tenant_id"] for e in body["entries"]}
    assert tenant_ids == {"acme", "outra"}


def test_global_filtra_por_tenant_id():
    client = make_client({
        "acme": [_entry("acme", "sem_resposta", "pendente", 1)],
        "outra": [_entry("outra", "fechado", "enviado", 2)],
    })

    response = client.get("/api/v1/follow-up-queue?tenant_id=acme")

    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["tenant_id"] == "acme"


def test_global_filtra_por_status_e_outcome():
    client = make_client({
        "acme": [
            _entry("acme", "sem_resposta", "pendente", 1),
            _entry("acme", "pensando", "pendente", 2),
            _entry("acme", "pensando", "aprovado", 3),
        ],
    })

    response = client.get("/api/v1/follow-up-queue?status=pendente&outcome=pensando")

    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == 2


def test_global_status_invalido_devolve_422():
    client = make_client()

    response = client.get("/api/v1/follow-up-queue?status=nao_existe")

    assert response.status_code == 422


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

"""EDI-63: CRUD de `global_notification_recipients` — contrato HTTP com um fake
repositório em memória (mesmo padrão dos demais testes de integração deste
projeto), sem exigir Postgres real.
"""
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.global_notification_recipients import (
    get_repository,
    router as recipients_router,
)


class FakeGlobalRecipients:
    def __init__(self):
        self._rows = {}
        self._next_id = 1

    def list_all(self):
        return list(self._rows.values())

    def email_exists(self, email):
        return any(row["email"] == email for row in self._rows.values())

    def create(self, email):
        row = {"id": self._next_id, "email": email, "active": True, "created_at": datetime.now(timezone.utc)}
        self._rows[self._next_id] = row
        self._next_id += 1
        return row

    def update(self, recipient_id, active):
        row = self._rows.get(recipient_id)
        if row is None:
            return None
        row["active"] = active
        return row

    def delete(self, recipient_id):
        return self._rows.pop(recipient_id, None) and recipient_id


def make_client():
    fake = FakeGlobalRecipients()
    app = FastAPI()
    app.include_router(recipients_router, prefix="/api/v1")
    app.dependency_overrides[get_repository] = lambda: fake
    return TestClient(app), fake


def test_crud_completo():
    client, _fake = make_client()

    created = client.post("/api/v1/global-notification-recipients/", json={"email": "ops@interasisai.com.br"})
    assert created.status_code == 201
    recipient_id = created.json()["id"]
    assert created.json()["active"] is True

    listed = client.get("/api/v1/global-notification-recipients/")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.put(f"/api/v1/global-notification-recipients/{recipient_id}", json={"active": False})
    assert updated.status_code == 200
    assert updated.json()["active"] is False

    deleted = client.delete(f"/api/v1/global-notification-recipients/{recipient_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": recipient_id, "message": "Recipient deleted successfully"}

    assert client.get("/api/v1/global-notification-recipients/").json() == []


def test_criar_email_duplicado_devolve_409():
    client, _fake = make_client()
    client.post("/api/v1/global-notification-recipients/", json={"email": "ops@interasisai.com.br"})

    response = client.post("/api/v1/global-notification-recipients/", json={"email": "ops@interasisai.com.br"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_atualizar_inexistente_devolve_404():
    client, _fake = make_client()

    response = client.put("/api/v1/global-notification-recipients/999", json={"active": False})

    assert response.status_code == 404


def test_excluir_inexistente_devolve_404():
    client, _fake = make_client()

    response = client.delete("/api/v1/global-notification-recipients/999")

    assert response.status_code == 404

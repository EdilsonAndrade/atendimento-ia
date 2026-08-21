from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import prompt_manager as prompt_manager_module


def make_client():
    app = FastAPI()
    app.include_router(prompt_manager_module.router, prefix="/api/v1")
    return TestClient(app)


def test_delete_guardrail_removes_it(db_cleanup):
    client = make_client()
    created = client.post(
        "/api/v1/prompt-manager/guardrails",
        json={"titulo": "Guardrail EDI-41", "conteudo": "c", "is_global": False},
    ).json()
    db_cleanup.track_guardrail(created)

    response = client.delete(f"/api/v1/prompt-manager/guardrails/{created['id']}")

    assert response.status_code == 204
    remaining_ids = [g["id"] for g in client.get("/api/v1/prompt-manager/guardrails").json()]
    assert created["id"] not in remaining_ids


def test_delete_guardrail_returns_404_when_not_found():
    client = make_client()

    response = client.delete("/api/v1/prompt-manager/guardrails/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_guardrail_linked_to_prompt_removes_association(db_cleanup):
    client = make_client()
    guardrail = client.post(
        "/api/v1/prompt-manager/guardrails",
        json={"titulo": "Guardrail Vinculado EDI-41", "conteudo": "c", "is_global": False},
    ).json()
    db_cleanup.track_guardrail(guardrail)

    prompt = client.post(
        "/api/v1/prompt-manager/prompts",
        json={
            "titulo": "Prompt EDI-41",
            "conteudo": "conteudo {guardrails}",
            "is_default": False,
            "guardrail_ids": [guardrail["id"]],
        },
    ).json()
    db_cleanup.track_prompt(prompt)

    response = client.delete(f"/api/v1/prompt-manager/guardrails/{guardrail['id']}")

    assert response.status_code == 204

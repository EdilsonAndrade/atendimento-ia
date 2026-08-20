from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import prompt_manager as prompt_manager_module


def make_client():
    app = FastAPI()
    app.include_router(prompt_manager_module.router, prefix="/api/v1")
    return TestClient(app)


def test_create_prompt_persists_node_type(db_cleanup):
    client = make_client()

    response = client.post(
        "/api/v1/prompt-manager/prompts",
        json={
            "titulo": "Chitchat EDI-42",
            "conteudo": "conteudo {guardrails}",
            "is_default": False,
            "node_type": "chitchat",
            "guardrail_ids": [],
        },
    )
    db_cleanup.track_prompt(response.json())

    assert response.status_code == 200
    body = response.json()
    assert body["node_type"] == "chitchat"


def test_create_prompt_defaults_node_type_to_operational_when_omitted(db_cleanup):
    client = make_client()

    response = client.post(
        "/api/v1/prompt-manager/prompts",
        json={"titulo": "Sem node_type", "conteudo": "c", "is_default": False, "guardrail_ids": []},
    )
    db_cleanup.track_prompt(response.json())

    assert response.status_code == 200
    assert response.json()["node_type"] == "operational"


def test_create_prompt_rejects_invalid_node_type():
    client = make_client()

    response = client.post(
        "/api/v1/prompt-manager/prompts",
        json={"titulo": "Inválido", "conteudo": "c", "is_default": False, "node_type": "nao_existe", "guardrail_ids": []},
    )

    # Rejeitado na validação -> nada é criado no banco, nada para limpar
    assert response.status_code == 422


def test_update_prompt_persists_node_type(db_cleanup):
    client = make_client()
    created = client.post(
        "/api/v1/prompt-manager/prompts",
        json={"titulo": "Institutional EDI-42", "conteudo": "c", "is_default": False, "node_type": "institutional", "guardrail_ids": []},
    ).json()
    db_cleanup.track_prompt(created)

    response = client.put(
        f"/api/v1/prompt-manager/prompts/{created['id']}",
        json={"titulo": "Institutional EDI-42 v2", "conteudo": "c2", "is_default": False, "node_type": "institutional", "guardrail_ids": []},
    )

    assert response.status_code == 200
    assert response.json()["node_type"] == "institutional"


def test_get_prompts_filters_by_node_type_query_param(db_cleanup):
    client = make_client()
    db_cleanup.track_prompt(client.post(
        "/api/v1/prompt-manager/prompts",
        json={"titulo": "Filtro Op", "conteudo": "c", "is_default": False, "node_type": "operational", "guardrail_ids": []},
    ).json())
    db_cleanup.track_prompt(client.post(
        "/api/v1/prompt-manager/prompts",
        json={"titulo": "Filtro Chit", "conteudo": "c", "is_default": False, "node_type": "chitchat", "guardrail_ids": []},
    ).json())

    response = client.get("/api/v1/prompt-manager/prompts?node_type=chitchat")

    assert response.status_code == 200
    assert all(p["node_type"] == "chitchat" for p in response.json())

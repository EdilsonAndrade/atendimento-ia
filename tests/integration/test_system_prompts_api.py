"""EDI-71: integração dos endpoints /api/v1/system-prompts com o Postgres real.

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a
migration 0010_system_prompts já aplicada (semeia as 4 chaves usadas aqui).

Rodar com: pytest tests/integration/test_system_prompts_api.py -v
"""
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.connection import DB_URI
from app.api.v1.endpoints import system_prompts as system_prompts_module


def make_client():
    app = FastAPI()
    app.include_router(system_prompts_module.router, prefix="/api/v1")
    return TestClient(app)


def _snapshot(prompt_key: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_version, last_version FROM system_prompts WHERE prompt_key = %s",
                (prompt_key,),
            )
            return cur.fetchone()


def _restore(prompt_key: str, current_version: str, last_version: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE system_prompts SET current_version = %s, last_version = %s WHERE prompt_key = %s",
                (current_version, last_version, prompt_key),
            )


@pytest.fixture
def restaurar_groundedness_rule():
    original = _snapshot("groundedness_rule")
    yield
    if original:
        _restore("groundedness_rule", *original)


def test_list_system_prompts_traz_as_4_chaves_semeadas():
    client = make_client()

    response = client.get("/api/v1/system-prompts")

    assert response.status_code == 200
    chaves = {row["prompt_key"] for row in response.json()}
    assert chaves == {
        "routing_agent",
        "groundedness_rule",
        "chitchat_no_knowledge_rule",
        "booking_integrity_rule",
    }


def test_get_system_prompt_por_chave():
    client = make_client()

    response = client.get("/api/v1/system-prompts/booking_integrity_rule")

    assert response.status_code == 200
    assert response.json()["prompt_key"] == "booking_integrity_rule"


def test_get_system_prompt_404_para_chave_invalida():
    client = make_client()

    response = client.get("/api/v1/system-prompts/nao_existe")

    assert response.status_code == 422  # rejeitado pelo Literal do schema


def test_update_e_rollback_ciclo_completo(restaurar_groundedness_rule):
    client = make_client()
    original_current, original_last = _snapshot("groundedness_rule")

    update_response = client.put(
        "/api/v1/system-prompts/groundedness_rule",
        json={"conteudo": "novo conteudo de teste EDI-71"},
    )
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["current_version"] == "novo conteudo de teste EDI-71"
    assert body["last_version"] == original_current

    rollback_response = client.post("/api/v1/system-prompts/groundedness_rule/rollback")
    assert rollback_response.status_code == 200
    body = rollback_response.json()
    assert body["current_version"] == original_current
    assert body["last_version"] == "novo conteudo de teste EDI-71"


def test_update_rejeita_conteudo_vazio(restaurar_groundedness_rule):
    client = make_client()

    response = client.put(
        "/api/v1/system-prompts/groundedness_rule",
        json={"conteudo": "   "},
    )

    assert response.status_code == 400


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

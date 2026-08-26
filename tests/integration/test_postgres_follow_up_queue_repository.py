"""EDI-53: PostgresFollowUpQueueRepository contra um Postgres real.

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a migration
0009_conversation_followup já aplicada.

Rodar com: pytest tests/integration/test_postgres_follow_up_queue_repository.py -v
"""
import uuid

import psycopg
import pytest

from infrastructure.connection import DB_URI
from modules.follow_up.domain.follow_up_entry import FollowUpEntry, Outcome
from modules.follow_up.infrastructure.postgres_follow_up_queue_repository import (
    PostgresFollowUpQueueRepository,
)


def _limpar(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM follow_up_queue WHERE tenant_id = %s", (tenant_id,))


def test_save_e_list_by_tenant():
    tenant_id = f"tenant_teste_edi53_fu_{uuid.uuid4().hex[:8]}"
    active_thread_id = f"{tenant_id}:123#abc"
    repository = PostgresFollowUpQueueRepository()

    try:
        criado = repository.save(FollowUpEntry(
            tenant_id=tenant_id,
            base_thread_id=f"{tenant_id}:123",
            active_thread_id=active_thread_id,
            outcome=Outcome.SEM_RESPOSTA,
            summary="Cliente não respondeu.",
            draft_message="Oi! Vi que você perguntou...",
        ))

        assert criado is True
        entradas = repository.list_by_tenant(tenant_id)
        assert len(entradas) == 1
        assert entradas[0].outcome == Outcome.SEM_RESPOSTA
        assert entradas[0].draft_message == "Oi! Vi que você perguntou..."
    finally:
        _limpar(tenant_id)


def test_reprocessar_mesma_sessao_nao_duplica():
    tenant_id = f"tenant_teste_edi53_fu_dup_{uuid.uuid4().hex[:8]}"
    active_thread_id = f"{tenant_id}:123#abc"
    repository = PostgresFollowUpQueueRepository()

    try:
        entry = FollowUpEntry(
            tenant_id=tenant_id,
            base_thread_id=f"{tenant_id}:123",
            active_thread_id=active_thread_id,
            outcome=Outcome.PENSANDO,
            summary="Cliente disse que ia pensar.",
            draft_message="Oi de novo!",
        )

        primeira = repository.save(entry)
        segunda = repository.save(entry)

        assert primeira is True
        assert segunda is False
        assert len(repository.list_by_tenant(tenant_id)) == 1
    finally:
        _limpar(tenant_id)


def test_filtra_por_status():
    tenant_id = f"tenant_teste_edi53_fu_status_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:1", active_thread_id=f"{tenant_id}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s1", draft_message="d1",
        ))
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:2", active_thread_id=f"{tenant_id}:2#a",
            outcome=Outcome.FECHADO, summary="s2",
        ))

        pendentes = repository.list_by_tenant(tenant_id, status="pendente")

        assert len(pendentes) == 2  # status default é 'pendente' para ambos
        assert repository.list_by_tenant(tenant_id, status="enviado") == []
    finally:
        _limpar(tenant_id)


def test_filtra_por_outcome():
    tenant_id = f"tenant_teste_edi53_fu_outcome_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:1", active_thread_id=f"{tenant_id}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s1", draft_message="d1",
        ))
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:2", active_thread_id=f"{tenant_id}:2#a",
            outcome=Outcome.PENSANDO, summary="s2", draft_message="d2",
        ))

        resultado = repository.list_by_tenant(tenant_id, outcome="pensando")

        assert len(resultado) == 1
        assert resultado[0].outcome == Outcome.PENSANDO
    finally:
        _limpar(tenant_id)


def test_list_all_sem_tenant_id_devolve_de_todos():
    tenant_a = f"tenant_teste_edi53_fu_all_a_{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant_teste_edi53_fu_all_b_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_a, base_thread_id=f"{tenant_a}:1", active_thread_id=f"{tenant_a}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s1",
        ))
        repository.save(FollowUpEntry(
            tenant_id=tenant_b, base_thread_id=f"{tenant_b}:1", active_thread_id=f"{tenant_b}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s2",
        ))

        resultado_a = repository.list_all(tenant_id=tenant_a)
        todos = repository.list_all()

        assert len(resultado_a) == 1
        assert resultado_a[0].tenant_id == tenant_a
        tenant_ids_presentes = {e.tenant_id for e in todos}
        assert {tenant_a, tenant_b} <= tenant_ids_presentes
    finally:
        _limpar(tenant_a)
        _limpar(tenant_b)


def test_update_aprova_e_seta_approved_at():
    tenant_id = f"tenant_teste_edi53_fu_upd_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:1", active_thread_id=f"{tenant_id}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s1", draft_message="d1",
        ))
        entry_id = repository.list_by_tenant(tenant_id)[0].id

        atualizado = repository.update(tenant_id, entry_id, status="aprovado", approved_by="admin@acme.com")

        assert atualizado.status.value == "aprovado"
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT approved_by, approved_at FROM follow_up_queue WHERE id = %s", (entry_id,)
                )
                approved_by, approved_at = cur.fetchone()
        assert approved_by == "admin@acme.com"
        assert approved_at is not None
    finally:
        _limpar(tenant_id)


def test_update_edita_draft_message_sem_mudar_status():
    tenant_id = f"tenant_teste_edi53_fu_upd_draft_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:1", active_thread_id=f"{tenant_id}:1#a",
            outcome=Outcome.PENSANDO, summary="s1", draft_message="original",
        ))
        entry_id = repository.list_by_tenant(tenant_id)[0].id

        atualizado = repository.update(tenant_id, entry_id, draft_message="revisado")

        assert atualizado.draft_message == "revisado"
        assert atualizado.status.value == "pendente"
    finally:
        _limpar(tenant_id)


def test_update_registro_inexistente_devolve_none():
    repository = PostgresFollowUpQueueRepository()

    assert repository.update("tenant_inexistente", 999999, status="aprovado") is None


def test_update_nao_atualiza_registro_de_outro_tenant():
    tenant_id = f"tenant_teste_edi53_fu_upd_iso_{uuid.uuid4().hex[:8]}"
    repository = PostgresFollowUpQueueRepository()

    try:
        repository.save(FollowUpEntry(
            tenant_id=tenant_id, base_thread_id=f"{tenant_id}:1", active_thread_id=f"{tenant_id}:1#a",
            outcome=Outcome.SEM_RESPOSTA, summary="s1", draft_message="d1",
        ))
        entry_id = repository.list_by_tenant(tenant_id)[0].id

        resultado = repository.update("outro_tenant_qualquer", entry_id, status="aprovado")

        assert resultado is None
    finally:
        _limpar(tenant_id)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

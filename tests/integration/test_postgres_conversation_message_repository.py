"""EDI-53: PostgresConversationMessageRepository contra um Postgres real.

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a migration
0009_conversation_followup já aplicada.

Rodar com: pytest tests/integration/test_postgres_conversation_message_repository.py -v
"""
import uuid
from datetime import timedelta

import psycopg
import pytest

from infrastructure.connection import DB_URI
from modules.conversation_history.domain.conversation_message import ConversationMessage
from modules.conversation_history.infrastructure.postgres_conversation_message_repository import (
    PostgresConversationMessageRepository,
)


def _limpar(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversation_messages WHERE tenant_id = %s", (tenant_id,))


def test_save_turn_e_list_by_thread_devolvem_em_ordem():
    tenant_id = f"tenant_teste_edi53_{uuid.uuid4().hex[:8]}"
    base_thread_id = f"{tenant_id}:5511999998888"
    active_thread_id = f"{base_thread_id}#abc"
    repository = PostgresConversationMessageRepository()

    try:
        repository.save_turn(
            ConversationMessage(tenant_id, base_thread_id, active_thread_id, "human", "Oi, quero agendar"),
            ConversationMessage(tenant_id, base_thread_id, active_thread_id, "ai", "Claro! Qual serviço?"),
        )

        mensagens = repository.list_by_thread(tenant_id, base_thread_id)

        assert [m.role for m in mensagens] == ["human", "ai"]
        assert mensagens[0].content == "Oi, quero agendar"
        assert mensagens[1].content == "Claro! Qual serviço?"
    finally:
        _limpar(tenant_id)


def test_list_by_thread_isola_por_tenant():
    tenant_a = f"tenant_teste_edi53_a_{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant_teste_edi53_b_{uuid.uuid4().hex[:8]}"
    base_thread_id = "mesmo_thread:123"  # mesmo sufixo de thread, tenants diferentes
    repository = PostgresConversationMessageRepository()

    try:
        repository.save_turn(
            ConversationMessage(tenant_a, base_thread_id, f"{base_thread_id}#a", "human", "do tenant A"),
            ConversationMessage(tenant_a, base_thread_id, f"{base_thread_id}#a", "ai", "resposta A"),
        )
        repository.save_turn(
            ConversationMessage(tenant_b, base_thread_id, f"{base_thread_id}#b", "human", "do tenant B"),
            ConversationMessage(tenant_b, base_thread_id, f"{base_thread_id}#b", "ai", "resposta B"),
        )

        mensagens_a = repository.list_by_thread(tenant_a, base_thread_id)

        assert len(mensagens_a) == 2
        assert all("A" in m.content or "do tenant A" == m.content for m in mensagens_a)
    finally:
        _limpar(tenant_a)
        _limpar(tenant_b)


def test_purge_older_than_respeita_retention_por_tenant():
    tenant_novo = f"tenant_teste_edi53_novo_{uuid.uuid4().hex[:8]}"
    tenant_antigo = f"tenant_teste_edi53_antigo_{uuid.uuid4().hex[:8]}"
    repository = PostgresConversationMessageRepository()

    try:
        with psycopg.connect(DB_URI, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_messages
                        (tenant_id, base_thread_id, active_thread_id, role, content, created_at)
                    VALUES
                        (%s, %s, %s, 'human', 'mensagem antiga', NOW() - INTERVAL '40 days'),
                        (%s, %s, %s, 'human', 'mensagem recente', NOW())
                    """,
                    (
                        tenant_antigo, f"{tenant_antigo}:1", f"{tenant_antigo}:1#a",
                        tenant_novo, f"{tenant_novo}:1", f"{tenant_novo}:1#a",
                    ),
                )

        apagadas = repository.purge_older_than(tenant_antigo, retention_days=30)

        assert apagadas == 1
        restantes_antigo = repository.list_by_thread(tenant_antigo, f"{tenant_antigo}:1")
        assert restantes_antigo == []
        restantes_novo = repository.list_by_thread(tenant_novo, f"{tenant_novo}:1")
        assert len(restantes_novo) == 1
    finally:
        _limpar(tenant_antigo)
        _limpar(tenant_novo)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

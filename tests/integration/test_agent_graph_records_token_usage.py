"""
Integration test do EDI-60: confirma que o wiring real em modules/ia/agent_graph.py
(routing_agent, chitchat_node) grava um registro em chat_token_usage quando o LLM é
chamado. A chamada ao LLM em si é monkeypatchada (resposta fake com usage_metadata
determinístico) para o teste ser rápido e não depender de rede/custo real — a parte
testada de verdade é a integração entre o nó do grafo e o Postgres real
(RecordTokenUsageUseCase + PostgresTokenUsageRepository reais, sem mocks).

PRÉ-REQUISITO: Postgres acessível via POSTGRES_DATABASE_URI/.env, com a migration
0007_chat_token_usage já aplicada.

Rodar com: pytest tests/integration/test_agent_graph_records_token_usage.py -v
"""
import uuid

import psycopg
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from infrastructure.connection import DB_URI
from modules.ia import agent_graph


class _FakeAIResponse:
    def __init__(self, content: str, usage_metadata: dict):
        self.content = content
        self.usage_metadata = usage_metadata
        self.tool_calls = []


def _limpar_registros(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_token_usage WHERE tenant_id = %s", (tenant_id,))


def _buscar_registros(tenant_id: str):
    with psycopg.connect(DB_URI, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT node_type, input_tokens, output_tokens FROM chat_token_usage WHERE tenant_id = %s",
                (tenant_id,),
            )
            return cur.fetchall()


def test_routing_agent_grava_registro_de_custo(monkeypatch):
    tenant_id = f"tenant_teste_edi60_routing_{uuid.uuid4().hex[:8]}"
    base_thread_id = f"{tenant_id}:sessao_1"

    monkeypatch.setattr(
        agent_graph.llm, "invoke",
        lambda messages: _FakeAIResponse(
            "OPERATIONAL",
            {"input_tokens": 42, "output_tokens": 3, "total_tokens": 45},
        ),
    )

    state = {"messages": [HumanMessage(content="quero marcar um horário")]}
    config = {"configurable": {"tenant_id": tenant_id, "base_thread_id": base_thread_id, "thread_id": f"{base_thread_id}#abc"}}

    try:
        agent_graph.routing_agent(state, config)

        registros = _buscar_registros(tenant_id)
        assert len(registros) == 1
        assert registros[0] == ("routing_agent", 42, 3)
    finally:
        _limpar_registros(tenant_id)


def test_chitchat_node_grava_registro_de_custo(monkeypatch):
    tenant_id = f"tenant_teste_edi60_chitchat_{uuid.uuid4().hex[:8]}"
    base_thread_id = f"{tenant_id}:sessao_1"

    monkeypatch.setattr(
        agent_graph.llm, "invoke",
        lambda messages: _FakeAIResponse(
            "Oi! Como posso ajudar?",
            {"input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
        ),
    )

    state = {"messages": [HumanMessage(content="oi tudo bem?")]}
    config = {"configurable": {"tenant_id": tenant_id, "base_thread_id": base_thread_id, "thread_id": f"{base_thread_id}#abc"}}

    try:
        agent_graph.chitchat_node(state, config)

        registros = _buscar_registros(tenant_id)
        assert len(registros) == 1
        assert registros[0] == ("chitchat_node", 20, 8)
    finally:
        _limpar_registros(tenant_id)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

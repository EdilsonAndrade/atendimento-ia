import json
import sys
import types

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from modules.ia import thread_session


class _FakeCursor:
    def __init__(self, sink: list):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        self._sink.append((query, params))


class _FakeConn:
    def __init__(self, sink: list):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return _FakeCursor(self._sink)


def _fake_psycopg_connect(sink: list):
    def _connect(*args, **kwargs):
        return _FakeConn(sink)
    return _connect


def test_generate_and_store_session_summary_persiste_resumo_e_fatos(monkeypatch):
    executed = []

    monkeypatch.setattr(
        thread_session, "_get_session_messages",
        lambda active_thread_id: [HumanMessage(content="Oi, meu nome é Ana")],
    )
    monkeypatch.setattr(
        thread_session, "_summarize_session",
        lambda messages: {
            "resumo": "Cliente Ana perguntou sobre corte de cabelo.",
            "fatos": {"nome": "Ana", "interesse": "corte de cabelo", "objecao": None, "resultado": "agendou"},
        },
    )
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))

    thread_session.generate_and_store_session_summary("tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert len(executed) == 1
    query, params = executed[0]
    assert "INSERT INTO chat_thread_summaries" in query
    base_thread_id, resumo, fatos_json, sessao_thread_id = params
    assert base_thread_id == "tenant_x:sessao_1"
    assert resumo == "Cliente Ana perguntou sobre corte de cabelo."
    assert json.loads(fatos_json)["nome"] == "Ana"
    assert sessao_thread_id == "tenant_x:sessao_1#abc123"


def test_generate_and_store_session_summary_nao_propaga_falha_do_resumo(monkeypatch):
    """FR-010: uma falha na geração do resumo não pode travar a expiração/nova sessão."""
    executed = []

    monkeypatch.setattr(
        thread_session, "_get_session_messages",
        lambda active_thread_id: [HumanMessage(content="oi")],
    )

    def _summarize_quebrado(messages):
        raise RuntimeError("falha simulada na chamada ao LLM de resumo")

    monkeypatch.setattr(thread_session, "_summarize_session", _summarize_quebrado)
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))

    # Não deve levantar exceção nenhuma.
    thread_session.generate_and_store_session_summary("tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert executed == []  # nenhuma tentativa de persistência após a falha


def test_generate_and_store_session_summary_ignora_sessao_sem_mensagens(monkeypatch):
    executed = []
    monkeypatch.setattr(thread_session, "_get_session_messages", lambda active_thread_id: [])
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))

    thread_session.generate_and_store_session_summary("tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert executed == []


def test_summarize_session_nao_inventa_campos_ausentes(monkeypatch):
    """FR-011: campos não identificáveis na conversa devem ficar None, nunca inventados."""

    class _FakeResponse:
        content = json.dumps({
            "resumo": "Cliente só perguntou o horário de funcionamento.",
            "fatos": {"nome": None, "interesse": None, "objecao": None, "resultado": "apenas_duvida"},
        })

    class _FakeLLM:
        def invoke(self, messages):
            return _FakeResponse()

    fake_agent_graph = types.ModuleType("modules.ia.agent_graph")
    fake_agent_graph.llm = _FakeLLM()
    monkeypatch.setitem(sys.modules, "modules.ia.agent_graph", fake_agent_graph)

    resultado = thread_session._summarize_session([
        HumanMessage(content="Vocês abrem que horas?"),
        AIMessage(content="Abrimos às 9h."),
    ])

    assert resultado["fatos"]["nome"] is None
    assert resultado["fatos"]["interesse"] is None
    assert resultado["fatos"]["resultado"] == "apenas_duvida"


def test_summarize_session_com_historico_vazio_nao_chama_llm(monkeypatch):
    chamadas = []

    class _FakeLLM:
        def invoke(self, messages):
            chamadas.append(messages)
            raise AssertionError("não deveria chamar o LLM para histórico sem conteúdo relevante")

    fake_agent_graph = types.ModuleType("modules.ia.agent_graph")
    fake_agent_graph.llm = _FakeLLM()
    monkeypatch.setitem(sys.modules, "modules.ia.agent_graph", fake_agent_graph)

    resultado = thread_session._summarize_session([])

    assert resultado == {"resumo": "", "fatos": {}}
    assert chamadas == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

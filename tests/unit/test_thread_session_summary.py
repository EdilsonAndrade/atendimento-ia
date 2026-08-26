import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from modules.ia import thread_session


class _FakeTenantService:
    """Evita a instanciação real de TenantService (conexão de DB) dentro de
    generate_and_store_session_summary — a busca de oferta_vigente (EDI-53) não é
    o que estes testes de orquestração cobrem."""

    def get_tenant_by_id(self, tenant_id):
        return None


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
        lambda messages, tenant_id, base_thread_id, active_thread_id,
               oferta_vigente_texto=None, oferta_vigente_validade=None: {
            "resumo": "Cliente Ana perguntou sobre corte de cabelo.",
            "fatos": {"nome": "Ana", "interesse": "corte de cabelo", "objecao": None, "resultado": "agendou"},
        },
    )
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))
    monkeypatch.setattr("modules.tenant.tenant_service.TenantService", _FakeTenantService)

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

    def _summarize_quebrado(*args, **kwargs):
        raise RuntimeError("falha simulada na chamada ao LLM de resumo")

    monkeypatch.setattr(thread_session, "_summarize_session", _summarize_quebrado)
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))
    monkeypatch.setattr("modules.tenant.tenant_service.TenantService", _FakeTenantService)

    # Não deve levantar exceção nenhuma.
    thread_session.generate_and_store_session_summary("tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert executed == []  # nenhuma tentativa de persistência após a falha


def test_generate_and_store_session_summary_ignora_sessao_sem_mensagens(monkeypatch):
    executed = []
    monkeypatch.setattr(thread_session, "_get_session_messages", lambda active_thread_id: [])
    monkeypatch.setattr(thread_session.psycopg, "connect", _fake_psycopg_connect(executed))

    thread_session.generate_and_store_session_summary("tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert executed == []


def test_summarize_session_monta_texto_da_conversa_e_delega_ao_use_case(monkeypatch):
    """A extração de resumo/fatos/outcome em si (FR-011: nunca inventar campo ausente)
    já é coberta em test_classify_session_outcome_use_case.py e
    test_llm_session_outcome_classifier_prompt.py. Aqui a responsabilidade própria de
    `_summarize_session` é testada: montar o texto da conversa (linhas de Cliente/
    Atendente/ferramenta) e delegar para ClassifySessionOutcomeUseCase com os
    parâmetros corretos (EDI-53)."""
    capturado = {}

    class _FakeUseCase:
        def __init__(self, repository, classifier):
            pass

        def execute(self, tenant_id, base_thread_id, active_thread_id, conversation_text,
                    oferta_vigente_texto, oferta_vigente_validade):
            capturado["args"] = (
                tenant_id, base_thread_id, active_thread_id, conversation_text,
                oferta_vigente_texto, oferta_vigente_validade,
            )
            return {"resumo": "Cliente só perguntou o horário de funcionamento.", "fatos": {"nome": None}}

    monkeypatch.setattr(
        "modules.follow_up.application.classify_session_outcome.ClassifySessionOutcomeUseCase",
        _FakeUseCase,
    )

    resultado = thread_session._summarize_session(
        [
            HumanMessage(content="Vocês abrem que horas?"),
            AIMessage(content="Abrimos às 9h."),
        ],
        "tenant_x", "tenant_x:sessao_1", "tenant_x:sessao_1#abc123",
        "10% off", date(2999, 1, 1),
    )

    assert resultado == {"resumo": "Cliente só perguntou o horário de funcionamento.", "fatos": {"nome": None}}
    tenant_id, base_thread_id, active_thread_id, conversation_text, oferta_texto, oferta_validade = capturado["args"]
    assert (tenant_id, base_thread_id, active_thread_id) == ("tenant_x", "tenant_x:sessao_1", "tenant_x:sessao_1#abc123")
    assert "Cliente: Vocês abrem que horas?" in conversation_text
    assert "Atendente: Abrimos às 9h." in conversation_text
    assert (oferta_texto, oferta_validade) == ("10% off", date(2999, 1, 1))


def test_summarize_session_com_historico_vazio_nao_chama_use_case():
    """Sem nenhuma linha com conteúdo relevante, retorna cedo sem sequer importar/
    chamar ClassifySessionOutcomeUseCase (evita custo de LLM à toa)."""
    resultado = thread_session._summarize_session([], "tenant_x", "tenant_x:sessao_1", "tenant_x:sessao_1#abc123")

    assert resultado == {"resumo": "", "fatos": {}}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

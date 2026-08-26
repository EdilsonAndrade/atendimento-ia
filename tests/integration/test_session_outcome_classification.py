"""EDI-53: `modules.ia.thread_session._summarize_session` delega para
`ClassifySessionOutcomeUseCase` (única chamada de LLM, ver research.md §1).
Testa a orquestração com o classificador/repositório de `follow_up` trocados por
fakes via monkeypatch (mesmo padrão de contrato usado no restante do projeto,
sem exigir Postgres/LLM reais).
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import modules.follow_up.infrastructure.llm_session_outcome_classifier as classifier_module
import modules.follow_up.infrastructure.postgres_follow_up_queue_repository as repository_module
from modules.ia.thread_session import _summarize_session


class _FakeFollowUpQueueRepository:
    def __init__(self):
        self.saved = []

    def save(self, entry):
        self.saved.append(entry)
        return True

    def list_by_tenant(self, tenant_id, status=None):
        raise NotImplementedError


class _FakeClassifier:
    def __init__(self, result):
        self._result = result

    def classify(self, conversation_text, oferta_vigente_texto, oferta_vigente_validade):
        self.last_conversation_text = conversation_text
        return self._result


@pytest.fixture
def fake_repo(monkeypatch):
    repo = _FakeFollowUpQueueRepository()
    monkeypatch.setattr(repository_module, "PostgresFollowUpQueueRepository", lambda: repo)
    return repo


def _install_classifier(monkeypatch, result):
    fake = _FakeClassifier(result)
    monkeypatch.setattr(classifier_module, "LlmSessionOutcomeClassifier", lambda: fake)
    return fake


def test_sessao_sem_mensagens_nao_classifica(fake_repo, monkeypatch):
    resultado = _summarize_session([], "acme", "acme:123", "acme:123#abc")

    assert resultado == {"resumo": "", "fatos": {}}
    assert fake_repo.saved == []


def test_cliente_sem_resposta_gera_registro_com_draft(fake_repo, monkeypatch):
    _install_classifier(monkeypatch, {
        "resumo": "Cliente perguntou sobre horário e não respondeu.",
        "fatos": {"nome": "Maria"},
        "outcome": "sem_resposta",
        "draft_message": "Oi Maria!",
    })
    messages = [
        HumanMessage(content="Oi, quero saber sobre horários"),
        AIMessage(content="Temos terça às 14h, funciona?"),
    ]

    resultado = _summarize_session(messages, "acme", "acme:123", "acme:123#abc")

    assert resultado["resumo"] == "Cliente perguntou sobre horário e não respondeu."
    assert len(fake_repo.saved) == 1
    assert fake_repo.saved[0].outcome.value == "sem_resposta"
    assert fake_repo.saved[0].draft_message == "Oi Maria!"


def test_agendamento_confirmado_por_tool_message_fecha_sem_draft(fake_repo, monkeypatch):
    fake_classifier = _install_classifier(monkeypatch, {
        "resumo": "Agendamento confirmado para terça 14h.",
        "fatos": {"resultado": "agendado"},
        "outcome": "fechado",
        "draft_message": None,
    })
    messages = [
        HumanMessage(content="Quero agendar terça 14h"),
        AIMessage(content="Confirmado!"),
        ToolMessage(content="Evento criado com sucesso: terça 14h", tool_call_id="call_1"),
    ]

    resultado = _summarize_session(messages, "acme", "acme:123", "acme:123#abc")

    assert fake_repo.saved[0].outcome.value == "fechado"
    assert fake_repo.saved[0].draft_message is None
    # A linha de ToolMessage precisa chegar ao classificador como fonte confiável
    # separada da fala do Atendente (guardrail anti-alucinação do EDI-61).
    assert "Resultado real de ferramenta" in fake_classifier.last_conversation_text
    assert "Evento criado com sucesso" in fake_classifier.last_conversation_text


def test_falha_no_classificador_nao_grava_e_devolve_vazio(fake_repo, monkeypatch):
    class _RaisingClassifier:
        def classify(self, *a, **k):
            raise RuntimeError("LLM indisponível")

    monkeypatch.setattr(classifier_module, "LlmSessionOutcomeClassifier", lambda: _RaisingClassifier())
    messages = [HumanMessage(content="oi"), AIMessage(content="olá")]

    resultado = _summarize_session(messages, "acme", "acme:123", "acme:123#abc")

    assert resultado == {"resumo": "", "fatos": {}}
    assert fake_repo.saved == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

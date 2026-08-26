import pytest

from modules.follow_up.application.classify_session_outcome import ClassifySessionOutcomeUseCase


class _FakeRepository:
    def __init__(self, save_returns=True):
        self.saved = None
        self._save_returns = save_returns

    def save(self, entry):
        self.saved = entry
        return self._save_returns

    def list_by_tenant(self, tenant_id, status=None):
        raise NotImplementedError


class _FakeClassifier:
    def __init__(self, result=None, raise_error=None):
        self._result = result or {}
        self._raise_error = raise_error

    def classify(self, conversation_text, oferta_vigente_texto, oferta_vigente_validade):
        if self._raise_error:
            raise self._raise_error
        return self._result


def test_grava_outcome_summary_e_draft():
    classifier = _FakeClassifier({
        "resumo": "Cliente pediu horário mas não respondeu à proposta.",
        "fatos": {"nome": "Maria"},
        "outcome": "sem_resposta",
        "draft_message": "Oi Maria! Vi que você chegou a perguntar...",
    })
    repo = _FakeRepository()
    use_case = ClassifySessionOutcomeUseCase(repo, classifier)

    resultado = use_case.execute("acme", "acme:123", "acme:123#abc", "Cliente: oi\nAtendente: ola")

    assert repo.saved.outcome.value == "sem_resposta"
    assert repo.saved.draft_message == "Oi Maria! Vi que você chegou a perguntar..."
    assert resultado == {"resumo": "Cliente pediu horário mas não respondeu à proposta.", "fatos": {"nome": "Maria"}}


def test_draft_fica_none_quando_outcome_nao_e_elegivel():
    classifier = _FakeClassifier({
        "resumo": "Agendamento confirmado.",
        "fatos": {},
        "outcome": "fechado",
        "draft_message": "isso não deveria sobreviver",
    })
    repo = _FakeRepository()
    use_case = ClassifySessionOutcomeUseCase(repo, classifier)

    use_case.execute("acme", "acme:123", "acme:123#abc", "conversa")

    assert repo.saved.outcome.value == "fechado"
    assert repo.saved.draft_message is None


def test_outcome_invalido_nao_grava_e_devolve_none():
    classifier = _FakeClassifier({"resumo": "x", "fatos": {}, "outcome": "outro_valor_qualquer"})
    repo = _FakeRepository()
    use_case = ClassifySessionOutcomeUseCase(repo, classifier)

    resultado = use_case.execute("acme", "acme:123", "acme:123#abc", "conversa")

    assert resultado is None
    assert repo.saved is None


def test_claim_perdido_nao_lanca():
    classifier = _FakeClassifier({"resumo": "x", "fatos": {}, "outcome": "em_andamento"})
    repo = _FakeRepository(save_returns=False)
    use_case = ClassifySessionOutcomeUseCase(repo, classifier)

    resultado = use_case.execute("acme", "acme:123", "acme:123#abc", "conversa")

    assert resultado is not None  # reprocessamento idempotente não é erro


def test_falha_do_classificador_e_so_logada():
    classifier = _FakeClassifier(raise_error=RuntimeError("LLM indisponível"))
    repo = _FakeRepository()
    use_case = ClassifySessionOutcomeUseCase(repo, classifier)

    resultado = use_case.execute("acme", "acme:123", "acme:123#abc", "conversa")

    assert resultado is None
    assert repo.saved is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

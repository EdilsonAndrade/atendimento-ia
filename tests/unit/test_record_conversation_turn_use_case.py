import pytest

from modules.conversation_history.application.record_conversation_turn import RecordConversationTurnUseCase


class _FakeRepository:
    def __init__(self, raise_error=None):
        self.saved = None
        self._raise_error = raise_error

    def save_turn(self, human, ai):
        if self._raise_error:
            raise self._raise_error
        self.saved = (human, ai)


def test_grava_par_human_e_ai():
    repo = _FakeRepository()
    use_case = RecordConversationTurnUseCase(repo)

    use_case.execute("acme", "acme:123", "acme:123#abc", "Oi, quero agendar", "Claro! Qual serviço?")

    human, ai = repo.saved
    assert human.role == "human" and human.content == "Oi, quero agendar"
    assert ai.role == "ai" and ai.content == "Claro! Qual serviço?"
    assert human.tenant_id == ai.tenant_id == "acme"
    assert human.active_thread_id == ai.active_thread_id == "acme:123#abc"


def test_falha_do_repositorio_nunca_propaga():
    repo = _FakeRepository(raise_error=RuntimeError("Postgres indisponível"))
    use_case = RecordConversationTurnUseCase(repo)

    use_case.execute("acme", "acme:123", "acme:123#abc", "oi", "olá")  # não deve lançar


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

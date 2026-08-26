import pytest

from modules.follow_up.application.get_follow_up_queue import GetFollowUpQueueUseCase


class _FakeRepository:
    def __init__(self, entries):
        self._entries = entries
        self.last_call = None

    def list_by_tenant(self, tenant_id, status=None, outcome=None):
        self.last_call = (tenant_id, status, outcome)
        result = [e for e in self._entries if e[0] == tenant_id]
        if status is not None:
            result = [e for e in result if e[1] == status]
        if outcome is not None:
            result = [e for e in result if e[2] == outcome]
        return result

    def save(self, entry):
        raise NotImplementedError


def test_sem_filtro_devolve_todos_status_do_tenant():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("acme", "enviado", "fechado"),
        ("outra", "pendente", "sem_resposta"),
    ])
    use_case = GetFollowUpQueueUseCase(repo)

    resultado = use_case.execute("acme")

    assert resultado == [("acme", "pendente", "sem_resposta"), ("acme", "enviado", "fechado")]


def test_filtra_por_status():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("acme", "enviado", "fechado"),
    ])
    use_case = GetFollowUpQueueUseCase(repo)

    resultado = use_case.execute("acme", status="pendente")

    assert resultado == [("acme", "pendente", "sem_resposta")]
    assert repo.last_call == ("acme", "pendente", None)


def test_filtra_por_outcome():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("acme", "pendente", "pensando"),
    ])
    use_case = GetFollowUpQueueUseCase(repo)

    resultado = use_case.execute("acme", outcome="pensando")

    assert resultado == [("acme", "pendente", "pensando")]
    assert repo.last_call == ("acme", None, "pensando")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

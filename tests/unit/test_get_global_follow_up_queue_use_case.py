import pytest

from modules.follow_up.application.get_global_follow_up_queue import GetGlobalFollowUpQueueUseCase


class _FakeRepository:
    def __init__(self, entries):
        self._entries = entries
        self.last_call = None

    def list_all(self, tenant_id=None, status=None, outcome=None):
        self.last_call = (tenant_id, status, outcome)
        result = self._entries
        if tenant_id is not None:
            result = [e for e in result if e[0] == tenant_id]
        if status is not None:
            result = [e for e in result if e[1] == status]
        if outcome is not None:
            result = [e for e in result if e[2] == outcome]
        return result


def test_sem_filtro_devolve_de_todos_os_tenants():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("outra", "enviado", "fechado"),
    ])
    use_case = GetGlobalFollowUpQueueUseCase(repo)

    resultado = use_case.execute()

    assert len(resultado) == 2
    assert repo.last_call == (None, None, None)


def test_filtra_por_tenant_id():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("outra", "pendente", "sem_resposta"),
    ])
    use_case = GetGlobalFollowUpQueueUseCase(repo)

    resultado = use_case.execute(tenant_id="acme")

    assert resultado == [("acme", "pendente", "sem_resposta")]


def test_filtra_por_status_e_outcome():
    repo = _FakeRepository([
        ("acme", "pendente", "sem_resposta"),
        ("acme", "pendente", "pensando"),
    ])
    use_case = GetGlobalFollowUpQueueUseCase(repo)

    resultado = use_case.execute(status="pendente", outcome="pensando")

    assert resultado == [("acme", "pendente", "pensando")]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

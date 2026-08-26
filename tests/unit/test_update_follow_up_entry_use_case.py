from datetime import datetime, timezone

import pytest

from modules.follow_up.application.update_follow_up_entry import (
    FollowUpEntryNotFoundError,
    UpdateFollowUpEntryUseCase,
)
from modules.follow_up.domain.follow_up_entry import FollowUpEntry


def _entry(tenant_id="acme", entry_id=1, status="pendente"):
    return FollowUpEntry(
        tenant_id=tenant_id,
        base_thread_id=f"{tenant_id}:123",
        active_thread_id=f"{tenant_id}:123#abc",
        outcome="sem_resposta",
        summary="resumo",
        draft_message="rascunho original",
        status=status,
        id=entry_id,
        created_at=datetime(2026, 8, 26, 20, 0, 0, tzinfo=timezone.utc),
    )


class _FakeRepository:
    def __init__(self, entries_by_id):
        self._entries_by_id = entries_by_id
        self.last_call = None

    def update(self, tenant_id, entry_id, status=None, draft_message=None, approved_by=None):
        self.last_call = (tenant_id, entry_id, status, draft_message, approved_by)
        entry = self._entries_by_id.get(entry_id)
        if entry is None or entry.tenant_id != tenant_id:
            return None
        if status is not None:
            entry.status = status
        if draft_message is not None:
            entry.draft_message = draft_message
        entry.__post_init__()
        return entry

    def list_by_tenant(self, tenant_id, status=None):
        raise NotImplementedError

    def save(self, entry):
        raise NotImplementedError


def test_aprova_registro_existente():
    repo = _FakeRepository({1: _entry()})
    use_case = UpdateFollowUpEntryUseCase(repo)

    resultado = use_case.execute("acme", 1, status="aprovado")

    assert resultado.status.value == "aprovado"
    assert repo.last_call == ("acme", 1, "aprovado", None, None)


def test_edita_draft_message():
    repo = _FakeRepository({1: _entry()})
    use_case = UpdateFollowUpEntryUseCase(repo)

    resultado = use_case.execute("acme", 1, draft_message="texto revisado")

    assert resultado.draft_message == "texto revisado"


def test_status_invalido_levanta_value_error():
    repo = _FakeRepository({1: _entry()})
    use_case = UpdateFollowUpEntryUseCase(repo)

    with pytest.raises(ValueError):
        use_case.execute("acme", 1, status="nao_existe")


def test_registro_inexistente_levanta_not_found():
    repo = _FakeRepository({})
    use_case = UpdateFollowUpEntryUseCase(repo)

    with pytest.raises(FollowUpEntryNotFoundError):
        use_case.execute("acme", 999, status="aprovado")


def test_isolamento_multi_tenant_nao_atualiza_registro_de_outro_tenant():
    repo = _FakeRepository({1: _entry(tenant_id="outra")})
    use_case = UpdateFollowUpEntryUseCase(repo)

    with pytest.raises(FollowUpEntryNotFoundError):
        use_case.execute("acme", 1, status="aprovado")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

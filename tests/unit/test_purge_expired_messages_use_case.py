import pytest

from modules.conversation_history.application.purge_expired_messages import PurgeExpiredMessagesUseCase


class _FakeRepository:
    def __init__(self, raise_for=None):
        self.calls = []
        self._raise_for = raise_for or {}

    def purge_older_than(self, tenant_id, retention_days):
        if tenant_id in self._raise_for:
            raise self._raise_for[tenant_id]
        self.calls.append((tenant_id, retention_days))
        return 3

    def save_turn(self, human, ai):
        raise NotImplementedError

    def list_by_thread(self, *a, **k):
        raise NotImplementedError


class _FakeTenantLookup:
    def __init__(self, tenants):
        self._tenants = tenants

    def list_tenants_with_retention(self):
        return self._tenants


def test_chama_purge_so_para_tenants_com_retention_days():
    repo = _FakeRepository()
    lookup = _FakeTenantLookup([
        {"id": "acme", "retention_days": 30},
        {"id": "outra", "retention_days": 180},
    ])
    use_case = PurgeExpiredMessagesUseCase(repo, lookup)

    resultado = use_case.execute()

    assert repo.calls == [("acme", 30), ("outra", 180)]
    assert resultado == {"acme": 3, "outra": 3}


def test_tenant_com_retention_days_none_e_ignorado():
    repo = _FakeRepository()
    lookup = _FakeTenantLookup([{"id": "acme", "retention_days": None}])
    use_case = PurgeExpiredMessagesUseCase(repo, lookup)

    use_case.execute()

    assert repo.calls == []


def test_falha_em_um_tenant_nao_impede_os_demais():
    repo = _FakeRepository(raise_for={"acme": RuntimeError("Postgres indisponível")})
    lookup = _FakeTenantLookup([
        {"id": "acme", "retention_days": 30},
        {"id": "outra", "retention_days": 180},
    ])
    use_case = PurgeExpiredMessagesUseCase(repo, lookup)

    resultado = use_case.execute()

    assert "acme" not in resultado
    assert resultado["outra"] == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

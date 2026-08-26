import pytest

from modules.tenant_limits.application.check_tenant_limit import CheckTenantLimitUseCase


class _FakeConfigPort:
    def __init__(self, limit=None, emails=None, raise_error=None):
        self._limit = limit
        self._emails = emails or []
        self._raise_error = raise_error

    def get_limit_and_emails(self, tenant_id):
        if self._raise_error:
            raise self._raise_error
        return self._limit, self._emails


class _FakeUsageCounter:
    def __init__(self, count=0, raise_error=None):
        self._count = count
        self._raise_error = raise_error

    def count_current_month(self, tenant_id):
        if self._raise_error:
            raise self._raise_error
        return self._count


def test_sem_limite_configurado_nunca_bloqueia():
    use_case = CheckTenantLimitUseCase(_FakeConfigPort(limit=None), _FakeUsageCounter(count=999_999))
    assert use_case.execute("tenant_x") is False


def test_abaixo_do_limite_nao_bloqueia():
    use_case = CheckTenantLimitUseCase(_FakeConfigPort(limit=1000), _FakeUsageCounter(count=999))
    assert use_case.execute("tenant_x") is False


def test_no_limite_bloqueia():
    use_case = CheckTenantLimitUseCase(_FakeConfigPort(limit=1000), _FakeUsageCounter(count=1000))
    assert use_case.execute("tenant_x") is True


def test_erro_na_checagem_de_config_faz_fail_open():
    use_case = CheckTenantLimitUseCase(
        _FakeConfigPort(raise_error=RuntimeError("Postgres indisponível")), _FakeUsageCounter(count=0)
    )
    assert use_case.execute("tenant_x") is False


def test_erro_na_contagem_faz_fail_open():
    use_case = CheckTenantLimitUseCase(
        _FakeConfigPort(limit=1000), _FakeUsageCounter(raise_error=RuntimeError("Postgres indisponível"))
    )
    assert use_case.execute("tenant_x") is False


def test_bloqueio_loga_tag_grepavel(caplog):
    use_case = CheckTenantLimitUseCase(_FakeConfigPort(limit=1000), _FakeUsageCounter(count=1000))
    with caplog.at_level("WARNING"):
        use_case.execute("tenant_x", thread_id="tenant_x:sessao_1")
    assert "TENANT_LIMIT_BLOCKED" in caplog.text
    assert "tenant_x" in caplog.text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

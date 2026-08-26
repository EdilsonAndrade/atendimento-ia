import pytest

from modules.tenant_limits.domain.usage_policy import (
    THRESHOLDS,
    is_over_limit,
    percentage_used,
    threshold_count,
)


def test_is_over_limit_sem_limite_nunca_bloqueia():
    assert is_over_limit(999_999, None) is False


def test_is_over_limit_abaixo_do_limite():
    assert is_over_limit(999, 1000) is False


def test_is_over_limit_no_limite_exato_bloqueia():
    assert is_over_limit(1000, 1000) is True


def test_is_over_limit_acima_do_limite_bloqueia():
    assert is_over_limit(1001, 1000) is True


def test_threshold_count_arredonda_para_cima():
    assert threshold_count(1000, 50) == 500
    assert threshold_count(1000, 80) == 800
    assert threshold_count(1000, 100) == 1000
    assert threshold_count(3, 50) == 2  # ceil(1.5) == 2


def test_percentage_used_sem_limite_e_none():
    assert percentage_used(500, None) is None


def test_percentage_used_calcula_percentual():
    assert percentage_used(310, 1000) == 31.0
    assert percentage_used(1000, 1000) == 100.0


def test_thresholds_ordem_crescente():
    assert THRESHOLDS == (50, 80, 100)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

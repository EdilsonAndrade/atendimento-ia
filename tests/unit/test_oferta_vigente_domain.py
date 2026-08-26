from datetime import date

import pytest

from modules.follow_up.domain.oferta_vigente import is_oferta_vigente

HOJE = date(2026, 8, 26)


def test_sem_texto_nao_e_vigente():
    assert is_oferta_vigente(None, date(2026, 12, 31), HOJE) is False


def test_sem_validade_nao_e_vigente():
    assert is_oferta_vigente("10% de desconto", None, HOJE) is False


def test_validade_no_passado_nao_e_vigente():
    assert is_oferta_vigente("10% de desconto", date(2026, 1, 1), HOJE) is False


def test_validade_futura_e_vigente():
    assert is_oferta_vigente("10% de desconto", date(2026, 12, 31), HOJE) is True


def test_validade_igual_a_hoje_e_vigente():
    assert is_oferta_vigente("10% de desconto", HOJE, HOJE) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

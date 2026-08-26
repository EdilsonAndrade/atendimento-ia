import pytest

import modules.follow_up.infrastructure.customer_name_lookup as lookup_module


def test_devolve_nome_quando_fatos_tem_nome(monkeypatch):
    monkeypatch.setattr(
        lookup_module, "get_latest_session_summary",
        lambda base_thread_id: {"resumo": "x", "fatos": {"nome": "Maria"}},
    )

    assert lookup_module.get_customer_name("acme:123") == "Maria"


def test_devolve_none_quando_sem_resumo(monkeypatch):
    monkeypatch.setattr(lookup_module, "get_latest_session_summary", lambda base_thread_id: None)

    assert lookup_module.get_customer_name("acme:123") is None


def test_devolve_none_quando_fatos_sem_nome(monkeypatch):
    monkeypatch.setattr(
        lookup_module, "get_latest_session_summary",
        lambda base_thread_id: {"resumo": "x", "fatos": {"interesse": "corte"}},
    )

    assert lookup_module.get_customer_name("acme:123") is None


def test_devolve_none_quando_nome_e_string_vazia(monkeypatch):
    monkeypatch.setattr(
        lookup_module, "get_latest_session_summary",
        lambda base_thread_id: {"resumo": "x", "fatos": {"nome": "   "}},
    )

    assert lookup_module.get_customer_name("acme:123") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

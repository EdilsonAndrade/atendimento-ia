import logging

import pytest

from util.tool_error_handling import safe_tool_result


def test_safe_tool_result_passes_through_successful_result():
    @safe_tool_result(fallback="fallback genérico")
    def minha_tool(tenant_id: str) -> str:
        return "resultado real da tool"

    assert minha_tool(tenant_id="tenant_x") == "resultado real da tool"


def test_safe_tool_result_returns_fallback_on_exception_without_leaking_raw_error():
    @safe_tool_result(fallback="Não foi possível concluir agora. Tente novamente.")
    def minha_tool(tenant_id: str) -> str:
        raise psycopg_like_error()

    resultado = minha_tool(tenant_id="tenant_x")

    assert resultado == "Não foi possível concluir agora. Tente novamente."
    assert "psycopg" not in resultado.lower()
    assert "traceback" not in resultado.lower()


def test_safe_tool_result_logs_exception_with_tenant_id_from_kwargs(caplog):
    @safe_tool_result(fallback="fallback")
    def minha_tool(tenant_id: str) -> str:
        raise ValueError("erro técnico interno de banco")

    with caplog.at_level(logging.ERROR):
        minha_tool(tenant_id="tenant_abc")

    assert any(
        "tenant_abc" in record.getMessage() and "erro técnico interno de banco" in record.getMessage()
        for record in caplog.records
    )


def test_safe_tool_result_logs_exception_with_static_tenant_id_from_closure(caplog):
    tenant_id_fixo = "tenant_fechado_por_closure"

    @safe_tool_result(fallback="fallback", tenant_id=tenant_id_fixo)
    def minha_tool_de_factory() -> str:
        raise RuntimeError("falha na API externa")

    with caplog.at_level(logging.ERROR):
        minha_tool_de_factory()

    assert any(tenant_id_fixo in record.getMessage() for record in caplog.records)


def psycopg_like_error() -> Exception:
    return Exception("connection to server at \"10.0.0.5\", port 5432 failed: FATAL")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

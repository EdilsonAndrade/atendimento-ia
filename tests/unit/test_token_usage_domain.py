from decimal import Decimal

import pytest

from modules.token_usage.domain.token_usage_record import TokenUsageRecord, calculate_cost_usd


def test_calculate_cost_usd_com_valores_conhecidos():
    custo = calculate_cost_usd(
        input_tokens=1000,
        output_tokens=500,
        price_per_1k_input=Decimal("0.27"),
        price_per_1k_output=Decimal("1.10"),
    )

    esperado = Decimal("0.27") + (Decimal("500") / Decimal("1000")) * Decimal("1.10")
    assert custo == esperado.quantize(Decimal("0.000001"))


def test_calculate_cost_usd_com_zero_tokens_e_zero():
    custo = calculate_cost_usd(0, 0, Decimal("0.27"), Decimal("1.10"))
    assert custo == Decimal("0.000000")


def test_calculate_cost_usd_nunca_fica_negativo_mesmo_com_tokens_negativos():
    custo = calculate_cost_usd(-10, -5, Decimal("0.27"), Decimal("1.10"))
    assert custo == Decimal("0.000000")


def test_token_usage_record_e_imutavel():
    record = TokenUsageRecord(
        tenant_id="tenant_x",
        base_thread_id="tenant_x:sessao_1",
        thread_id="tenant_x:sessao_1#abc",
        node_type="operational_node",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        estimated_cost_usd=Decimal("0.001"),
    )

    with pytest.raises(Exception):
        record.tenant_id = "outro_tenant"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

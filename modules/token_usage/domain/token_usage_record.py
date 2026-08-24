"""Entidade e regra de negócio do rastreamento de custo de token (EDI-60).

Camada Domain (Princípio III da constituição): sem import de framework (FastAPI,
psycopg, LangChain) — só Python puro, testável sem banco/LLM real.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class TokenUsageRecord:
    tenant_id: str
    base_thread_id: str
    thread_id: str | None
    node_type: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal


def calculate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    price_per_1k_input: Decimal,
    price_per_1k_output: Decimal,
) -> Decimal:
    """Calcula o custo estimado (USD) de uma chamada ao LLM a partir dos tokens
    consumidos e do preço por 1000 tokens de cada tipo.

    Tokens negativos não fazem sentido de negócio; são tratados como 0 em vez de
    gerar custo negativo (defesa simples, sem levantar exceção, para nunca quebrar
    o fluxo de conversa por causa de um dado de uso inesperado — ver FR-006).
    """
    entrada = max(input_tokens, 0)
    saida = max(output_tokens, 0)

    custo = (Decimal(entrada) / Decimal(1000)) * price_per_1k_input
    custo += (Decimal(saida) / Decimal(1000)) * price_per_1k_output

    return custo.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

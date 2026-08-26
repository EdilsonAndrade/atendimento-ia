"""Regra pura de limite mensal de mensagens por tenant (EDI-63).

Camada Domain (Princípio III da constituição): sem import de framework — só
Python puro, testável sem banco/LLM real.
"""
import math

THRESHOLDS: tuple[int, ...] = (50, 80, 100)


def is_over_limit(current_month_calls: int, monthly_message_limit: int | None) -> bool:
    """Sem limite configurado (`None`), nunca bloqueia (comportamento atual
    preservado — SC-002)."""
    if monthly_message_limit is None:
        return False
    return current_month_calls >= monthly_message_limit


def threshold_count(monthly_message_limit: int, pct: int) -> int:
    """Quantas chamadas correspondem a `pct`% do limite, arredondado para cima —
    um tenant com limite 1000 cruza o marco de 50% na chamada 500, não na 499.5."""
    return math.ceil(monthly_message_limit * pct / 100)


def percentage_used(current_month_calls: int, monthly_message_limit: int | None) -> float | None:
    if monthly_message_limit is None or monthly_message_limit <= 0:
        return None
    return round(current_month_calls / monthly_message_limit * 100, 1)

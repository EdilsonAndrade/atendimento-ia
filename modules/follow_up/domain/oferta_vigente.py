"""Regra pura: quando a oferta comercial de um tenant é considerada vigente (EDI-53).

Guardrail contra o rascunho de follow-up inventar desconto/condição comercial que o
tenant não tenha de fato configurado — mesma classe de guardrail do c92de57/EDI-61
(nunca confiar em texto gerado por LLM para algo que devia vir de um dado real).
"""
from datetime import date


def is_oferta_vigente(texto: str | None, validade: date | None, hoje: date) -> bool:
    if not texto or not validade:
        return False
    return validade >= hoje

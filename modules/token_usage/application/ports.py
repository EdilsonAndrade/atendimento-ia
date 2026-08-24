"""Portas (interfaces) da Application layer — Princípio III da constituição.

A Application depende apenas desta abstração para persistência; a implementação
concreta (Postgres) vive na Infrastructure layer e é injetada de fora.
"""
from typing import Protocol

from modules.token_usage.domain.token_usage_record import TokenUsageRecord


class TokenUsageRepository(Protocol):
    def save(self, record: TokenUsageRecord) -> None:
        ...

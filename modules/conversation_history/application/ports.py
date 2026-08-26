"""Ports (Protocols) do módulo conversation_history — Application layer.

Nenhuma implementação concreta aqui; Infrastructure implementa estes Protocols
(dependency inversion, Princípio III).
"""
from datetime import datetime
from typing import Protocol

from modules.conversation_history.domain.conversation_message import ConversationMessage


class ConversationMessageRepository(Protocol):
    def save_turn(self, human: ConversationMessage, ai: ConversationMessage) -> None:
        ...

    def list_by_thread(
        self,
        tenant_id: str,
        base_thread_id: str,
        limit: int = 200,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        ...

    def purge_older_than(self, tenant_id: str, retention_days: int) -> int:
        ...

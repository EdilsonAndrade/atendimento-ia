"""Caso de uso: consultar o histórico de mensagens de uma conversa (EDI-53, FR-008)."""
from datetime import datetime

from modules.conversation_history.application.ports import ConversationMessageRepository
from modules.conversation_history.domain.conversation_message import ConversationMessage


class GetConversationHistoryUseCase:
    def __init__(self, repository: ConversationMessageRepository):
        self._repository = repository

    def execute(
        self,
        tenant_id: str,
        base_thread_id: str,
        limit: int = 200,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        return self._repository.list_by_thread(tenant_id, base_thread_id, limit=limit, before=before)

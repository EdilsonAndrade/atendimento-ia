"""Caso de uso: registrar o turno (mensagem do cliente + resposta do atendente) de
uma conversa em `conversation_messages` (EDI-53).

Único ponto onde a regra "uma falha aqui nunca pode afetar a resposta ao cliente"
(FR-010) vive — mesmo espírito de `RecordTokenUsageUseCase` (EDI-60).
"""
import logging

from modules.conversation_history.application.ports import ConversationMessageRepository
from modules.conversation_history.domain.conversation_message import ConversationMessage
from modules.observability.interface.logger_factory import get_logger

logger = logging.getLogger(__name__)


class RecordConversationTurnUseCase:
    def __init__(self, repository: ConversationMessageRepository):
        self._repository = repository

    def execute(
        self,
        tenant_id: str,
        base_thread_id: str,
        active_thread_id: str,
        human_content: str,
        ai_content: str,
    ) -> None:
        try:
            human = ConversationMessage(
                tenant_id=tenant_id,
                base_thread_id=base_thread_id,
                active_thread_id=active_thread_id,
                role="human",
                content=human_content,
            )
            ai = ConversationMessage(
                tenant_id=tenant_id,
                base_thread_id=base_thread_id,
                active_thread_id=active_thread_id,
                role="ai",
                content=ai_content,
            )
            self._repository.save_turn(human, ai)
        except Exception as exc:
            logger.error(
                "Falha ao registrar turno de conversa (tenant_id=%s, base_thread_id=%s): %s",
                tenant_id,
                base_thread_id,
                exc,
                exc_info=True,
            )
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="conversation_history").error(
                message=f"Failed to record conversation turn: {exc}",
                method="modules.conversation_history.application.record_conversation_turn.execute",
                line=43,
                thread_id=active_thread_id,
                extra={"error": str(exc)},
            )

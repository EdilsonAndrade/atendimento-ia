"""Entrypoint do job de expurgo de `conversation_messages` por `retention_days`
de cada tenant (EDI-53).

Script de execução única — roda, processa, termina. O agendamento (cron diário,
etc.) é responsabilidade de infraestrutura, fora deste repositório.

Rodar com: python -m workers.conversation_history_purge
"""
import logging

from modules.conversation_history.application.purge_expired_messages import PurgeExpiredMessagesUseCase
from modules.conversation_history.infrastructure.postgres_conversation_message_repository import (
    PostgresConversationMessageRepository,
)
from modules.tenant.tenant_service import TenantService

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    PurgeExpiredMessagesUseCase(PostgresConversationMessageRepository(), TenantService()).execute()

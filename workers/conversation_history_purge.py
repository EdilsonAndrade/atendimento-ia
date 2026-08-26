"""Entrypoint do job de expurgo de `conversation_messages` por `retention_days`
de cada tenant (EDI-53).

Script de execução única — roda, processa, termina. O agendamento (cron diário,
etc.) é responsabilidade de infraestrutura, fora deste repositório.

Rodar com: python -m workers.conversation_history_purge
"""
import asyncio
import logging

from app.core.observability import init_observability, shutdown_observability, start_observability_flush
from modules.conversation_history.application.purge_expired_messages import PurgeExpiredMessagesUseCase
from modules.conversation_history.infrastructure.postgres_conversation_message_repository import (
    PostgresConversationMessageRepository,
)
from modules.tenant.tenant_service import TenantService

logging.basicConfig(level=logging.INFO)


async def _main() -> None:
    # Este worker é um script de execução única (roda, processa, termina) — não
    # é o processo da API FastAPI. Precisa inicializar sua própria observabilidade,
    # senão os get_logger() do use case cairiam no no-op silenciosamente.
    init_observability()
    start_observability_flush()
    try:
        PurgeExpiredMessagesUseCase(PostgresConversationMessageRepository(), TenantService()).execute()
    finally:
        # Drena a fila antes do processo terminar — sem isso, logs enfileirados
        # no fim da execução nunca seriam enviados (o processo morre antes do
        # próximo ciclo de flush do LogService).
        await shutdown_observability()


if __name__ == "__main__":
    asyncio.run(_main())

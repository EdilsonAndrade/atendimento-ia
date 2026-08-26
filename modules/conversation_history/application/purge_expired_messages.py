"""Caso de uso: expurgar `conversation_messages` mais antigas que `retention_days`
de cada tenant (EDI-53, FR-007).

Chamado pelo script `workers/conversation_history_purge.py` (execução única,
agendada por cron externo — não é um processo de longa duração).
"""
import logging
from typing import Protocol

from modules.conversation_history.application.ports import ConversationMessageRepository
from modules.observability.interface.logger_factory import get_logger

logger = logging.getLogger(__name__)


class TenantRetentionLookupPort(Protocol):
    def list_tenants_with_retention(self) -> list[dict]:
        ...


class PurgeExpiredMessagesUseCase:
    def __init__(self, repository: ConversationMessageRepository, tenant_lookup: TenantRetentionLookupPort):
        self._repository = repository
        self._tenant_lookup = tenant_lookup

    def execute(self) -> dict[str, int]:
        apagadas_por_tenant: dict[str, int] = {}
        for tenant in self._tenant_lookup.list_tenants_with_retention():
            tenant_id = tenant["id"]
            retention_days = tenant["retention_days"]
            if not retention_days:
                continue
            try:
                apagadas = self._repository.purge_older_than(tenant_id, retention_days)
                apagadas_por_tenant[tenant_id] = apagadas
                logger.info(
                    "Expurgo de conversation_messages: tenant_id=%s retention_days=%s linhas_apagadas=%s",
                    tenant_id, retention_days, apagadas,
                )
            except Exception as exc:
                logger.error(
                    "Falha ao expurgar conversation_messages do tenant_id=%s: %s",
                    tenant_id, exc, exc_info=True,
                )
                get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="conversation_purge_job").error(
                    message=f"Failed to purge expired conversation_messages: {exc}",
                    method="modules.conversation_history.application.purge_expired_messages.execute",
                    line=39,
                    thread_id="system",
                    extra={"error": str(exc), "retention_days": retention_days},
                )
        return apagadas_por_tenant

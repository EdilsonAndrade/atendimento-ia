"""Caso de uso: checar se um tenant atingiu o limite mensal (EDI-63).

Roda ANTES de qualquer chamada ao LLM (chamado pelo Interface layer — ver
app/api/v1/endpoints/chat.py e modules/webhook/whatsapp.py) para que uma
mensagem bloqueada custe zero chamadas de LLM (ver plan.md > Technical Context).
"""
import logging

from modules.tenant_limits.application.ports import TenantLimitConfigPort, UsageCounterPort
from modules.tenant_limits.domain.usage_policy import is_over_limit

logger = logging.getLogger(__name__)


class CheckTenantLimitUseCase:
    def __init__(self, config_port: TenantLimitConfigPort, usage_counter: UsageCounterPort):
        self._config_port = config_port
        self._usage_counter = usage_counter

    def execute(self, tenant_id: str, thread_id: str | None = None) -> bool:
        """Devolve True se o tenant está bloqueado agora. Fail-open em qualquer
        erro (research.md §2) — uma falha de infraestrutura na checagem nunca
        deve impedir um tenant legítimo de ser atendido."""
        try:
            monthly_message_limit, _ = self._config_port.get_limit_and_emails(tenant_id)
            if monthly_message_limit is None:
                return False

            current_month_calls = self._usage_counter.count_current_month(tenant_id)
            blocked = is_over_limit(current_month_calls, monthly_message_limit)

            if blocked:
                logger.warning(
                    "TENANT_LIMIT_BLOCKED tenant_id=%s thread_id=%s current_month_calls=%s "
                    "monthly_message_limit=%s",
                    tenant_id, thread_id, current_month_calls, monthly_message_limit,
                )
            return blocked
        except Exception as exc:
            logger.error(
                "Falha ao checar limite mensal (tenant_id=%s, thread_id=%s): %s — fail-open (não bloqueando).",
                tenant_id, thread_id, exc, exc_info=True,
            )
            return False

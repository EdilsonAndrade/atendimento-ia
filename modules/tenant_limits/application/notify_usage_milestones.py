"""Caso de uso: disparar os avisos progressivos de 50/80/100% do limite mensal
(EDI-63).

Roda DEPOIS de uma chamada ao LLM bem-sucedida (Interface layer). Idempotente por
mês/marco via `NotificationClaimPort` (research.md §3) — testa os 3 marcos a cada
chamada em vez de comparar "antes/depois", o que resolve rajadas que cruzam mais
de um marco na mesma chamada sem lógica extra (FR-009, ver spec.md > Clarifications).
"""
import logging
from datetime import datetime, timezone

from modules.tenant_limits.application.ports import (
    EmailSenderPort,
    GlobalRecipientsPort,
    NotificationClaimPort,
    TenantLimitConfigPort,
    UsageCounterPort,
)
from modules.tenant_limits.domain.usage_policy import THRESHOLDS, threshold_count

logger = logging.getLogger(__name__)


class NotifyUsageMilestonesUseCase:
    def __init__(
        self,
        config_port: TenantLimitConfigPort,
        usage_counter: UsageCounterPort,
        claim_port: NotificationClaimPort,
        global_recipients: GlobalRecipientsPort,
        email_sender: EmailSenderPort,
    ):
        self._config_port = config_port
        self._usage_counter = usage_counter
        self._claim_port = claim_port
        self._global_recipients = global_recipients
        self._email_sender = email_sender

    def execute(self, tenant_id: str) -> None:
        """Nunca lança — uma falha aqui nunca pode afetar a resposta ao cliente
        (mesma filosofia do FR-006 do EDI-60)."""
        try:
            logger.info(f"[EDI-63] execute() iniciado para tenant_id={tenant_id}")
            monthly_message_limit, notification_emails = self._config_port.get_limit_and_emails(tenant_id)
            logger.info(f"[EDI-63] limit={monthly_message_limit}, emails={notification_emails}")
            if monthly_message_limit is None:
                logger.info(f"[EDI-63] Tenant sem limite configurado, retornando")
                return

            current_month_calls = self._usage_counter.count_current_month(tenant_id)
            logger.info(f"[EDI-63] usage this month={current_month_calls}")
            year_month = datetime.now(timezone.utc).strftime("%Y-%m")

            for milestone in THRESHOLDS:
                threshold = threshold_count(monthly_message_limit, milestone)
                logger.info(f"[EDI-63] Verificando milestone={milestone}% (threshold={threshold}, current={current_month_calls})")
                if current_month_calls < threshold:
                    logger.info(f"[EDI-63] Não atingiu o marco ainda")
                    continue

                if not self._claim_port.try_claim(tenant_id, year_month, milestone):
                    logger.info(f"[EDI-63] Já enviado este mês para o marco={milestone}%")
                    continue  # já enviado este mês para este marco

                logger.info(f"[EDI-63] Enviando email do milestone={milestone}%")
                self._send_milestone_email(
                    tenant_id, milestone, current_month_calls, monthly_message_limit, notification_emails,
                )
        except Exception as exc:
            logger.error(
                "Falha ao processar notificações de marco (tenant_id=%s): %s",
                tenant_id, exc, exc_info=True,
            )

    def _send_milestone_email(
        self,
        tenant_id: str,
        milestone: int,
        current_month_calls: int,
        monthly_message_limit: int,
        notification_emails: list[str],
    ) -> None:
        if milestone == 50:
            subject = "Aviso de consumo: 50% do limite mensal"
            body = (
                f"Você já usou {current_month_calls} de {monthly_message_limit} mensagens este mês. "
                "Continue acompanhando seu plano."
            )
            recipients = notification_emails
        elif milestone == 80:
            subject = "Atenção: 80% do limite mensal atingido"
            faltam = max(monthly_message_limit - current_month_calls, 0)
            body = (
                f"Atenção! Você já usou {current_month_calls} de {monthly_message_limit} mensagens este mês. "
                f"Faltam {faltam} mensagens até o bloqueio."
            )
            recipients = notification_emails
        else:  # 100
            subject = "Limite mensal atingido — bloqueio ativo"
            body = (
                f"Seu plano de {monthly_message_limit} mensagens/mês foi atingido. "
                "Novas solicitações serão bloqueadas até o próximo reset."
            )
            recipients = [*notification_emails, *self._global_recipients.list_active_emails()]

        if recipients:
            self._email_sender.send(to=recipients, subject=subject, body=body)

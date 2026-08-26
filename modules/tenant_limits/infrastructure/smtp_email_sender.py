"""Adapter SMTP de `EmailSenderPort` — Infrastructure layer.

Sem provedor transacional configurado no projeto hoje (ver research.md §6) — usa
`smtplib` (stdlib) com credenciais via env var, mesmo padrão de configuração já
usado no resto do projeto (`os.getenv`, sem `pydantic-settings`).
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText

from modules.observability.interface.logger_factory import get_logger as get_obs_logger

logger = logging.getLogger(__name__)


class SmtpEmailSender:
    def __init__(self):
        self._host = os.getenv("SMTP_HOST")
        self._port = int(os.getenv("SMTP_PORT", "587"))
        self._username = os.getenv("SMTP_USERNAME")
        self._password = os.getenv("SMTP_PASSWORD")
        self._from = os.getenv("SMTP_FROM", self._username or "")
        self._use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

    def send(self, to: list[str], subject: str, body: str) -> None:
        """Nunca lança — uma falha de envio de e-mail não pode derrubar o
        request-path que a chamou (mesma filosofia do FR-006 do EDI-60)."""
        logger.info(f"[EDI-63] SmtpEmailSender.send() called: to={to}, subject={subject}")
        if not to:
            logger.warning("[EDI-63] Lista de destinatários vazia, retornando")
            return
        if not self._host:
            logger.warning(
                "[EDI-63] SMTP_HOST não configurado — e-mail '%s' para %s não foi enviado.", subject, to
            )
            return

        logger.info(f"[EDI-63] Tentando enviar email via SMTP ({self._host}:{self._port})")
        try:
            message = MIMEText(body, "plain", "utf-8")
            message["Subject"] = subject
            message["From"] = self._from
            message["To"] = ", ".join(to)

            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                if self._use_tls:
                    logger.info("[EDI-63] Iniciando TLS...")
                    smtp.starttls()
                if self._username and self._password:
                    logger.info("[EDI-63] Autenticando...")
                    smtp.login(self._username, self._password)
                logger.info("[EDI-63] Enviando email...")
                smtp.sendmail(self._from, to, message.as_string())
                logger.info(f"[EDI-63] Email enviado com sucesso! To: {to}, Subject: {subject}")
        except Exception as exc:
            logger.error("[EDI-63] Falha ao enviar e-mail '%s' para %s: %s", subject, to, exc, exc_info=True)
            get_obs_logger(tenant_id="unknown", tenant_name="unknown", agent="email_sender").error(
                message=f"Failed to send email: {exc}",
                method="modules.tenant_limits.infrastructure.smtp_email_sender.send",
                line=54,
                thread_id="system",
                extra={"error": str(exc), "subject": subject},
            )

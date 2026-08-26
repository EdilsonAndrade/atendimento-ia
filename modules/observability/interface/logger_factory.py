"""Interface layer: Logger factory for agent integration."""

import logging
from datetime import datetime
from typing import Optional

from modules.observability.application.log_service import LogService
from modules.observability.domain.log_event import LogEntry

logger = logging.getLogger(__name__)

# Global LogService instance (set by init_observability in app.main)
_log_service: Optional[LogService] = None


def set_log_service(service: Optional[LogService]) -> None:
    """Set the global LogService instance (called during app initialization)."""
    global _log_service
    _log_service = service


def get_logger(
    tenant_id: str, tenant_name: str, agent: Optional[str] = None
) -> "AgentLogger":
    """Factory: create a logger with tenant/agent context pre-populated.

    Args:
        tenant_id: Tenant identifier (e.g., "acme-corp")
        tenant_name: Human-readable tenant name
        agent: Optional agent name (e.g., "booking_agent")

    Returns:
        AgentLogger instance with context embedded
    """
    if not _log_service:
        # Observability disabled (safe no-op)
        return AgentLogger(None, tenant_id, tenant_name, agent)

    return AgentLogger(_log_service, tenant_id, tenant_name, agent)


class AgentLogger:
    """Logger instance with tenant/agent context pre-populated.

    Agents use this to log lifecycle events (start, end, error, decision).
    """

    def __init__(
        self,
        service: Optional[LogService],
        tenant_id: str,
        tenant_name: str,
        agent: Optional[str] = None,
    ):
        """Initialize logger with context.

        Args:
            service: LogService instance (None if observability disabled)
            tenant_id: Tenant ID
            tenant_name: Tenant name
            agent: Agent name
        """
        self.service = service
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.agent = agent

    def info(
        self,
        message: str,
        method: str,
        line: int,
        thread_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Log INFO level event.

        Args:
            message: Description of the event
            method: Code location (module.function)
            line: Source code line number
            thread_id: Conversation/session ID for correlation
            extra: Optional custom context dict
        """
        self._log("INFO", message, method, line, thread_id, extra)

    def warn(
        self,
        message: str,
        method: str,
        line: int,
        thread_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Log WARN level event."""
        self._log("WARN", message, method, line, thread_id, extra)

    def error(
        self,
        message: str,
        method: str,
        line: int,
        thread_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Log ERROR level event.

        Args:
            message: Description of the error
            method: Code location where error occurred
            line: Source line number
            thread_id: Conversation/session ID
            extra: Optional error context (error_code, error_details, etc.)
        """
        self._log("ERROR", message, method, line, thread_id, extra)

    def debug(
        self,
        message: str,
        method: str,
        line: int,
        thread_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Log DEBUG level event."""
        self._log("DEBUG", message, method, line, thread_id, extra)

    def _log(
        self,
        level: str,
        message: str,
        method: str,
        line: int,
        thread_id: str,
        extra: Optional[dict] = None,
    ) -> None:
        """Internal: log an entry (non-blocking).

        Args:
            level: Log level
            message: Description
            method: Code location
            line: Line number
            thread_id: Conversation ID
            extra: Optional context
        """
        if not self.service:
            # Observability disabled, silently discard
            return

        try:
            entry = LogEntry(
                tenant_id=self.tenant_id,
                tenant_name=self.tenant_name,
                thread_id=thread_id,
                agent=self.agent,
                method=method,
                line=line,
                level=level,
                message=message,
                timestamp=datetime.utcnow(),
                extra=extra,
            )
            self.service.log(entry)
        except Exception as e:
            # Don't let logging errors crash the app
            logger.error(f"Error queueing log entry: {e}")

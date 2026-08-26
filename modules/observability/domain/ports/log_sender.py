"""Port: abstract interface for transmitting logs to external backends."""

from abc import ABC, abstractmethod
from typing import List
from modules.observability.domain.log_event import LogEntry


class LogSender(ABC):
    """Abstract port for sending logs to any backend (Loki, etc.).

    Implementations must be non-blocking and handle retries.
    """

    @abstractmethod
    async def send_batch(self, entries: List[LogEntry]) -> bool:
        """Send a batch of log entries to backend.

        Args:
            entries: List of LogEntry objects to send

        Returns:
            True if send succeeded, False if retryable error occurred.
            Non-retryable errors (4xx) should raise HTTPException or similar.
        """
        pass

"""Application layer: LogService use case (log queueing and batching)."""

import asyncio
import logging
from queue import Queue, Full
from typing import List, Optional

from modules.observability.domain.log_event import LogEntry
from modules.observability.domain.ports.log_sender import LogSender

logger = logging.getLogger(__name__)


class LogService:
    """Use case: queue log entries and batch-transmit to backend.

    Non-blocking: callers queue logs immediately, background task sends to backend.
    """

    def __init__(
        self,
        sender: LogSender,
        batch_size: int = 100,
        flush_interval_sec: float = 2.0,
        queue_max_size: int = 10000,
    ):
        """Initialize LogService.

        Args:
            sender: LogSender implementation (Loki, no-op, etc.)
            batch_size: Max entries per batch before forcing flush
            flush_interval_sec: Max wait between flushes
            queue_max_size: Max in-memory queue size before dropping oldest
        """
        self.sender = sender
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.queue: Queue = Queue(maxsize=queue_max_size)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start background flush task."""
        if self._running:
            return

        self._running = True
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._task = loop.create_task(self._flush_loop())
        logger.debug("LogService started")

    async def stop(self) -> None:
        """Stop background task and flush remaining entries."""
        if not self._running:
            return

        self._running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("LogService flush loop did not complete within 5s")
                self._task.cancel()

        # Flush remaining entries
        batch = self._drain_queue()
        if batch:
            success = await self.sender.send_batch(batch)
            if not success:
                logger.warning(f"Failed to flush {len(batch)} logs on shutdown")

        logger.debug("LogService stopped")

    def log(self, entry: LogEntry) -> None:
        """Queue a log entry (non-blocking).

        Args:
            entry: LogEntry to queue

        Raises:
            ValueError: If entry validation fails
        """
        entry.validate()  # Fail fast on invalid entries

        try:
            self.queue.put_nowait(entry)
        except Full:
            # Queue full: drop oldest entry and retry
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(entry)
            except Full:
                logger.warning("LogService queue overflow, dropping oldest logs")

    async def _flush_loop(self) -> None:
        """Background task: periodically flush queue to sender."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_sec)

                # Drain queue
                batch = self._drain_queue(max_size=self.batch_size)

                if batch:
                    success = await self.sender.send_batch(batch)

                    if not success:
                        logger.debug(f"Failed to send {len(batch)} logs (retryable)")
                        # On retryable failure, logs are discarded
                        # (not re-queued, as design accepts loss on backend unavailability)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in LogService flush loop: {e}", exc_info=True)

    def _drain_queue(self, max_size: Optional[int] = None) -> List[LogEntry]:
        """Drain up to max_size entries from queue.

        Args:
            max_size: Maximum entries to drain (default: batch_size)

        Returns:
            List of LogEntry objects
        """
        max_size = max_size or self.batch_size
        batch: List[LogEntry] = []

        while len(batch) < max_size and not self.queue.empty():
            try:
                entry = self.queue.get_nowait()
                batch.append(entry)
            except Exception:
                break

        return batch

    def queue_size(self) -> int:
        """Get current queue size (for monitoring)."""
        return self.queue.qsize()

"""Unit tests for LogService (Application layer)."""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from modules.observability.domain.log_event import LogEntry
from modules.observability.application.log_service import LogService
from modules.observability.domain.ports.log_sender import LogSender
from modules.observability.interface.logger_factory import AgentLogger, set_log_service


@pytest.fixture
def mock_sender():
    """Create mock LogSender for testing."""
    sender = MagicMock(spec=LogSender)
    sender.send_batch = AsyncMock(return_value=True)
    return sender


@pytest.fixture
def log_service(mock_sender):
    """Create LogService with mock sender."""
    return LogService(mock_sender, batch_size=10, flush_interval_sec=0.1)


class TestLogService:
    """Unit tests for LogService use case."""

    def test_log_service_creation(self, mock_sender):
        """Test: LogService initializes correctly."""
        service = LogService(mock_sender)
        assert service.sender == mock_sender
        assert service.batch_size == 100
        assert service.flush_interval_sec == 2.0

    def test_log_entry_queuing(self, log_service):
        """Test: log() queues entry without blocking."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        # Should complete immediately (< 1ms)
        log_service.log(entry)

        assert log_service.queue_size() == 1

    def test_log_entry_validation_on_queue(self, log_service):
        """Test: log() validates entry before queuing."""
        invalid_entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=-1,  # Invalid line number
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError):
            log_service.log(invalid_entry)

        assert log_service.queue_size() == 0

    @pytest.mark.asyncio
    async def test_flush_loop_batches_entries(self, log_service, mock_sender):
        """Test: _flush_loop batches and sends entries."""
        log_service.start()

        # Queue some entries
        for i in range(3):
            entry = LogEntry(
                tenant_id="test",
                tenant_name="Test",
                thread_id=f"thread_{i}",
                method="test.func",
                line=i + 1,
                level="INFO",
                message=f"Message {i}",
                timestamp=datetime.utcnow(),
            )
            log_service.log(entry)

        # Wait for flush
        await asyncio.sleep(0.2)

        # Stop and drain
        await log_service.stop()

        # Verify sender was called
        mock_sender.send_batch.assert_called()

    @pytest.mark.asyncio
    async def test_log_service_stop_flushes_remaining(self, log_service, mock_sender):
        """Test: stop() flushes remaining entries before shutdown."""
        log_service.start()

        # Queue an entry
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )
        log_service.log(entry)

        # Stop (should flush)
        await log_service.stop()

        # Verify sender was called
        mock_sender.send_batch.assert_called()
        assert log_service.queue_size() == 0

    def test_queue_overflow_handling(self, mock_sender):
        """Test: queue overflow drops oldest entries gracefully."""
        service = LogService(mock_sender, queue_max_size=5)

        # Fill queue
        for i in range(10):
            entry = LogEntry(
                tenant_id="test",
                tenant_name="Test",
                thread_id=f"thread_{i}",
                method="test.func",
                line=i + 1,
                level="INFO",
                message=f"Message {i}",
                timestamp=datetime.utcnow(),
            )
            service.log(entry)  # Should not raise, drops oldest if full

        # Queue size should be clamped to max
        assert service.queue_size() <= 5

    def test_drain_queue_respects_max_size(self, log_service):
        """Test: _drain_queue respects max_size parameter."""
        # Queue 20 entries
        for i in range(20):
            entry = LogEntry(
                tenant_id="test",
                tenant_name="Test",
                thread_id=f"thread_{i}",
                method="test.func",
                line=i + 1,
                level="INFO",
                message=f"Message {i}",
                timestamp=datetime.utcnow(),
            )
            log_service.log(entry)

        # Drain only 5
        batch = log_service._drain_queue(max_size=5)

        assert len(batch) == 5
        assert log_service.queue_size() == 15


class TestAgentLogger:
    """Unit tests for AgentLogger interface."""

    def test_agent_logger_creation(self, log_service):
        """Test: AgentLogger initializes with context."""
        set_log_service(log_service)
        logger = AgentLogger(log_service, "tenant_id", "Tenant Name", "booking_agent")

        assert logger.tenant_id == "tenant_id"
        assert logger.tenant_name == "Tenant Name"
        assert logger.agent == "booking_agent"

    def test_agent_logger_info_level(self, log_service):
        """Test: AgentLogger.info() logs correctly."""
        set_log_service(log_service)
        logger = AgentLogger(log_service, "test", "Test", "agent")

        logger.info(
            message="Test message",
            method="test.method",
            line=42,
            thread_id="thread_123",
            extra={"key": "value"},
        )

        assert log_service.queue_size() == 1

    def test_agent_logger_error_level(self, log_service):
        """Test: AgentLogger.error() logs correctly."""
        set_log_service(log_service)
        logger = AgentLogger(log_service, "test", "Test", "agent")

        logger.error(
            message="Error occurred",
            method="test.method",
            line=99,
            thread_id="thread_123",
            extra={"error_code": "TEST_ERROR"},
        )

        assert log_service.queue_size() == 1

    def test_agent_logger_disabled_observability(self):
        """Test: AgentLogger works gracefully when observability disabled."""
        set_log_service(None)
        logger = AgentLogger(None, "test", "Test", "agent")

        # Should not raise when observability is None
        logger.info(
            message="Test",
            method="test.method",
            line=1,
            thread_id="thread",
        )

    def test_agent_logger_preserves_context(self, log_service):
        """Test: AgentLogger logs include tenant/agent context."""
        set_log_service(log_service)
        logger = AgentLogger(log_service, "acme-corp", "Acme Corp", "booking_agent")

        logger.info(
            message="Booking started",
            method="modules.agendamento.execute",
            line=156,
            thread_id="conv_123",
            extra={"booking_id": "bk_789"},
        )

        # Check queued entry
        batch = log_service._drain_queue()
        assert len(batch) == 1

        entry = batch[0]
        assert entry.tenant_id == "acme-corp"
        assert entry.tenant_name == "Acme Corp"
        assert entry.agent == "booking_agent"
        assert entry.message == "Booking started"


class TestPIIRedaction:
    """Tests for PII redaction in infrastructure layer."""

    def test_pii_redaction_password(self):
        """Test: password fields are redacted."""
        from modules.observability.infrastructure.loki_client import LokiLogSender

        sender = LokiLogSender("http://test", "token", "12345")
        data = {
            "message": "User login",
            "password": "secret123",
            "safe_field": "safe_value",
        }

        redacted = sender._redact_dict(data)

        assert redacted["password"] == "[REDACTED]"
        assert redacted["safe_field"] == "safe_value"

    def test_pii_redaction_token(self):
        """Test: token fields are redacted."""
        from modules.observability.infrastructure.loki_client import LokiLogSender

        sender = LokiLogSender("http://test", "token", "12345")
        data = {"api_token": "jwt_secret", "api_key": "key_123"}

        redacted = sender._redact_dict(data)

        assert redacted["api_token"] == "[REDACTED]"
        assert redacted["api_key"] == "[REDACTED]"

    def test_pii_redaction_nested(self):
        """Test: nested dicts are recursively redacted."""
        from modules.observability.infrastructure.loki_client import LokiLogSender

        sender = LokiLogSender("http://test", "token", "12345")
        data = {
            "user": {"name": "John", "password": "secret"},
            "api": {"key": "abc123", "url": "https://example.com"},
        }

        redacted = sender._redact_dict(data)

        assert redacted["user"]["password"] == "[REDACTED]"
        assert redacted["api"]["key"] == "[REDACTED]"
        assert redacted["user"]["name"] == "John"
        assert redacted["api"]["url"] == "https://example.com"

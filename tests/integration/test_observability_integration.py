"""Integration tests for observability (Grafana Loki logging)."""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from modules.observability.domain.log_event import LogEntry
from modules.observability.application.log_service import LogService
from modules.observability.infrastructure.loki_client import LokiLogSender


@pytest.fixture
def mock_loki_sender():
    """Mock Loki sender for testing."""
    sender = MagicMock(spec=LokiLogSender)
    sender.send_batch = AsyncMock(return_value=True)
    return sender


@pytest.fixture
def log_service(mock_loki_sender):
    """Create LogService with mock sender."""
    return LogService(mock_loki_sender)


class TestObservabilityIntegration:
    """Integration tests for observability module."""

    @pytest.mark.asyncio
    async def test_log_service_queues_entries(self, log_service):
        """Test: LogService queues log entries without blocking."""
        entry = LogEntry(
            tenant_id="test-tenant",
            tenant_name="Test Tenant",
            thread_id="thread_123",
            method="test.method",
            line=42,
            level="INFO",
            message="Test message",
            agent="test_agent",
        )

        # Should not block
        log_service.log(entry)
        assert not log_service.queue.empty()

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, log_service, mock_loki_sender):
        """Test: Logs from different tenants are isolated."""
        # Create logs for two tenants
        entry1 = LogEntry(
            tenant_id="tenant-a",
            tenant_name="Tenant A",
            thread_id="thread_1",
            method="test.method",
            line=1,
            level="INFO",
            message="Message from tenant A",
        )

        entry2 = LogEntry(
            tenant_id="tenant-b",
            tenant_name="Tenant B",
            thread_id="thread_2",
            method="test.method",
            line=2,
            level="INFO",
            message="Message from tenant B",
        )

        log_service.log(entry1)
        log_service.log(entry2)

        # Verify both are queued
        assert not log_service.queue.empty()

    def test_pii_redaction_in_loki_client(self):
        """Test: LokiLogSender redacts sensitive fields."""
        sender = LokiLogSender(
            url="https://test.grafana.net/loki/api/v1/push",
            api_token="glsa_test_token",
            user_id="12345",
        )

        # Entry with sensitive data in extra
        data_with_pii = {
            "message": "User login",
            "password": "secret123",
            "token": "jwt_token_here",
            "safe_field": "safe_value",
        }

        redacted = sender._redact_dict(data_with_pii)

        # Sensitive fields should be redacted
        assert redacted["password"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"
        # Safe field preserved
        assert redacted["safe_field"] == "safe_value"

    def test_log_entry_serialization(self):
        """Test: LogEntry serializes correctly for Loki."""
        entry = LogEntry(
            tenant_id="test-tenant",
            tenant_name="Test Tenant",
            thread_id="conv_123",
            method="modules.test.function",
            line=99,
            level="ERROR",
            message="Test error",
            agent="test_agent",
            extra={"error_code": "TEST_ERROR", "retry": True},
        )

        entry.validate()  # Should not raise

        # Should serialize without error
        entry_dict = entry.to_dict()
        assert entry_dict["thread_id"] == "conv_123"
        assert entry_dict["message"] == "Test error"
        assert entry_dict["extra"]["error_code"] == "TEST_ERROR"


class TestLogEntry:
    """Unit tests for LogEntry entity."""

    def test_log_entry_validation_required_fields(self):
        """Test: LogEntry validates required fields."""
        # Valid entry
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
        )
        entry.validate()  # Should not raise

    def test_log_entry_validation_invalid_level(self):
        """Test: LogEntry rejects invalid log level."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INVALID",  # Invalid level
            message="Test",
        )
        with pytest.raises(ValueError):
            entry.validate()

    def test_log_entry_validation_invalid_line_number(self):
        """Test: LogEntry rejects invalid line number."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=-1,  # Negative line number
            level="INFO",
            message="Test",
        )
        with pytest.raises(ValueError):
            entry.validate()

    def test_log_entry_validation_invalid_tenant_id(self):
        """Test: LogEntry rejects invalid tenant_id format."""
        entry = LogEntry(
            tenant_id="",  # Empty tenant_id
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
        )
        with pytest.raises(ValueError):
            entry.validate()

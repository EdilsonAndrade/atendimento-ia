"""Unit tests for LogEntry validation."""

import pytest
from datetime import datetime
from modules.observability.domain.log_event import LogEntry


class TestLogEntryValidation:
    """Tests for LogEntry entity validation."""

    def test_valid_log_entry(self):
        """Test: valid LogEntry passes validation."""
        entry = LogEntry(
            tenant_id="acme-corp",
            tenant_name="Acme Corporation",
            thread_id="conv_123",
            method="modules.agendamento.booking.execute",
            line=156,
            level="INFO",
            message="Booking confirmed",
            timestamp=datetime.utcnow(),
            agent="booking_agent",
            extra={"booking_id": "bk_789"},
        )

        entry.validate()  # Should not raise

    def test_tenant_id_required(self):
        """Test: tenant_id is required."""
        entry = LogEntry(
            tenant_id="",  # Empty
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            entry.validate()

    def test_tenant_id_max_length(self):
        """Test: tenant_id must be <= 50 chars."""
        entry = LogEntry(
            tenant_id="a" * 51,  # Too long
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            entry.validate()

    def test_tenant_id_invalid_chars(self):
        """Test: tenant_id must contain only alphanumeric, -, _."""
        entry = LogEntry(
            tenant_id="acme@corp",  # Invalid char: @
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="must contain only alphanumeric"):
            entry.validate()

    def test_invalid_line_negative(self):
        """Test: line must be >= 0."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=-1,  # Negative
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid line number"):
            entry.validate()

    def test_invalid_line_too_large(self):
        """Test: line must be <= 999999."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1000000,  # Too large
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid line number"):
            entry.validate()

    def test_invalid_level(self):
        """Test: level must be ERROR, WARN, INFO, or DEBUG."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INVALID",  # Invalid level
            message="Test",
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid level"):
            entry.validate()

    def test_valid_levels(self):
        """Test: all valid levels pass."""
        for level in ("ERROR", "WARN", "INFO", "DEBUG"):
            entry = LogEntry(
                tenant_id="test",
                tenant_name="Test",
                thread_id="thread",
                method="test.func",
                line=1,
                level=level,
                message="Test",
                timestamp=datetime.utcnow(),
            )
            entry.validate()  # Should not raise

    def test_message_required(self):
        """Test: message is required."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="",  # Empty
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid message"):
            entry.validate()

    def test_message_max_length(self):
        """Test: message must be <= 1000 chars."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="x" * 1001,  # Too long
            timestamp=datetime.utcnow(),
        )

        with pytest.raises(ValueError, match="Invalid message"):
            entry.validate()

    def test_extra_dict_max_keys(self):
        """Test: extra dict max 10 keys."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
            extra={f"key{i}": f"value{i}" for i in range(11)},  # 11 keys
        )

        with pytest.raises(ValueError, match="extra dict too large"):
            entry.validate()

    def test_extra_dict_valid_size(self):
        """Test: extra dict with 10 keys passes."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread",
            method="test.func",
            line=1,
            level="INFO",
            message="Test",
            timestamp=datetime.utcnow(),
            extra={f"key{i}": f"value{i}" for i in range(10)},  # 10 keys
        )

        entry.validate()  # Should not raise

    def test_log_entry_to_dict(self):
        """Test: LogEntry serializes to dict correctly."""
        entry = LogEntry(
            tenant_id="test",
            tenant_name="Test",
            thread_id="thread_123",
            method="test.func",
            line=42,
            level="INFO",
            message="Test message",
            timestamp=datetime(2026, 8, 26, 12, 34, 56),
            extra={"key": "value"},
        )

        data = entry.to_dict()

        assert data["thread_id"] == "thread_123"
        assert data["message"] == "Test message"
        assert data["extra"]["key"] == "value"
        assert data["timestamp"].endswith("Z")  # ISO format with Z

    def test_log_entry_to_loki_labels(self):
        """Test: LogEntry generates correct Loki labels."""
        entry = LogEntry(
            tenant_id="acme-corp",
            tenant_name="Acme Corp",
            thread_id="thread",
            method="modules.test.func",
            line=99,
            level="ERROR",
            message="Test",
            timestamp=datetime.utcnow(),
            agent="test_agent",
        )

        labels = entry.to_loki_labels()

        assert labels["tenant"] == "acme-corp|Acme Corp"
        assert labels["method"] == "modules.test.func"
        assert labels["line"] == "99"
        assert labels["level"] == "ERROR"
        assert labels["agent"] == "test_agent"

    def test_log_entry_immutable(self):
        """Test: LogEntry is immutable (frozen dataclass)."""
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

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.message = "Modified"

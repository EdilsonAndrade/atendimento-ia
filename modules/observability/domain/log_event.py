"""Domain entity: LogEntry (immutable log event)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class LogEntry:
    """Immutable domain entity representing a single logged event.

    Attributes:
        tenant_id: Tenant identifier (e.g., "acme-corp")
        tenant_name: Human-readable tenant name (e.g., "Acme Corporation")
        thread_id: Conversation/session ID for correlation
        method: Code location (module.function)
        line: Source code line number
        level: Log level (ERROR, WARN, INFO, DEBUG)
        message: Human-readable event description
        timestamp: UTC timestamp of event
        agent: Optional agent name (e.g., "booking_agent")
        extra: Optional custom context dict
    """

    tenant_id: str
    tenant_name: str
    thread_id: str
    method: str
    line: int
    level: str  # ERROR, WARN, INFO, DEBUG
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent: Optional[str] = None
    extra: Optional[dict] = None

    def validate(self) -> None:
        """Validate all fields; raise ValueError if invalid."""
        # tenant_id: alphanumeric with - and _, 2-50 chars
        if not self.tenant_id or len(self.tenant_id) > 50:
            raise ValueError(f"Invalid tenant_id: must be 2-50 chars, got {len(self.tenant_id)}")

        if not all(c.isalnum() or c in "-_" for c in self.tenant_id):
            raise ValueError("Invalid tenant_id: must contain only alphanumeric, -, _")

        # tenant_name: non-empty, <= 255 chars
        if not self.tenant_name or len(self.tenant_name) > 255:
            raise ValueError("Invalid tenant_name: must be 1-255 chars")

        # thread_id: non-empty, <= 255 chars
        if not self.thread_id or len(self.thread_id) > 255:
            raise ValueError("Invalid thread_id: must be 1-255 chars")

        # method: non-empty, <= 255 chars
        if not self.method or len(self.method) > 255:
            raise ValueError("Invalid method: must be 1-255 chars")

        # line: positive int, <= 999999
        if self.line < 0 or self.line > 999999:
            raise ValueError(f"Invalid line number: must be 0-999999, got {self.line}")

        # level: must be one of the valid levels
        valid_levels = {"ERROR", "WARN", "INFO", "DEBUG"}
        if self.level not in valid_levels:
            raise ValueError(f"Invalid level: must be one of {valid_levels}, got {self.level}")

        # message: non-empty, <= 1000 chars
        if not self.message or len(self.message) > 1000:
            raise ValueError(f"Invalid message: must be 1-1000 chars, got {len(self.message)}")

        # agent: optional, <= 100 chars if provided
        if self.agent and len(self.agent) > 100:
            raise ValueError(f"Invalid agent: must be <= 100 chars, got {len(self.agent)}")

        # extra: optional dict with <= 10 keys, all values JSON-serializable
        if self.extra:
            if not isinstance(self.extra, dict):
                raise TypeError("extra must be a dict")
            if len(self.extra) > 10:
                raise ValueError(f"extra dict too large: max 10 keys, got {len(self.extra)}")

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "thread_id": self.thread_id,
            "agent": self.agent,
            "method": self.method,
            "line": self.line,
            "level": self.level,
            "message": self.message,
            "extra": self.extra or {},
            "timestamp": self.timestamp.isoformat() + "Z",
        }

    def to_loki_labels(self) -> dict:
        """Convert to Loki label format for queryability."""
        labels = {
            "tenant": f"{self.tenant_id}|{self.tenant_name}",
            "method": self.method,
            "line": str(self.line),
            "level": self.level,
        }

        if self.agent:
            labels["agent"] = self.agent

        return labels

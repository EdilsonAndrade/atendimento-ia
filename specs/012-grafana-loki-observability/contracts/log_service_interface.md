# Contract: LogService Interface

**Status**: Specification for internal service contract  
**Used By**: Agent modules (booking, calendar, RAG, webhook handlers)  
**Stability**: Stable (backward-compatible additions only)

---

## Overview

The LogService exposes a single public method: `log()`. Agents call this method to record observable events (start, end, error, decision) with full context. The service is non-blocking; logs are queued for async transmission to Grafana Loki.

---

## Method: `log()`

### Signature

```python
def log(
    tenant_id: str,
    tenant_name: str,
    thread_id: str,
    agent: str | None,
    method: str,
    line: int,
    level: Literal["ERROR", "WARN", "INFO", "DEBUG"],
    message: str,
    extra: dict | None = None
) -> None:
```

### Parameters

| Name | Type | Required | Description | Example |
|------|------|----------|-------------|---------|
| `tenant_id` | str | **YES** | Unique tenant identifier | `"acme-corp"` |
| `tenant_name` | str | **YES** | Human-readable tenant name | `"Acme Corporation"` |
| `thread_id` | str | **YES** | Conversation/session ID for correlation | `"conv_abc123"` |
| `agent` | str \| None | No | Name of the agent (omit for non-agent ops) | `"booking_agent"` |
| `method` | str | **YES** | Code location: `module.function` | `"modules.agendamento.booking_tools.execute_booking"` |
| `line` | int | **YES** | Source code line number | `156` |
| `level` | Literal | **YES** | Severity: ERROR, WARN, INFO, DEBUG | `"ERROR"` |
| `message` | str | **YES** | Human-readable description | `"Booking confirmed"` |
| `extra` | dict | No | Custom context (JSON-serializable) | `{"booking_id": "bk_123"}` |

### Behavior

1. **Non-blocking**: Method returns immediately; logs are queued for async transmission
2. **Idempotent**: Multiple calls with identical parameters are safe; duplicates are acceptable
3. **Fail-silent**: If observability is disabled (env vars missing), logs are discarded silently
4. **Field validation**: Invalid field values raise `ValueError` at call time (fail fast)
5. **Timestamp**: Generated automatically (not passed by caller)

### Returns

`None` — Fire and forget. Callers should not await or check return value.

---

## Example Usage

```python
from modules.observability.interface.logger_factory import get_logger

# In a booking agent:
logger = get_logger(
    tenant_id="acme-corp",
    agent_name="booking_agent"
)

# Log operation start
logger.info(
    message="Booking started",
    method="modules.agendamento.booking_tools.execute_booking",
    line=156,
    thread_id=session.thread_id,
    extra={
        "booking_id": "bk_123",
        "time_slot": "2026-08-27 14:00"
    }
)

# Log success
logger.info(
    message="Booking confirmed",
    method="modules.agendamento.booking_tools.execute_booking",
    line=178,
    thread_id=session.thread_id,
    extra={"booking_id": "bk_123"}
)

# Log error
logger.error(
    message="Calendar unavailable",
    method="modules.agendamento.booking_tools.execute_booking",
    line=185,
    thread_id=session.thread_id,
    extra={
        "booking_id": "bk_123",
        "error_code": "CALENDAR_SERVICE_ERROR"
    }
)
```

---

## Field Validation

### `tenant_id`
- Pattern: `^[a-z0-9_-]{2,50}$`
- Error if: empty, uppercase, special chars (except `-` `_`), < 2 or > 50 chars
- Raise: `ValueError("Invalid tenant_id format")`

### `tenant_name`
- Constraint: non-empty, ≤ 255 chars
- Error if: empty or > 255 chars
- Raise: `ValueError("Invalid tenant_name length")`

### `thread_id`
- Constraint: non-empty, ≤ 255 chars
- Error if: empty or > 255 chars
- Raise: `ValueError("Invalid thread_id")`

### `method`
- Pattern: Suggested `^[a-z_][a-z0-9_.]*$` (module.function notation)
- Error if: empty
- Raise: `ValueError("Invalid method format")`

### `line`
- Constraint: positive integer, ≤ 999999
- Error if: < 0 or > 999999
- Raise: `ValueError("Invalid line number")`

### `level`
- Allowed: `"ERROR"`, `"WARN"`, `"INFO"`, `"DEBUG"`
- Error if: any other value
- Raise: `ValueError("Invalid log level")`

### `message`
- Constraint: non-empty, ≤ 1000 chars
- Error if: empty or > 1000 chars
- Raise: `ValueError("Invalid message length")`

### `extra`
- Constraint: dict with ≤ 10 keys; values must be JSON-serializable
- Error if: non-dict, > 10 keys, circular references, non-serializable values
- Raise: `ValueError("Invalid extra data")`, `TypeError("Non-serializable value in extra")`

---

## Performance Guarantees

- **Call latency**: < 1 ms (queue put operation)
- **Memory overhead**: ~500 bytes per queued log entry
- **Queue capacity**: 10,000 entries (blocking put if queue full; fail-safe)
- **Throughput**: 10,000+ entries per minute to Loki

---

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Loki endpoint unreachable | Retry with exponential backoff; logs retained in memory queue; oldest dropped if queue full |
| Invalid field values | Raise `ValueError`; log not queued |
| Observability disabled (env vars missing) | Silent discard; no error |
| App crash | In-memory queue lost; logs not recovered (acceptable for operational data) |

---

## Compatibility

- **Added fields in `extra`**: Backward compatible (schema-free)
- **New `level` values**: Backward compatible (only if added to enum)
- **Method signature changes**: Breaking; must be deprecated with notice period
- **Removal of fields**: Breaking; requires major version

---

## Testing Responsibilities

**Unit Tests** (`modules/observability/test_log_service.py`):
- ✅ Happy path: valid parameters
- ✅ Error path: invalid parameters raise
- ✅ PII redaction: sensitive fields removed
- ✅ Non-blocking: method returns immediately
- ✅ Fail-silent when disabled

**Integration Tests** (`tests/integration/test_observability_integration.py`):
- ✅ End-to-end: logs appear in Loki
- ✅ Multi-tenant isolation: tenant A's logs invisible to tenant B
- ✅ HTTP contract: correct Loki endpoint, Bearer auth

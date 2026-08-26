# Phase 0 Research: Grafana + Loki Observability

**Date**: 2026-08-26  
**Status**: Complete — all clarifications resolved

## Research Summary

This document captures technical decisions made during Phase 0 research for the observability feature. All architectural unknowns from the plan have been resolved based on project constraints and best practices.

---

## Decision 1: Logging Library Choice

**Context**: Python offers many logging options (`logging` stdlib, Structlog, Python-JSON-Logger, etc.)

**Decision**: Use Python's built-in `logging` module with structured dict payloads

**Rationale**:
- Zero external dependency (already in stdlib)
- Already integrated into FastAPI/Uvicorn ecosystem (familiar to team)
- `logging.Formatter` can emit JSON via custom formatters (no external lib needed)
- Minimal performance overhead for async queue scenario
- `QueueHandler` + `QueueListener` (stdlib) handles async transmission without extra packages

**Alternatives Considered**:
- **Structlog**: Cleaner API, but adds dependency + learning curve; overkill for current volume
- **Python-JSON-Logger**: Simpler JSON emission than custom formatter, but still an extra dependency
- **LangChain observability**: Vendor-specific, not needed for general-purpose logging

**Implementation**: Use `logging.QueueHandler` → `logging.QueueListener` → custom Loki sender thread

---

## Decision 2: Log Transmission Pattern (Sync vs. Async)

**Context**: Requests to Loki can block. System must not delay response to agents/users.

**Decision**: Queue-based async transmission (in-process thread, not distributed job queue)

**Rationale**:
- Loki endpoint can be slow (100ms+ network latency in some deployments)
- Blocking on HTTP to Loki would degrade agent response time
- In-process `Queue` + background thread is lightweight and doesn't require Redis/Celery
- Logs are non-critical operational data; losing a batch on crash is acceptable (will retry after restart)
- Existing project has no job queue infrastructure; adding Celery would violate principle of "minimally invasive"

**Alternatives Considered**:
- **Sync transmission (blocking)**: Too risky; can cascade failures if Loki slow
- **Celery/distributed queue**: Overkill; adds operational burden and Docker dependency
- **Buffering to disk**: More complex; in-memory queue sufficient for expected volume

**Implementation**: `logging.QueueHandler` in main thread pushes to queue; background thread runs `QueueListener` that batches events and sends to Loki

---

## Decision 3: Loki HTTP Client Library

**Context**: No existing Loki client in project. Need to choose: `requests`, `httpx`, custom urllib3

**Decision**: Use `requests` library

**Rationale**:
- Already in FastAPI dependency tree (stable, familiar)
- Simple blocking HTTP (sufficient for background thread sending)
- Supports Bearer token auth directly in `requests.auth`
- No async needed (background thread is already async from app perspective)
- Retry logic simple to add via backoff library if needed

**Alternatives Considered**:
- **httpx**: More modern, but adds dependency; `requests` already available
- **urllib3 directly**: Lower-level; would need to build retry logic manually
- **aiohttp**: Async, but background thread is not async context; would add complexity

**Implementation**: `requests.post()` with `Authorization: Bearer {token}` header to Loki `/loki/api/v1/push` endpoint

---

## Decision 4: Data Model for Logs

**Context**: What fields must every log contain? How are custom data represented?

**Decision**: Core fields (tenant, thread, agent, method, line, level, timestamp) + message + structured `extra` dict for context

**Rationale**:
- Core fields map directly to Loki labels for efficient querying
- Extra dict allows agent-specific context (e.g., booking ID, calendar event ID) without schema explosion
- Message is human-readable fallback; structured data in labels + extra for filtering
- Thread ID enables tracing related operations across modules

**Field Definitions**:
```python
{
  "tenant_id": "...",           # (required)
  "tenant_name": "...",         # (required)
  "thread_id": "...",           # (required)
  "agent": "optional",          # agent name if this log is from an agent
  "method": "module.function",  # where in code this occurred
  "line": 123,                  # line number in source
  "level": "ERROR|WARN|INFO|DEBUG",
  "timestamp": "2026-08-26T12:34:56Z",
  "message": "...",
  "extra": {                    # custom data per agent/operation
    "booking_id": "...",
    "calendar_event_id": "..."
  }
}
```

---

## Decision 5: PII Redaction Strategy

**Context**: Agents handle customer data (names, emails, phone numbers, calendar details). Logs must not expose PII.

**Decision**: Pre-transmission field-level redaction: filter known-sensitive field names before HTTP send

**Rationale**:
- PII exposure is a compliance risk and was explicitly required in spec ("MUST NOT log passwords/tokens")
- Redacting at transmission layer (not ingestion) is faster and centralizes policy
- Field-name-based filtering (e.g., `password`, `token`, `secret`, `key`) catches most common cases
- Custom agent code can override with explicit "this data is safe to log" wrapper if needed

**Alternatives Considered**:
- **Regex-based content filtering**: Too expensive (every string scanned); misses context
- **Allowlist approach**: Would require knowing every safe field upfront; not maintainable
- **Application layer filtering**: Would require every agent to remember; error-prone

**Implementation**: Redaction function in `infrastructure/loki_client.py` strips or replaces values of any key matching `/(password|token|secret|api_key|authorization|credential)/i`

---

## Decision 6: Environment Variable Configuration

**Context**: Loki endpoint and API token must be configurable per environment (dev, staging, prod)

**Decision**: Two env vars, with safe defaults (logging disabled if not set)

- `GRAFANA_LOKI_URL`: Loki push endpoint (e.g., `https://your-org.grafana.net/loki/api/v1/push`)
- `GRAFANA_LOKI_API_TOKEN`: Bearer token from Grafana Cloud API key
- Default: If either is missing, observability is a no-op (logs discarded at queue level)

**Rationale**:
- No-op default allows dev/test environments to run without Grafana Cloud account
- Matches existing project convention (`pydantic-settings` in `app/core/config.py`)
- Fail-safe: missing token won't crash the system

**Implementation**: `pydantic.Settings` in `app/core/observability_config.py`

---

## Decision 7: Integration with Existing Agent Code (Minimal Invasion)

**Context**: Agents live in `modules/agendamento`, `modules/ia`, `modules/webhook`, etc. How to add logging without refactoring?

**Decision**: Inject a logger factory function; agents call it at key points (start, error, decision)

**Rationale**:
- Avoids full rewrite of legacy modules
- Follows existing dependency-injection pattern in project (FastAPI `Depends()`)
- Agents remain testable: can swap real logger for mock
- Logging remains optional at runtime (can be disabled via env)

**Alternatives Considered**:
- **Rewrite all agents to use Clean Architecture**: Violates legacy migration policy (EDI-45 retrofit not scheduled)
- **Global logger instance**: Works, but doesn't play well with multi-tenancy (can mix tenant IDs)
- **Logging decorators**: Cleaner for methods, but loses context inside async agent graph traversal

**Implementation**: 
```python
# In modules/observability/interface/logger_factory.py
def get_logger(tenant_id: str, agent_name: str) -> AgentLogger:
    ...

# In agent code:
logger = get_logger(tenant_id, "booking_agent")
logger.info("Booking started", extra={"booking_id": "123"})
```

---

## Decision 8: Testing Strategy

**Context**: How to test logging without blocking on real Loki calls?

**Decision**: Unit tests mock the HTTP layer; integration tests use `httpx.MockTransport`

**Rationale**:
- Unit tests verify business logic (PII redaction, label formatting) fast
- Integration tests verify HTTP contract (correct endpoint, auth header) without real Loki
- No external dependencies on Grafana Cloud for running tests
- Existing project uses pytest + httpx mocking; consistent pattern

**Implementation**:
- `modules/observability/test_log_service.py`: mock `loki_client.send_batch()`
- `tests/integration/test_observability_integration.py`: mock `requests.post()` via `httpx.MockTransport`

---

## Decision 9: Alerting (Phase 2, Out of Scope Here)

**Context**: Spec mentions alert rules in Grafana for errors. Who configures them?

**Decision**: Out of scope for code implementation. Manual setup in Grafana UI during Phase 2 (after logs are flowing).

**Rationale**:
- Alert rules are Grafana UI configuration, not code
- Can be documented in `quickstart.md` as "post-launch steps"
- No code changes needed; Loki can fire alerts based on LogQL queries

---

## Summary of Resolutions

All NEEDS CLARIFICATION items from the plan have been resolved:

| Item | Resolution |
|------|-----------|
| Logging library | Python `logging` stdlib + `QueueHandler/QueueListener` |
| Transmission | In-process async queue + background thread |
| HTTP client | `requests` library (already available) |
| Data model | Core fields → Loki labels + structured extra |
| PII safety | Pre-transmission field-level redaction |
| Configuration | Two env vars (`GRAFANA_LOKI_URL`, `GRAFANA_LOKI_API_TOKEN`) with safe defaults |
| Agent integration | Logger factory injected via dependency, minimal invasion |
| Testing | Unit mocks + integration via `httpx.MockTransport` |
| Alerting | Manual UI setup in Phase 2 |

**Confidence Level**: High — all decisions align with project constraints and best practices.

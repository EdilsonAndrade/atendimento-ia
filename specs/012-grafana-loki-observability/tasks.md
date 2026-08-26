# Implementation Tasks: Grafana + Loki Observability

**Feature**: EDI-66 — Grafana + Loki Observability  
**Branch**: `012-grafana-loki-observability`  
**Date**: 2026-08-26  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## Executive Summary

Total Tasks: **32** | Estimated Duration: **5-7 days** (1 developer)

### Task Breakdown by Story

| User Story | Priority | Tasks | Est. Hours |
|-----------|----------|-------|-----------|
| Monitor Agent Logs in Real-Time | P1 | 18 | 18 |
| Query & Visualize Logs | P2 | 8 | 8 |
| Alert on Errors | P3 | 4 | 4 |
| **Setup & Foundational** | — | 8 | 8 |
| **Polish & Cross-Cutting** | — | 3 | 3 |
| **Total** | — | **32** | **41** |

### Parallel Opportunities

- **P1 & P2 independent**: Can start P2 foundational tasks before P1 complete
- **Infrastructure & domain layers**: Domain + Infrastructure layers can be developed in parallel
- **Tests**: Unit & integration tests can run in parallel with implementation

### MVP Scope (First Iteration)

**Recommended MVP = Phase 1 + Phase 2 + Phase 3 (P1 story only)**

Deploy with:
- ✅ Core logging to Loki functional
- ✅ Multi-tenant isolation working
- ✅ PII redaction active
- ✅ Unit + integration tests passing

**Defer to Phase 2**:
- P2 dashboard (can be manual in Grafana)
- P3 alert rules (can be created in Grafana UI post-launch)

---

## Phase 1: Setup & Project Initialization

### Goal

Establish project structure, configuration, and dependencies for observability module.

### Tasks

- [ ] T001 Create `modules/observability/` directory structure per Clean Architecture (domain/, application/, infrastructure/, interface/)
- [ ] T002 Create `modules/observability/__init__.py` (module entry point)
- [ ] T003 Create `.env.example` with `GRAFANA_LOKI_URL` and `GRAFANA_LOKI_API_TOKEN` placeholders and documentation
- [ ] T004 Update `requirements.txt` to ensure `requests` library is included (already present, verify version ≥ 2.28.0)
- [ ] T005 Create `app/core/observability_config.py` — Pydantic Settings for Loki configuration (env vars with safe defaults)
- [ ] T006 Create `app/core/observability.py` — Main observability wiring (init function for app startup)
- [ ] T007 Update `app/main.py` to call `init_observability()` in `@app.on_event("startup")` hook
- [ ] T008 Create `tests/integration/test_observability_integration.py` (test file structure, imports, fixtures for mock Loki)

### Independent Test Criteria

- ✅ Module structure matches Clean Architecture layout
- ✅ Environment variables load with safe defaults
- ✅ App starts without errors when GRAFANA_LOKI_* vars missing

---

## Phase 2: Foundational & Infrastructure (Blocking Prerequisites)

### Goal

Implement core domain entities, ports, and low-level Loki transmission logic. These tasks block all user stories.

### Tasks

- [ ] T009 [P] Create `modules/observability/domain/log_event.py` — LogEntry dataclass with validation (tenant_id, thread_id, method, line, level, message, extra)
- [ ] T010 [P] Create `modules/observability/domain/ports/log_sender.py` — Abstract LogSender port (send_batch method)
- [ ] T011 [P] Create `modules/observability/infrastructure/loki_client.py` — LokiLogSender adapter class:
  - HTTP POST to Loki endpoint
  - PII redaction (password, token, secret, key, auth fields)
  - Retry logic (exponential backoff for 5xx/429)
  - Response handling (204 success, 4xx fail-fast, 5xx retry)
- [ ] T012 [P] Create `modules/observability/infrastructure/log_sender_factory.py` — Factory function returning real or no-op sender based on env
- [ ] T013 Create `modules/observability/infrastructure/__init__.py`
- [ ] T014 Create `modules/observability/domain/__init__.py`
- [ ] T015 Create `modules/observability/domain/ports/__init__.py`
- [ ] T016 Create `modules/observability/test_log_event_validation.py` — Unit tests for LogEntry validation (tenant_id format, line range, level enum)

### Independent Test Criteria

- ✅ LogEntry validates all required fields
- ✅ LogEntry rejects invalid tenant_id, line, level
- ✅ LokiLogSender redacts sensitive fields
- ✅ Factory returns no-op sender when env vars missing

---

## Phase 3: User Story P1 — Monitor Agent Execution Logs in Real-Time

### Goal

Enable operators to monitor agent lifecycle events (start, end, error, decision) with full context (tenant, thread, method, line, agent).

### Story Dependencies

- Blocks: Phase 4 (P2), Phase 5 (P3)
- Unblocked by: Nothing (depends only on Phase 2)

### Tasks

**Application Layer (Use Case)**:

- [ ] T017 [US1] Create `modules/observability/application/log_service.py` — LogService class:
  - `__init__(sender: LogSender, batch_size=100, flush_interval_sec=2.0)`
  - `log(entry: LogEntry)` method (queue non-blocking)
  - `_flush_loop()` background task (drain queue, batch, send)
  - `start()` / `stop()` lifecycle methods
- [ ] T018 [US1] Create `modules/observability/application/__init__.py`

**Interface Layer (Logger Factory)**:

- [ ] T019 [US1] Create `modules/observability/interface/logger_factory.py` — AgentLogger class:
  - `get_logger(tenant_id, tenant_name, agent=None)` factory function
  - `AgentLogger.info()`, `.error()` convenience methods with (message, method, line, thread_id, extra)
  - Pre-populate tenant/agent context (capture at logger creation)
- [ ] T020 [US1] Create `modules/observability/interface/__init__.py`

**Unit Tests**:

- [ ] T021 [P] [US1] Create `modules/observability/test_log_service.py` — Unit tests:
  - Mock LogSender port (no real Loki calls)
  - Test: log() queues entry without blocking (< 1ms)
  - Test: flush_loop batches and calls sender (happy path)
  - Test: PII redaction removes passwords/tokens
  - Test: Invalid LogEntry fields raise ValueError
  - Test: Disabled observability (no-op sender) discards logs silently
  - Test: Queue overflow handling (oldest dropped if full)
- [ ] T022 [P] [US1] Create `modules/observability/test_logger_factory.py` — Unit tests:
  - Test: get_logger() returns AgentLogger with tenant context
  - Test: AgentLogger.info() creates valid LogEntry
  - Test: AgentLogger methods non-blocking

**Integration Tests**:

- [ ] T023 [US1] Implement `tests/integration/test_observability_integration.py` — Integration tests:
  - Mock Loki HTTP endpoint via httpx.MockTransport
  - Test: End-to-end log transmission (app logs → queue → HTTP POST)
  - Test: Multi-tenant isolation (tenant A logs invisible to tenant B query)
  - Test: HTTP contract validation (correct endpoint, Bearer auth header, payload format)
  - Test: Retry logic (5xx response triggers retry, 401 fails fast)
  - Test: Real LogEntry serialization to Loki format

**Agent Integration (Non-Breaking)**:

- [ ] T024 [P] [US1] Update `modules/agendamento/booking_tools.py` to use observability logger:
  - Add import: `from modules.observability.interface.logger_factory import get_logger`
  - At operation start: `logger.info("Booking started", method="...", line=..., thread_id=..., extra={"booking_id": "..."})`
  - At operation end: `logger.info("Booking confirmed", ...)`
  - On error: `logger.error("Booking failed: ...", ...)`
  - Minimal changes (2-3 log statements per flow)
- [ ] T025 [P] [US1] Update `modules/agendamento/consulta_agenda_tool.py` similarly (availability check logs)
- [ ] T026 [P] [US1] Update `modules/google_calendar/google_calendar_service.py` similarly (calendar event creation logs)
- [ ] T027 [P] [US1] Update `modules/ia/agent_graph.py` similarly (agent decision point logs)

### Independent Test Criteria (P1)

- ✅ Logs appear in mock Loki within 2 seconds
- ✅ LogEntry validates and serializes correctly
- ✅ Tenant A's logs never visible to tenant B (query isolation)
- ✅ PII fields redacted (no passwords/tokens in payload)
- ✅ Agent code can call logger without blocking
- ✅ All unit + integration tests pass

---

## Phase 4: User Story P2 — Query & Visualize Logs by Tenant/Operation

### Goal

Operators can visually inspect logs in Grafana dashboard filtered by tenant, operation, method, agent.

### Story Dependencies

- Blocks: Phase 5 (P3)
- Requires: Phase 3 (P1) complete (logs flowing to Loki)

### Tasks

**Grafana Dashboard (Manual UI Setup)**:

- [ ] T028 [US2] Document Grafana dashboard creation steps in `specs/012-grafana-loki-observability/grafana-dashboard.md`:
  - Step 1: Create new dashboard
  - Step 2: Add panel with LogQL query `{tenant="acme-corp*"} | json`
  - Step 3: Add filters (dropdown for tenant, operation, method, agent)
  - Step 4: Configure table view (show thread_id, method, line, message, timestamp)
  - Step 5: Save dashboard (no code change, manual in Grafana UI)
- [ ] T029 [US2] Document LogQL query examples for operators in quickstart.md (already in data-model.md; just reference)

**Optional: Dashboard Provisioning (Advanced)**:

- [ ] T030 [P] [US2] Create `modules/observability/infrastructure/grafana_provisioning.py` (optional, low priority):
  - Functions to programmatically create Grafana dashboard via Grafana API
  - Can be deferred to post-launch phase if UI manual setup sufficient

### Independent Test Criteria (P2)

- ✅ Dashboard can filter logs by tenant (manual verification)
- ✅ Dashboard displays method, line, agent in table
- ✅ LogQL queries return correct log subset within 1 second
- ✅ Docs clear enough for operator to replicate dashboard

---

## Phase 5: User Story P3 — Alert on Agent Errors

### Goal

Operations receive automatic notifications (email/Slack) when agent errors occur, enabling rapid response.

### Story Dependencies

- Requires: Phase 3 (P1) complete (error logs flowing to Loki)

### Tasks

**Grafana Alert Rule (Manual Setup)**:

- [ ] T031 [US3] Document Grafana alert creation steps in `specs/012-grafana-loki-observability/grafana-alerts.md`:
  - Step 1: Create alert rule from dashboard panel
  - Step 2: LogQL query: `{tenant="acme-corp*", level="ERROR"} | json | count by (method)`
  - Step 3: Condition: `count > 0 in last 5 minutes`
  - Step 4: Notification channel (email, Slack webhook, etc.)
  - Step 5: Save and test (manual in Grafana UI)
- [ ] T032 [US3] Document alert testing procedure (trigger intentional error, verify notification received)

### Independent Test Criteria (P3)

- ✅ Alert fires when error log count > 0 in 5-minute window (manual verification)
- ✅ Notification sent to configured channel within 1 minute
- ✅ Docs clear for operator to set up alerts for their tenant

---

## Phase 6: Polish & Cross-Cutting Concerns

### Goal

Ensure production readiness, monitoring, and long-term maintainability.

### Tasks

- [ ] T033 [P] Add observability metrics (optional, low priority):
  - Track in logs: queue depth, flush latency, Loki response time
  - Can be deferred if logs themselves sufficient for monitoring
- [ ] T034 Create `docs/OBSERVABILITY.md` — Operator reference guide:
  - Architecture overview
  - How to query logs
  - Common troubleshooting (no logs appearing, partial logs, duplicates)
  - Dashboard provisioning steps
  - Alert creation steps
- [ ] T035 Update project README.md to mention observability feature and link to operator guide

---

## Task Execution Order & Dependencies

### Parallel Execution Examples

**Example 1: Setup Phase (T001-T008)**
- Can run all in sequence (no parallelization needed, short phase)

**Example 2: Foundational Phase (T009-T016)**
- T009-T012: Can run **in parallel** (different files, no dependencies)
- T013-T015: Wait for T009-T012 complete (imports)
- T016: Wait for T009 complete (depends on LogEntry)

**Example 3: P1 Story (T017-T027)**
- T017-T018: Sequential (Application layer)
- T019-T020: Sequential (Interface layer)
- T021-T022: Can run **in parallel** with T017-T020 (mocking, no real implementation needed yet)
- T023: Wait for T017-T020 complete (integration test)
- T024-T027: Can run **in parallel** (different agent modules, no dependencies)

**Example 4: P2 Story (T028-T030)**
- T028-T029: Sequential (docs)
- T030: Optional, can defer

---

## Implementation Strategy

### MVP First Approach

**Tier 1 (MVP = Production Ready)**:
1. Phase 1: Setup ✅
2. Phase 2: Foundational (domain, infrastructure) ✅
3. Phase 3: P1 Story (logging working end-to-end) ✅
4. **Deploy & Monitor**

**Tier 2 (Post-Launch Quality)**:
5. Phase 4: P2 Story (dashboard docs) ✅
6. Phase 5: P3 Story (alert docs) ✅
7. Phase 6: Polish & docs ✅

### Incremental Delivery

- **Day 1-2**: Phases 1-2 (setup + infrastructure)
- **Day 3-5**: Phase 3 (P1 + tests + agent integration)
- **Day 6**: Phase 4 (docs)
- **Day 7**: Phase 5 (alert docs) + Phase 6 (polish)

---

## Validation Checklist

**Before Phase 1 → Phase 2**:
- [ ] Project structure created
- [ ] Env vars documented
- [ ] App starts cleanly

**Before Phase 2 → Phase 3**:
- [ ] LogEntry validates correctly
- [ ] LokiLogSender redacts PII
- [ ] Factory pattern working

**Before Phase 3 → Phase 4**:
- [ ] Logs appear in mock Loki
- [ ] Multi-tenant isolation verified
- [ ] Unit tests pass (all T021-T022)
- [ ] Integration tests pass (T023)

**Before Phase 4 → Phase 5**:
- [ ] Dashboard created and querying logs
- [ ] Query performance acceptable (< 1s)

**Before Phase 5 → Phase 6**:
- [ ] Alert rules firing on errors
- [ ] Notifications delivered

**Before Deploy**:
- [ ] All tasks complete
- [ ] Code review passed
- [ ] No PII in logs (verified via log inspection)
- [ ] Docs clear and complete

---

## Test Strategy (Summary)

### Unit Tests (Tier 1: Fast Feedback)
- LogEntry validation (T021, T022)
- PII redaction logic (T021)
- Factory pattern (T022)
- No real HTTP or Loki calls

### Integration Tests (Tier 2: Contract Verification)
- Mock Loki endpoint (T023)
- End-to-end flow (log → queue → HTTP → Loki)
- Multi-tenant isolation (T023)
- HTTP contract compliance (T023)

### Manual Testing (Tier 3: Production Confidence)
- Real Grafana Cloud instance (after Phase 3)
- Dashboard queries (Phase 4)
- Alert triggering (Phase 5)
- No regressions in agent flows (T024-T027)

---

## Notes for Implementation

1. **No Breaking Changes**: All agent integrations (T024-T027) use new logger factory; existing code paths unchanged
2. **Graceful Degradation**: If Loki unreachable, logs silently discarded (no app failure)
3. **Test Coverage Target**: > 80% code coverage for domain + application + infrastructure layers
4. **Performance Baseline**: Log call < 1ms; flush to Loki < 2s latency observed in tests
5. **Documentation Priority**: Grafana docs (T028-T032) must be very clear for operators (non-technical audience)

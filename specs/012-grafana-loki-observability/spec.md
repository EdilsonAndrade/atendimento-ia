# Feature Specification: Grafana + Loki Observability

**Feature Branch**: `edilsonaandrade/edi-66-implementar-observabilidade-com-grafana-loki-para`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: EDI-66: Implementar observabilidade com Grafana + Loki para rastreamento de agentes

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Monitor Agent Execution Logs in Real-time (Priority: P1)

System operators need to monitor what's happening in agents (start, end, errors, decisions) with full context (tenant, thread, method, line number) to debug issues and audit operations.

**Why this priority**: Core capability - without this, observability doesn't exist. Critical for debugging production issues and auditing.

**Independent Test**: Deploy logger to single agent endpoint, execute operation, verify logs appear in Grafana dashboard in real-time with correct structure.

**Acceptance Scenarios**:

1. **Given** an agent executes an operation, **When** the operation starts, **Then** a log entry is created with tenant_id, thread_id, agent name, method name, line number
2. **Given** an agent completes an operation successfully, **When** execution ends, **Then** a success log entry with final state is sent to Loki
3. **Given** an agent encounters an error, **When** the error occurs, **Then** an error log with stack trace (method, line) is sent to Loki immediately
4. **Given** an agent makes a decision, **When** the decision is made, **Then** decision context is logged with decision outcome and reasoning

---

### User Story 2 - Query and Visualize Logs by Tenant and Operation (Priority: P2)

Operations team needs a visual dashboard to quickly find and analyze logs for specific tenants, operations, and agents without writing complex queries.

**Why this priority**: High value but depends on P1 data being available. Enables efficient troubleshooting.

**Independent Test**: Dashboard loads with sample logs from Story 1, can filter by tenant/operation/agent, and displays logs in readable format.

**Acceptance Scenarios**:

1. **Given** logs exist in Loki from Story 1, **When** user opens dashboard, **Then** logs are displayed grouped by tenant
2. **Given** dashboard is open, **When** user filters by operation name, **Then** only logs for that operation are shown
3. **Given** dashboard is open, **When** user filters by agent, **Then** only logs from that agent are shown
4. **Given** dashboard is open, **When** user views error logs, **Then** method name and line number are clearly visible

---

### User Story 3 - Alert on Agent Errors (Priority: P3)

Operations team needs automatic notifications when agents encounter errors to respond quickly to issues.

**Why this priority**: Important for incident response but can be added after core logging works. Depends on P1 logs being reliable.

**Independent Test**: Trigger intentional error in agent, verify alert rule fires and notification is sent.

**Acceptance Scenarios**:

1. **Given** error logs exist in Loki, **When** error count exceeds threshold in 5-minute window, **Then** alert is triggered
2. **Given** alert is triggered, **When** alert action executes, **Then** notification is sent to configured endpoint (email/Slack/webhook)

---

### Edge Cases

- What happens when tenant_id or thread_id is missing from context? (Default to "unknown" if not available, log a warning)
- How does system handle sensitive data accidentally included in logs? (Pre-emptive sanitization, never log passwords/tokens/PII)
- What happens if Loki endpoint is unreachable? (Queue logs locally, retry with exponential backoff, log failures to stderr)
- How are sensitive fields like authentication tokens filtered before sending? (Implement field-level redaction rules)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST send agent logs to Grafana Loki with Bearer token authentication
- **FR-002**: System MUST include in every log entry: tenant_id, tenant_name, thread_id, method name, line number, and agent name (if applicable)
- **FR-003**: System MUST NOT log passwords, API tokens, or sensitive authentication data
- **FR-004**: System MUST track agent lifecycle events: operation start, operation end, errors with stack traces, and decision points
- **FR-005**: System MUST use structured labels in Loki: `tenant="TENANT_ID|TENANT_NAME"`, `operation="operation_name"`, `method="method_name"`, `line="line_number"`, `agent="agent_name"`
- **FR-006**: System MUST support real-time log transmission to Loki with configurable batch size and flush interval
- **FR-007**: System MUST gracefully handle Loki unavailability by queueing logs locally and retrying
- **FR-008**: Grafana dashboard MUST display logs searchable and filterable by tenant, operation, method, and agent
- **FR-009**: System MUST implement alert rules in Grafana that fire when error log count > 0 in 5-minute window
- **FR-010**: System MUST store Loki endpoint URL and authentication token in environment variables (not hardcoded)

### Key Entities

- **LogEntry**: Represents a single log event with tenant context, thread ID, execution method, line number, agent name, timestamp, and message content
- **AlertRule**: Represents an alert condition (error threshold, time window) that triggers notifications when met
- **LokiLabel**: Represents structured label for log categorization (tenant, operation, method, line, agent)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Logs appear in Grafana Loki dashboard within 2 seconds of being generated
- **SC-002**: Dashboard can filter logs by tenant, operation, method, agent, and displays results in under 1 second
- **SC-003**: 100% of logs are free of password/token/sensitive data leaks (auditable via log review)
- **SC-004**: Alert rules fire within 1 minute of error log being generated
- **SC-005**: System can handle 10,000+ log entries per minute without dropping events
- **SC-006**: Loki free tier (50GB/month) is sufficient for expected log volume

## Assumptions

- Grafana Cloud account already exists with Loki enabled and valid API token
- Python `requests` library is available in project dependencies
- Environment variables can be configured for Loki endpoint URL and authentication token
- Existing agents have defined entry/exit points and error handling where logging can be instrumented
- No requirement to implement custom Loki client; `requests` library is sufficient
- Thread ID and tenant ID are available in agent execution context
- Stack traces are automatically captured in exception handlers
- Log retention policy: minimum 7 days, maximum 30 days (within Loki free tier limits)

# Contract: Grafana Loki HTTP Push API

**Status**: External API specification (Grafana Cloud)  
**Used By**: `modules.observability.infrastructure.loki_client.LokiLogSender`  
**Reference**: [Loki Push API docs](https://grafana.com/docs/loki/latest/api/#post-lokiapiv1push)

---

## Overview

Logs are transmitted to Grafana Loki via HTTP POST to the `/loki/api/v1/push` endpoint. This contract defines the request format, authentication, and expected responses.

---

## Endpoint

**URL**: `https://<YOUR_ORG>.grafana.net/loki/api/v1/push`

**Method**: `POST`

**Authentication**: Bearer token in `Authorization` header

---

## Request Format

### Headers

```http
POST /loki/api/v1/push HTTP/1.1
Host: <YOUR_ORG>.grafana.net
Authorization: Bearer <GRAFANA_LOKI_API_TOKEN>
Content-Type: application/json
Content-Length: <bytes>
```

### Body

Loki push API expects a JSON object with `streams` array:

```json
{
  "streams": [
    {
      "stream": {
        "tenant": "TENANT_ID|TENANT_NAME",
        "operation": "operation_name",
        "method": "module.function",
        "line": "123",
        "agent": "agent_name",
        "level": "ERROR"
      },
      "values": [
        [
          "1693062285000000000",
          "{...json log entry as string...}"
        ]
      ]
    }
  ]
}
```

**Explanation**:

- **`stream`**: Labels (indexed dimensions for filtering)
  - `tenant`: `"TENANT_ID|TENANT_NAME"` (e.g., `"acme-corp|Acme Corporation"`)
  - `operation`, `method`, `line`, `agent`, `level`: Loki query dimensions
  
- **`values`**: Array of [timestamp, log_line] tuples
  - `timestamp`: Nanoseconds since epoch (as string)
  - `log_line`: JSON-stringified log entry

### Batch Example

Sending 3 logs from different operations:

```json
{
  "streams": [
    {
      "stream": {
        "tenant": "acme-corp|Acme Corporation",
        "operation": "confirm_booking",
        "method": "modules.agendamento.booking_tools.confirm_booking",
        "line": "156",
        "agent": "booking_agent",
        "level": "INFO"
      },
      "values": [
        [
          "1693062285123456000",
          "{\"thread_id\":\"conv_abc123\",\"message\":\"Booking confirmed\",\"extra\":{\"booking_id\":\"bk_789\"}}"
        ]
      ]
    },
    {
      "stream": {
        "tenant": "acme-corp|Acme Corporation",
        "operation": "check_availability",
        "method": "modules.agendamento.consulta_agenda_tool.check_availability",
        "line": "89",
        "agent": "calendar_agent",
        "level": "INFO"
      },
      "values": [
        [
          "1693062286000000000",
          "{\"thread_id\":\"conv_abc123\",\"message\":\"Availability checked for 2026-08-27\"}"
        ]
      ]
    }
  ]
}
```

---

## Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| **204** | No Content (success) | Logs accepted; continue |
| **400** | Bad Request | Malformed payload; do not retry (log error and discard) |
| **401** | Unauthorized | Invalid token; fail-fast (do not retry; operator must fix env vars) |
| **403** | Forbidden | Insufficient permissions; do not retry |
| **429** | Too Many Requests | Rate limited; retry with exponential backoff |
| **500, 502, 503, 504** | Server error | Retryable; retry with exponential backoff |
| **Other 5xx** | Server error | Retryable; retry with exponential backoff |

---

## Retry Strategy

**For 5xx / 429 errors**:

1. Retry immediately (attempt 1)
2. Wait 1 second (attempt 2)
3. Wait 2 seconds (attempt 3)
4. Wait 4 seconds (attempt 4)
5. After 4 attempts, drop batch and log warning

**For 4xx errors** (except 429):

- Do not retry; log error; discard batch

**Timeout**:

- HTTP request timeout: 30 seconds
- If timeout, treat as 5xx (retry)

---

## Payload Size Limits

- **Max payload size**: 10 MB per request (Grafana Cloud free tier limit)
- **Batching strategy**: If batch exceeds 10 MB, split and send multiple requests
- **Max logs per batch**: Recommended 100-1000 (depends on log size)

---

## Label Constraints

| Label | Format | Required | Max Length |
|-------|--------|----------|-----------|
| `tenant` | `"ID\|NAME"` | YES | 255 chars (ID ≤ 50, NAME ≤ 200) |
| `operation` | `[a-z_][a-z0-9_]*` | No | 255 chars |
| `method` | `module.function` | No | 255 chars |
| `line` | `^[0-9]{1,6}$` | No | 6 chars (0-999999) |
| `agent` | `[a-z_][a-z0-9_]*` | No | 100 chars |
| `level` | `ERROR\|WARN\|INFO\|DEBUG` | YES | 5 chars |

**Note**: Loki enforces a max of ~100 label keys per stream. Our design uses ~6 fixed labels, leaving room for future extensions.

---

## Implementation Notes

### Timestamp Generation

Loki expects nanosecond precision (13-digit epoch + 6-digit nanos = 19 total digits).

```python
import time
ns_since_epoch = int(time.time() * 1e9)  # Python's time.time() is float (seconds)
```

### JSON Payload String Escaping

The log entry is JSON-encoded **twice**:

1. First as a Python dict
2. Then as a JSON string (for Loki's `values` field)

```python
import json

log_entry = {
    "thread_id": "conv_abc123",
    "message": "Booking confirmed",
    "extra": {"booking_id": "bk_789"}
}

# JSON-encode the entry
json_string = json.dumps(log_entry)

# This becomes the value in the Loki payload:
loki_payload = {
    "streams": [
        {
            "stream": {...labels...},
            "values": [[timestamp_ns_str, json_string]]  # json_string goes here
        }
    ]
}

# Finally, POST the Loki payload as JSON
requests.post(url, json=loki_payload, ...)
```

### PII Redaction

Before transmission, the `log_entry` dict (before JSON encoding) must be sanitized:

```python
SENSITIVE_KEYS = {
    "password", "token", "secret", "api_key", "authorization", 
    "credential", "auth", "key", "pwd", "pass"
}

def redact_pii(obj: dict) -> dict:
    """Recursively redact sensitive fields."""
    redacted = {}
    for k, v in obj.items():
        if k.lower() in SENSITIVE_KEYS:
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_pii(v)
        else:
            redacted[k] = v
    return redacted

# Use before JSON encoding:
safe_entry = redact_pii(log_entry)
json_string = json.dumps(safe_entry)
```

---

## Example Request/Response

### Request

```bash
curl -X POST \
  https://acme-corp.grafana.net/loki/api/v1/push \
  -H "Authorization: Bearer glsa_xxxx...xxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "streams": [
      {
        "stream": {
          "tenant": "acme-corp|Acme Corporation",
          "level": "INFO"
        },
        "values": [
          ["1693062285123456000", "{\"message\":\"Test log\",\"thread_id\":\"conv_123\"}"]
        ]
      }
    ]
  }'
```

### Response (Success)

```http
HTTP/1.1 204 No Content
Content-Length: 0
```

### Response (Auth Error)

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "errors": ["Unauthorized"]
}
```

---

## Monitoring & Debugging

**In Grafana Explore**:

```logql
# View all logs for a tenant
{tenant="acme-corp*"}

# Filter by level
{tenant="acme-corp*", level="ERROR"}

# Search by operation
{operation="confirm_booking"}

# Count logs per method
{tenant="acme-corp*"} | json | stats count() by method

# Error logs with stack traces
{level="ERROR"} | json | extra_error_code!=""
```

**Troubleshooting**:

- **No logs appearing**: Check API token (401), endpoint URL (404), network connectivity
- **Partial logs**: Check payload size (10 MB limit); split batch if needed
- **Wrong tenant**: Verify `tenant` label format is `"ID|NAME"` (pipe-separated)
- **Duplicate logs**: Multiple sends of same timestamp + content are idempotent in Loki

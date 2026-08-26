# Quickstart: Grafana + Loki Observability

**Status**: Phase 1 complete — ready for Phase 2 (implementation)  
**Audience**: Developers implementing the feature + QA testing

---

## Prerequisites

1. **Grafana Cloud account** (free tier sufficient)
   - Sign up at https://grafana.com/products/cloud/
   - Create API key (generate in Grafana Cloud UI under Administration → API Keys)

2. **Environment variables** (add to `.env` or `.env.local`):
   ```bash
   GRAFANA_LOKI_URL=https://<YOUR_ORG>.grafana.net/loki/api/v1/push
   GRAFANA_LOKI_API_TOKEN=glsa_...your_token...
   ```

3. **Python dependencies** (already in project):
   - `requests` (for HTTP client)
   - Python's built-in `logging` and `queue` modules

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│ Agent Module (e.g., booking_agent)                              │
├─────────────────────────────────────────────────────────────────┤
│ logger = get_logger("tenant_id", "booking_agent")               │
│ logger.info("Booking started", method=..., line=..., ...)       │
└────────────────┬────────────────────────────────────────────────┘
                 │ (non-blocking queue.put)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LogService (Application Layer)                                  │
├─────────────────────────────────────────────────────────────────┤
│ queue.Queue() → in-process buffer                               │
│ Flush loop: every 2s or 100 entries                             │
└────────────────┬────────────────────────────────────────────────┘
                 │ (async background thread)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LokiLogSender (Infrastructure Adapter)                          │
├─────────────────────────────────────────────────────────────────┤
│ Redact PII → Format Loki payload → POST to Loki endpoint        │
│ Retry on 5xx (exponential backoff) / fail on 4xx                │
└────────────────┬────────────────────────────────────────────────┘
                 │ (HTTP POST via requests)
                 ▼
        Grafana Loki (SaaS)
        ↓
        Dashboard (query logs by tenant/operation/agent)
        ↓
        Alert Rules (fire on errors)
```

---

## Phase 2 Implementation Steps (Summary)

### Step 1: Create Clean Architecture Module

**Create directory structure**:
```
modules/observability/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── log_event.py           # LogEntry entity
│   └── ports/
│       ├── __init__.py
│       └── log_sender.py       # Abstract LogSender port
├── application/
│   ├── __init__.py
│   └── log_service.py          # LogService use case
├── infrastructure/
│   ├── __init__.py
│   ├── loki_client.py          # LokiLogSender adapter
│   └── log_sender_factory.py   # Port binding
├── interface/
│   ├── __init__.py
│   └── logger_factory.py       # Public API for agents
└── test_log_service.py         # Unit tests
```

### Step 2: Implement Domain Layer

**File: `modules/observability/domain/log_event.py`**

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass(frozen=True)
class LogEntry:
    """Immutable domain entity for a log event."""
    tenant_id: str
    tenant_name: str
    thread_id: str
    method: str
    line: int
    level: str  # ERROR, WARN, INFO, DEBUG
    message: str
    timestamp: datetime
    agent: Optional[str] = None
    extra: Optional[dict] = None
    
    def validate(self) -> None:
        """Validate all fields; raise ValueError if invalid."""
        # Check tenant_id format, line number range, level enum, etc.
        if not self.tenant_id or len(self.tenant_id) > 50:
            raise ValueError("Invalid tenant_id")
        if self.line < 0 or self.line > 999999:
            raise ValueError("Invalid line number")
        if self.level not in ("ERROR", "WARN", "INFO", "DEBUG"):
            raise ValueError(f"Invalid level: {self.level}")
        # ... more validation ...
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "thread_id": self.thread_id,
            "message": self.message,
            "extra": self.extra or {},
            "timestamp": self.timestamp.isoformat() + "Z"
        }
```

**File: `modules/observability/domain/ports/log_sender.py`**

```python
from abc import ABC, abstractmethod
from typing import List
from modules.observability.domain.log_event import LogEntry

class LogSender(ABC):
    """Port: abstract interface for sending logs to external systems."""
    
    @abstractmethod
    async def send_batch(self, entries: List[LogEntry]) -> bool:
        """Send a batch of logs. Return True if successful."""
        pass
```

### Step 3: Implement Application Layer

**File: `modules/observability/application/log_service.py`**

```python
import asyncio
from queue import Queue, Full
from typing import List, Optional
from modules.observability.domain.log_event import LogEntry
from modules.observability.domain.ports.log_sender import LogSender

class LogService:
    """Use case: queue and batch-send logs."""
    
    def __init__(self, sender: LogSender, batch_size: int = 100, flush_interval_sec: float = 2.0):
        self.sender = sender
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.queue: Queue = Queue(maxsize=10000)
        self._running = False
        self._task = None
    
    def start(self):
        """Start background flush loop."""
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())
    
    async def stop(self):
        """Stop background flush loop and drain queue."""
        self._running = False
        if self._task:
            await self._task
    
    def log(self, entry: LogEntry) -> None:
        """Queue a log entry (non-blocking)."""
        entry.validate()
        try:
            self.queue.put_nowait(entry)
        except Full:
            # Queue full; drop oldest or log warning (implementation choice)
            pass
    
    async def _flush_loop(self) -> None:
        """Background task: periodically flush queue to Loki."""
        while self._running:
            await asyncio.sleep(self.flush_interval_sec)
            batch = self._drain_queue()
            if batch:
                success = await self.sender.send_batch(batch)
                if not success:
                    # Log failure; retry on next cycle
                    pass
    
    def _drain_queue(self, max_size: Optional[int] = None) -> List[LogEntry]:
        """Drain up to max_size entries from queue."""
        max_size = max_size or self.batch_size
        batch = []
        while len(batch) < max_size and not self.queue.empty():
            try:
                batch.append(self.queue.get_nowait())
            except:
                break
        return batch
```

### Step 4: Implement Infrastructure Layer

**File: `modules/observability/infrastructure/loki_client.py`**

```python
import requests
import json
import os
from typing import List
from datetime import datetime
from modules.observability.domain.log_event import LogEntry
from modules.observability.domain.ports.log_sender import LogSender

class LokiLogSender(LogSender):
    """Adapter: send logs to Grafana Loki via HTTP."""
    
    SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "key", "pwd", "auth"}
    
    def __init__(self, url: str, api_token: str):
        self.url = url
        self.api_token = api_token
        self.session = requests.Session()
    
    async def send_batch(self, entries: List[LogEntry]) -> bool:
        """Send batch to Loki."""
        if not entries:
            return True
        
        # Redact PII
        safe_entries = [self._redact_entry(e) for e in entries]
        
        # Format Loki payload
        payload = self._format_payload(safe_entries)
        
        # Send with retries
        return await self._send_with_retry(payload)
    
    def _redact_entry(self, entry: LogEntry) -> dict:
        """Remove sensitive fields from entry."""
        data = entry.to_dict()
        if data.get("extra"):
            data["extra"] = self._redact_dict(data["extra"])
        return data
    
    def _redact_dict(self, obj: dict) -> dict:
        """Recursively redact sensitive keys."""
        result = {}
        for k, v in obj.items():
            if k.lower() in self.SENSITIVE_KEYS:
                result[k] = "[REDACTED]"
            elif isinstance(v, dict):
                result[k] = self._redact_dict(v)
            else:
                result[k] = v
        return result
    
    def _format_payload(self, entries: List[dict]) -> dict:
        """Convert entries to Loki push API format."""
        streams = []
        for entry_data in entries:
            # Group by labels
            labels = {
                "tenant": entry_data.get("tenant"),
                "level": entry_data.get("level")
            }
            timestamp_ns = int(entry_data["timestamp_ns"])
            log_line = json.dumps(entry_data)
            
            streams.append({
                "stream": labels,
                "values": [[str(timestamp_ns), log_line]]
            })
        
        return {"streams": streams}
    
    async def _send_with_retry(self, payload: dict, max_retries: int = 4) -> bool:
        """POST to Loki with exponential backoff."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        for attempt in range(max_retries):
            try:
                resp = self.session.post(self.url, json=payload, headers=headers, timeout=30)
                
                if resp.status_code == 204:
                    return True
                elif resp.status_code in (400, 401, 403):
                    # Non-retryable error
                    print(f"Loki error {resp.status_code}: {resp.text}")
                    return False
                elif resp.status_code >= 500 or resp.status_code == 429:
                    # Retryable error
                    if attempt < max_retries - 1:
                        wait_sec = 2 ** attempt
                        await asyncio.sleep(wait_sec)
                        continue
                    return False
                else:
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    print(f"Loki send failed: {e}")
                    return False
        
        return False


class NoOpLogSender(LogSender):
    """Stub: discards logs (used when Loki is disabled)."""
    
    async def send_batch(self, entries: List[LogEntry]) -> bool:
        return True
```

**File: `modules/observability/infrastructure/log_sender_factory.py`**

```python
import os
from modules.observability.infrastructure.loki_client import LokiLogSender, NoOpLogSender

def get_log_sender():
    """Factory: return real or no-op sender based on env config."""
    url = os.getenv("GRAFANA_LOKI_URL")
    token = os.getenv("GRAFANA_LOKI_API_TOKEN")
    
    if not url or not token:
        return NoOpLogSender()
    
    return LokiLogSender(url, token)
```

### Step 5: Implement Interface Layer

**File: `modules/observability/interface/logger_factory.py`**

```python
from datetime import datetime
from modules.observability.domain.log_event import LogEntry
from modules.observability.application.log_service import LogService
from modules.observability.infrastructure.log_sender_factory import get_log_sender

_log_service: LogService = None

def init_observability():
    """Initialize observability (call once on app startup)."""
    global _log_service
    sender = get_log_sender()
    _log_service = LogService(sender)
    _log_service.start()

def get_logger(tenant_id: str, tenant_name: str, agent: str = None):
    """Factory: return logger with tenant/agent context pre-populated."""
    if not _log_service:
        init_observability()
    
    return AgentLogger(_log_service, tenant_id, tenant_name, agent)

class AgentLogger:
    """Logger instance with tenant/agent context."""
    
    def __init__(self, service: LogService, tenant_id: str, tenant_name: str, agent: str = None):
        self.service = service
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.agent = agent
    
    def info(self, message: str, method: str, line: int, thread_id: str, extra: dict = None):
        self._log("INFO", message, method, line, thread_id, extra)
    
    def error(self, message: str, method: str, line: int, thread_id: str, extra: dict = None):
        self._log("ERROR", message, method, line, thread_id, extra)
    
    def _log(self, level: str, message: str, method: str, line: int, thread_id: str, extra: dict = None):
        entry = LogEntry(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            thread_id=thread_id,
            agent=self.agent,
            method=method,
            line=line,
            level=level,
            message=message,
            timestamp=datetime.utcnow(),
            extra=extra
        )
        self.service.log(entry)
```

### Step 6: Wire into FastAPI Startup

**File: `app/main.py`** (modify startup):

```python
from modules.observability.interface.logger_factory import init_observability

@app.on_event("startup")
async def startup():
    init_observability()
    # ... other startup logic ...
```

### Step 7: Write Tests

**File: `modules/observability/test_log_service.py`**:

- Unit tests for LogEntry validation
- Unit tests for PII redaction
- Unit tests for LogService queueing

**File: `tests/integration/test_observability_integration.py`**:

- Integration tests sending logs to mock Loki
- Multi-tenant isolation tests
- HTTP contract validation

### Step 8: Manual Testing in Grafana Cloud

1. Deploy app with GRAFANA_LOKI_URL and token set
2. Trigger agent operations (create booking, check calendar)
3. Log in to Grafana Cloud → Explore → select Loki data source
4. Query: `{tenant="acme-corp*"}` → should see logs
5. Create dashboard panel filtering by tenant/operation
6. Create alert rule for error logs

---

## Environment Variables Summary

Add to `.env` or deploy config:

```bash
# Required to enable observability; omit to disable
GRAFANA_LOKI_URL=https://<YOUR_ORG>.grafana.net/loki/api/v1/push
GRAFANA_LOKI_API_TOKEN=glsa_...your_api_key...
```

To find your endpoint and token:

1. Log in to Grafana Cloud (https://grafana.com/auth/sign-in)
2. Click "Loki" → "Send logs"
3. Copy URL and API key from the provided examples

---

## Key Behaviors

| Scenario | Result |
|----------|--------|
| Loki unreachable | Retry with backoff; oldest logs drop if queue full (10k entries) |
| No env vars set | Logging disabled (no-op); no errors |
| Invalid log fields | ValueError raised at call time (fail fast) |
| App crash | In-memory queue lost; acceptable for operational data |
| Sensitive data in log | Redacted (password, token, secret, key, auth fields replaced with "[REDACTED]") |

---

## Testing Commands

```bash
# Unit tests
pytest modules/observability/test_log_service.py -v

# Integration tests
pytest tests/integration/test_observability_integration.py -v

# Run app with observability
GRAFANA_LOKI_URL=https://... GRAFANA_LOKI_API_TOKEN=glsa_... \
  python -m uvicorn app.main:app --reload
```

---

## Next: Phase 2 Implementation

Once you have this quickstart, move to Phase 2:

1. `/speckit-tasks` — Generate task breakdowns
2. `/speckit-implement` — Begin coding with structured tasks
3. Manual testing in Grafana Cloud
4. PR review + merge

**Ready to proceed?** Commit this plan and start Phase 2.

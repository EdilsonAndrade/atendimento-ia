"""Infrastructure adapter: Grafana Loki HTTP client."""

import asyncio
import json
import logging
from typing import List
import httpx

from modules.observability.domain.log_event import LogEntry
from modules.observability.domain.ports.log_sender import LogSender

logger = logging.getLogger(__name__)


class LokiLogSender(LogSender):
    """Adapter: send logs to Grafana Loki via HTTP push API."""

    # Fields to redact (PII protection)
    SENSITIVE_KEYS = {
        "password",
        "token",
        "secret",
        "api_key",
        "authorization",
        "credential",
        "auth",
        "key",
        "pwd",
        "pass",
    }

    def __init__(self, url: str, api_token: str, user_id: str):
        """Initialize Loki client.

        Args:
            url: Loki push API endpoint (e.g., https://org.grafana.net/loki/api/v1/push)
            api_token: Grafana Cloud API token
            user_id: Grafana Cloud Loki Instance/User ID (numeric). O push API do
                Loki hospedado no Grafana Cloud exige HTTP Basic Auth
                (user_id:api_token) — Bearer sozinho retorna 401.
        """
        self.url = url
        self.api_token = api_token
        self.user_id = user_id
        # httpx.AsyncClient (não requests): `_send_with_retry` roda dentro do
        # event loop do uvicorn — uma chamada HTTP síncrona travaria a API
        # inteira (todos os tenants) até o Loki responder, inclusive em cada
        # retry com backoff. Client fica aberto (reuso de conexão), fechado só
        # se este sender for descartado — não há esse ciclo de vida hoje.
        self.client = httpx.AsyncClient(timeout=30)

    async def send_batch(self, entries: List[LogEntry]) -> bool:
        """Send batch of logs to Loki with retries."""
        if not entries:
            return True

        try:
            # Redact PII from entries
            safe_entries = [self._redact_entry(e) for e in entries]

            # Format Loki payload
            payload = self._format_payload(safe_entries)

            # Send with retries
            return await self._send_with_retry(payload)

        except Exception as e:
            logger.error(f"Unexpected error sending logs to Loki: {e}", exc_info=True)
            return False

    def _redact_entry(self, entry: LogEntry) -> dict:
        """Remove sensitive fields from log entry."""
        data = entry.to_dict()

        # Redact extra dict if present
        if data.get("extra"):
            data["extra"] = self._redact_dict(data["extra"])

        return data

    def _redact_dict(self, obj: dict) -> dict:
        """Recursively redact sensitive keys in dict."""
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
        """Convert LogEntry dicts to Loki push API format."""
        streams = []

        for entry_data in entries:
            # Labels viram o índice do Loki (stream selector) — mantidos de baixa
            # cardinalidade de propósito. method/line/agent ficam só no corpo JSON
            # (consultáveis via `| json`), nunca como label: cada combinação
            # method+line é quase única por chamada de log, o que explodiria a
            # cardinalidade de streams no Loki se virasse label.
            labels = {
                "level": entry_data.get("level", "INFO"),
                "tenant": entry_data.get("tenant_id", "unknown"),
            }

            # Timestamp in nanoseconds since epoch
            timestamp_str = entry_data.get("timestamp", "")
            if timestamp_str:
                # Parse ISO format and convert to nanoseconds
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                    timestamp_ns = int(dt.timestamp() * 1e9)
                except Exception:
                    timestamp_ns = int(asyncio.get_event_loop().time() * 1e9)
            else:
                timestamp_ns = int(asyncio.get_event_loop().time() * 1e9)

            # Log line as JSON string
            log_line = json.dumps(entry_data)

            streams.append(
                {
                    "stream": labels,
                    "values": [[str(timestamp_ns), log_line]],
                }
            )

        return {"streams": streams}

    async def _send_with_retry(self, payload: dict, max_retries: int = 4) -> bool:
        """POST to Loki with exponential backoff retry logic."""
        headers = {"Content-Type": "application/json"}

        for attempt in range(max_retries):
            try:
                response = await self.client.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    auth=(self.user_id, self.api_token),
                )

                # Success
                if response.status_code == 204:
                    logger.debug(
                        f"Successfully sent {len(payload.get('streams', []))} log streams to Loki"
                    )
                    return True

                # Non-retryable error (4xx)
                elif 400 <= response.status_code < 500:
                    if response.status_code == 401:
                        logger.error(
                            "Loki authentication failed (401 Unauthorized) — check API token"
                        )
                    else:
                        logger.error(
                            f"Loki non-retryable error {response.status_code}: {response.text}"
                        )
                    return False

                # Retryable error (5xx or 429)
                elif response.status_code >= 500 or response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_sec = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8
                        logger.warning(
                            f"Loki error {response.status_code}, retrying in {wait_sec}s..."
                        )
                        await asyncio.sleep(wait_sec)
                        continue
                    else:
                        logger.error(
                            f"Loki error {response.status_code} after {max_retries} attempts"
                        )
                        return False

                else:
                    logger.error(f"Unexpected Loki response: {response.status_code}")
                    return False

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_sec = 2 ** attempt
                    logger.warning(f"Loki request timeout, retrying in {wait_sec}s...")
                    await asyncio.sleep(wait_sec)
                else:
                    logger.error("Loki request timed out after all retries")
                    return False

            except httpx.HTTPError as e:
                if attempt < max_retries - 1:
                    wait_sec = 2 ** attempt
                    logger.warning(f"Loki request failed: {e}, retrying in {wait_sec}s...")
                    await asyncio.sleep(wait_sec)
                else:
                    logger.error(f"Loki request failed after all retries: {e}")
                    return False

        return False


class NoOpLogSender(LogSender):
    """Stub sender: discards all logs (used when observability disabled)."""

    async def send_batch(self, entries: List[LogEntry]) -> bool:
        """Silently discard logs."""
        return True

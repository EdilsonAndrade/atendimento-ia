"""Entrypoint do worker de retry de `chat_token_usage` (EDI-63).

Rodar com: python -m workers.token_usage_retry_worker
"""
import asyncio
import logging
import threading

from app.core.observability import init_observability, start_observability_flush
from modules.token_usage.infrastructure.retry_worker import TokenUsageRetryWorker

logging.basicConfig(level=logging.INFO)


def _run_observability_flush_loop() -> None:
    """Roda a task de flush do LogService num event loop dedicado, numa thread
    separada. Este worker é síncrono (`run_forever()` é um `while True`
    bloqueante, sem asyncio) — sem um loop rodando de verdade em algum lugar,
    a task criada por `start_observability_flush()` fica presa a um loop morto
    e nunca envia nada ao Loki (mesmo bug corrigido em app/main.py)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_observability_flush()
    loop.run_forever()


if __name__ == "__main__":
    init_observability()
    threading.Thread(target=_run_observability_flush_loop, daemon=True).start()
    TokenUsageRetryWorker().run_forever()

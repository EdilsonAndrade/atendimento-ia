"""Entrypoint do worker de retry de `chat_token_usage` (EDI-63).

Rodar com: python -m workers.token_usage_retry_worker
"""
import logging

from modules.token_usage.infrastructure.retry_worker import TokenUsageRetryWorker

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    TokenUsageRetryWorker().run_forever()

"""Worker que drena a fila de retry de `chat_token_usage` (EDI-63).

Ao subir, reclama (XAUTOCLAIM) qualquer entrada pendente há tempo demais — inclusive
as que ficaram no PEL porque o worker anterior caiu no meio do processamento — antes
de esperar por entradas novas (XREADGROUP). Uma entrada só é confirmada (XACK) depois
de gravada com sucesso no Postgres; depois de `TOKEN_USAGE_RETRY_MAX_ATTEMPTS`
tentativas sem sucesso, vai para a stream de dead-letter em vez de ficar sendo
retentada para sempre (FR-018 do EDI-63).
"""
import logging
import os
import time

import redis

from modules.token_usage.domain.token_usage_record import TokenUsageRecord
from modules.token_usage.infrastructure.postgres_token_usage_repository import (
    PostgresTokenUsageRepository,
)
from modules.token_usage.infrastructure.redis_retry_queue import (
    CONSUMER_GROUP,
    DEAD_LETTER_STREAM_NAME,
    STREAM_NAME,
    fields_to_record,
    get_redis_client,
    record_to_fields,
)
from modules.observability.interface.logger_factory import get_logger

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = int(os.getenv("TOKEN_USAGE_RETRY_MAX_ATTEMPTS", "5"))
DEFAULT_MIN_IDLE_MS = int(os.getenv("TOKEN_USAGE_RETRY_MIN_IDLE_MS", "30000"))
DEFAULT_CONSUMER_NAME = os.getenv("TOKEN_USAGE_RETRY_CONSUMER_NAME", "token_usage_retry_worker")
DEFAULT_POLL_INTERVAL_SECONDS = float(os.getenv("TOKEN_USAGE_RETRY_POLL_INTERVAL_SECONDS", "2.0"))


class TokenUsageRetryWorker:
    def __init__(
        self,
        client: redis.Redis | None = None,
        repository: PostgresTokenUsageRepository | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        consumer_name: str = DEFAULT_CONSUMER_NAME,
        min_idle_ms: int = DEFAULT_MIN_IDLE_MS,
    ):
        self._client = client or get_redis_client()
        self._repository = repository or PostgresTokenUsageRepository()
        self._max_attempts = max_attempts
        self._consumer_name = consumer_name
        self._min_idle_ms = min_idle_ms
        self._ensure_group()

    def _ensure_group(self) -> None:
        try:
            self._client.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                get_logger(tenant_id="unknown", tenant_name="unknown", agent="token_usage_retry_worker").error(
                    message=f"Failed to ensure Redis consumer group: {exc}",
                    method="modules.token_usage.infrastructure.retry_worker._ensure_group",
                    line=56,
                    thread_id="system",
                    extra={"error": str(exc)},
                )
                raise

    def _process_message(self, message_id: str, fields: dict) -> None:
        try:
            record = fields_to_record(fields)
        except Exception as exc:
            # Dado corrompido/ilegível: não há como reprocessar — vai direto pra
            # dead-letter em vez de martelar para sempre num payload inválido.
            logger.error("Entrada ilegível na fila de retry (id=%s): %s", message_id, exc, exc_info=True)
            get_logger(tenant_id="unknown", tenant_name="unknown", agent="token_usage_retry_worker").error(
                message=f"Unparseable entry in token usage retry queue: {exc}",
                method="modules.token_usage.infrastructure.retry_worker._process_message",
                line=66,
                thread_id="system",
                extra={"error": str(exc), "message_id": message_id},
            )
            self._move_to_dead_letter_raw(message_id, fields)
            return

        try:
            self._repository.save(record)
            self._client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
        except Exception as exc:
            logger.error(
                "Falha ao reprocessar entrada da fila de retry (id=%s, tenant_id=%s): %s",
                message_id, record.tenant_id, exc, exc_info=True,
            )
            get_logger(tenant_id=record.tenant_id, tenant_name=record.tenant_id, agent="token_usage_retry_worker").error(
                message=f"Failed to reprocess token usage retry entry: {exc}",
                method="modules.token_usage.infrastructure.retry_worker._process_message",
                line=74,
                thread_id=record.thread_id,
                extra={"error": str(exc), "message_id": message_id},
            )
            self._maybe_dead_letter(message_id, record)

    def _delivery_count(self, message_id: str) -> int:
        pending = self._client.xpending_range(STREAM_NAME, CONSUMER_GROUP, message_id, message_id, 1)
        if not pending:
            return 0
        return pending[0]["times_delivered"]

    def _maybe_dead_letter(self, message_id: str, record: TokenUsageRecord) -> None:
        if self._delivery_count(message_id) < self._max_attempts:
            return  # ainda dentro do limite de tentativas — permanece no PEL para retry

        logger.critical(
            "TOKEN_USAGE_RETRY_DEAD_LETTER tenant_id=%s thread_id=%s message_id=%s — "
            "esgotadas %s tentativas, movendo para dead-letter.",
            record.tenant_id, record.thread_id, message_id, self._max_attempts,
        )
        fields = record_to_fields(record)
        fields["original_message_id"] = message_id
        fields["failed_attempts"] = str(self._max_attempts)
        self._client.xadd(DEAD_LETTER_STREAM_NAME, fields)
        self._client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)

    def _move_to_dead_letter_raw(self, message_id: str, fields: dict) -> None:
        dead_fields = {**fields, "original_message_id": message_id, "failed_attempts": "unparseable"}
        self._client.xadd(DEAD_LETTER_STREAM_NAME, dead_fields)
        self._client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)

    def _drain_backlog(self) -> None:
        """Reclama entradas paradas há mais de DEFAULT_MIN_IDLE_MS (inclusive de
        um worker anterior que caiu no meio do processamento) antes de ler
        entradas novas."""
        cursor = "0-0"
        while True:
            cursor, claimed, _deleted = self._client.xautoclaim(
                STREAM_NAME, CONSUMER_GROUP, self._consumer_name,
                min_idle_time=self._min_idle_ms, start_id=cursor, count=50,
            )
            for message_id, fields in claimed:
                self._process_message(message_id, fields)
            if cursor == "0-0":
                break

    def run_once(self) -> None:
        self._drain_backlog()

        response = self._client.xreadgroup(
            CONSUMER_GROUP, self._consumer_name, {STREAM_NAME: ">"}, count=50, block=1000,
        )
        for _stream_name, entries in response or []:
            for message_id, fields in entries:
                self._process_message(message_id, fields)

    def run_forever(self) -> None:
        logger.info("TokenUsageRetryWorker iniciado (consumer=%s).", self._consumer_name)
        while True:
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Erro no loop do TokenUsageRetryWorker: %s", exc, exc_info=True)
                get_logger(tenant_id="unknown", tenant_name="unknown", agent="token_usage_retry_worker").error(
                    message=f"TokenUsageRetryWorker loop error: {exc}",
                    method="modules.token_usage.infrastructure.retry_worker.run_forever",
                    line=137,
                    thread_id="system",
                    extra={"error": str(exc)},
                )
                time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)

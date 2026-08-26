"""Caso de uso: registrar o custo de uma chamada real ao LLM (EDI-60).

Único ponto onde a regra "uma falha aqui nunca pode afetar a resposta ao cliente"
(FR-006) vive — todo chamador (ex.: modules/ia/agent_graph.py) só precisa invocar
`execute(...)`, nunca lidar com exceção de persistência.
"""
import logging
import os
from decimal import Decimal
from typing import Any

from modules.token_usage.application.ports import RetryQueuePort, TokenUsageRepository
from modules.token_usage.domain.token_usage_record import TokenUsageRecord, calculate_cost_usd

logger = logging.getLogger(__name__)


class RecordTokenUsageUseCase:
    def __init__(
        self,
        repository: TokenUsageRepository,
        price_per_1k_input: Decimal | None = None,
        price_per_1k_output: Decimal | None = None,
        retry_queue: RetryQueuePort | None = None,
    ):
        self._repository = repository
        # EDI-63: quando o INSERT direto falhar, o registro vai para esta fila em
        # vez de só ser perdido — ver modules/token_usage/infrastructure/redis_retry_queue.py.
        self._retry_queue = retry_queue
        # Preço configurável via env var — não há tabela de preços oficial embutida
        # neste projeto (varia por provedor/plano); ver research.md §5.
        self._price_per_1k_input = price_per_1k_input if price_per_1k_input is not None else Decimal(
            os.getenv("LLM_PRICE_PER_1K_INPUT_TOKENS_USD", "0")
        )
        self._price_per_1k_output = price_per_1k_output if price_per_1k_output is not None else Decimal(
            os.getenv("LLM_PRICE_PER_1K_OUTPUT_TOKENS_USD", "0")
        )

    def execute(
        self,
        response: Any,
        tenant_id: str,
        base_thread_id: str | None,
        thread_id: str | None,
        node_type: str,
    ) -> None:
        try:
            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

            if not base_thread_id:
                # Sem conversa identificável não há o que agrupar (FR-002/US2) —
                # registrar mesmo assim seria um dado órfão inútil.
                return

            record = TokenUsageRecord(
                tenant_id=tenant_id,
                base_thread_id=base_thread_id,
                thread_id=thread_id,
                node_type=node_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=calculate_cost_usd(
                    input_tokens, output_tokens, self._price_per_1k_input, self._price_per_1k_output
                ),
            )
            try:
                self._repository.save(record)
            except Exception as exc:
                logger.error(
                    "Falha ao registrar uso de token (tenant_id=%s, base_thread_id=%s, node_type=%s): %s",
                    tenant_id,
                    base_thread_id,
                    node_type,
                    exc,
                    exc_info=True,
                )
                self._publish_to_retry_queue(record)
        except Exception as exc:
            logger.error(
                "Falha ao registrar uso de token (tenant_id=%s, base_thread_id=%s, node_type=%s): %s",
                tenant_id,
                base_thread_id,
                node_type,
                exc,
                exc_info=True,
            )

    def _publish_to_retry_queue(self, record: TokenUsageRecord) -> None:
        """Nunca lança — se até a publicação na fila de retry falhar, o registro
        é perdido (mesmo comportamento de antes do EDI-63), mas o request-path
        nunca é afetado (FR-006 do EDI-60)."""
        if self._retry_queue is None:
            return
        try:
            self._retry_queue.publish(record)
        except Exception as exc:
            logger.error(
                "Falha ao publicar registro de uso de token na fila de retry (tenant_id=%s): %s",
                record.tenant_id, exc, exc_info=True,
            )

"""Caso de uso: classificar outcome + gerar resumo/rascunho de follow-up de uma
sessão fechada, em uma única chamada ao LLM (EDI-53).

Reaproveita a mesma chamada de LLM que antes só gerava resumo/fatos em
`modules/ia/thread_session.py` (EDI-59/61) — ver research.md §1. Grava a entrada
em `follow_up_queue` de forma idempotente (FR-004) e devolve resumo/fatos para o
chamador legado ainda gravar `chat_thread_summaries` como já fazia.

Nunca lança (FR-010) — mesmo espírito de `RecordConversationTurnUseCase`/
`RecordTokenUsageUseCase`.
"""
import logging
from datetime import date

from modules.follow_up.application.ports import FollowUpQueueRepository, SessionOutcomeClassifierPort
from modules.follow_up.domain.follow_up_entry import FollowUpEntry, Outcome
from modules.observability.interface.logger_factory import get_logger

logger = logging.getLogger(__name__)

_VALID_OUTCOMES = {o.value for o in Outcome}


class ClassifySessionOutcomeUseCase:
    def __init__(self, repository: FollowUpQueueRepository, classifier: SessionOutcomeClassifierPort):
        self._repository = repository
        self._classifier = classifier

    def execute(
        self,
        tenant_id: str,
        base_thread_id: str,
        active_thread_id: str,
        conversation_text: str,
        oferta_vigente_texto: str | None = None,
        oferta_vigente_validade: date | None = None,
    ) -> dict | None:
        try:
            classificacao = self._classifier.classify(
                conversation_text, oferta_vigente_texto, oferta_vigente_validade
            )

            outcome_bruto = classificacao.get("outcome")
            if outcome_bruto not in _VALID_OUTCOMES:
                # Classificação fora do enum esperado — não é seguro gravar um
                # outcome inventado; loga e desiste desta sessão (FR-010).
                logger.error(
                    "Outcome inválido devolvido pelo classificador (tenant_id=%s, base_thread_id=%s): %r",
                    tenant_id, base_thread_id, outcome_bruto,
                )
                get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="follow_up_classifier").error(
                    message=f"Invalid outcome returned by classifier: {outcome_bruto!r}",
                    method="modules.follow_up.application.classify_session_outcome.execute",
                    line=46,
                    thread_id=active_thread_id,
                    extra={"error": "INVALID_OUTCOME"},
                )
                return None

            entry = FollowUpEntry(
                tenant_id=tenant_id,
                base_thread_id=base_thread_id,
                active_thread_id=active_thread_id,
                outcome=Outcome(outcome_bruto),
                summary=str(classificacao.get("resumo") or ""),
                draft_message=classificacao.get("draft_message") or None,
            )
            self._repository.save(entry)  # idempotente — False (duplicata) não é erro

            return {
                "resumo": entry.summary,
                "fatos": classificacao.get("fatos") or {},
            }
        except Exception as exc:
            logger.error(
                "Falha ao classificar outcome da sessão (tenant_id=%s, base_thread_id=%s, active_thread_id=%s): %s",
                tenant_id, base_thread_id, active_thread_id, exc, exc_info=True,
            )
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="follow_up_classifier").error(
                message=f"Session outcome classification failed: {exc}",
                method="modules.follow_up.application.classify_session_outcome.execute",
                line=66,
                thread_id=active_thread_id,
                extra={"error": str(exc)},
            )
            return None

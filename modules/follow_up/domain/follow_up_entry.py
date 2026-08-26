"""Entidade de Domínio: outcome + rascunho de follow-up de uma sessão fechada (EDI-53).

Framework-free (Princípio III).
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Outcome(str, Enum):
    FECHADO = "fechado"
    PENSANDO = "pensando"
    SEM_RESPOSTA = "sem_resposta"
    RECUSADO = "recusado"
    EM_ANDAMENTO = "em_andamento"


class Status(str, Enum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    ENVIADO = "enviado"
    DESCARTADO = "descartado"
    OPT_OUT = "opt_out"


# Outcomes para os quais um rascunho de follow-up faz sentido (FR-003).
DRAFT_ELIGIBLE_OUTCOMES = (Outcome.PENSANDO, Outcome.SEM_RESPOSTA)


@dataclass
class FollowUpEntry:
    tenant_id: str
    base_thread_id: str
    active_thread_id: str
    outcome: Outcome
    summary: str
    draft_message: str | None = None
    status: Status = Status.PENDENTE
    id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, Outcome):
            self.outcome = Outcome(self.outcome)
        if not isinstance(self.status, Status):
            self.status = Status(self.status)
        if self.draft_message and self.outcome not in DRAFT_ELIGIBLE_OUTCOMES:
            # Defensivo (FR-003): mesmo que o classificador erre, a entidade nunca
            # carrega um draft fora dos outcomes elegíveis.
            self.draft_message = None

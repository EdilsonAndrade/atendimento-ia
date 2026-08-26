"""Caso de uso: aprovar/descartar/marcar opt_out (ou editar o rascunho) de um
registro da fila de follow-up (EDI-53/EDI-65, pré-requisito da UI de aprovação).
"""
from modules.follow_up.application.ports import FollowUpQueueRepository
from modules.follow_up.domain.follow_up_entry import FollowUpEntry, Status


class FollowUpEntryNotFoundError(Exception):
    pass


class UpdateFollowUpEntryUseCase:
    def __init__(self, repository: FollowUpQueueRepository):
        self._repository = repository

    def execute(
        self,
        tenant_id: str,
        entry_id: int,
        status: str | None = None,
        draft_message: str | None = None,
        approved_by: str | None = None,
    ) -> FollowUpEntry:
        if status is not None:
            status = Status(status).value  # ValueError -> 422 na borda HTTP

        updated = self._repository.update(
            tenant_id,
            entry_id,
            status=status,
            draft_message=draft_message,
            approved_by=approved_by,
        )
        if updated is None:
            raise FollowUpEntryNotFoundError(
                f"Registro {entry_id} não encontrado para o tenant {tenant_id!r}."
            )
        return updated

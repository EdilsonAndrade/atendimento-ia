"""Caso de uso: consultar a fila de follow-up de um tenant, opcionalmente por
status (EDI-53, FR-009)."""
from modules.follow_up.application.ports import FollowUpQueueRepository
from modules.follow_up.domain.follow_up_entry import FollowUpEntry


class GetFollowUpQueueUseCase:
    def __init__(self, repository: FollowUpQueueRepository):
        self._repository = repository

    def execute(
        self, tenant_id: str, status: str | None = None, outcome: str | None = None
    ) -> list[FollowUpEntry]:
        return self._repository.list_by_tenant(tenant_id, status=status, outcome=outcome)

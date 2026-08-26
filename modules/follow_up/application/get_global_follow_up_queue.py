"""Caso de uso: consultar a fila de follow-up entre tenants, para o painel admin
(EDI-53/EDI-65). Sem `tenant_id`, lista de todos os tenants — uso restrito a admin,
nunca chamado no caminho do próprio tenant (Princípio I continua valendo nos
endpoints de tenant, este é só para a visão consolidada do painel)."""
from modules.follow_up.application.ports import FollowUpQueueRepository
from modules.follow_up.domain.follow_up_entry import FollowUpEntry


class GetGlobalFollowUpQueueUseCase:
    def __init__(self, repository: FollowUpQueueRepository):
        self._repository = repository

    def execute(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
    ) -> list[FollowUpEntry]:
        return self._repository.list_all(tenant_id=tenant_id, status=status, outcome=outcome)

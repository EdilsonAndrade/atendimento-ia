"""Leitura e aprovação da fila de follow-up gerada no fechamento de sessão
(EDI-53, FR-009; PATCH e endpoint global adicionados como pré-requisito do
painel admin do EDI-65).

Router simples o bastante para chamar o Use Case diretamente com um repositório
concreto, mesmo padrão de `app/api/v1/endpoints/conversation_history.py`.
"""
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.follow_up_queue import (
    VALID_OUTCOMES,
    VALID_STATUSES,
    FollowUpEntryItem,
    FollowUpQueueResponse,
    FollowUpQueueUpdateRequest,
    GlobalFollowUpQueueResponse,
)
from modules.follow_up.application.get_follow_up_queue import GetFollowUpQueueUseCase
from modules.follow_up.application.get_global_follow_up_queue import GetGlobalFollowUpQueueUseCase
from modules.follow_up.application.update_follow_up_entry import (
    FollowUpEntryNotFoundError,
    UpdateFollowUpEntryUseCase,
)
from modules.follow_up.domain.follow_up_entry import FollowUpEntry
from modules.follow_up.infrastructure.customer_name_lookup import get_customer_name
from modules.follow_up.infrastructure.postgres_follow_up_queue_repository import (
    PostgresFollowUpQueueRepository,
)
from modules.observability.interface.logger_factory import get_logger

router = APIRouter(prefix="/tenants/{tenant_id}/follow-up-queue", tags=["Follow-up Queue"])
global_router = APIRouter(prefix="/follow-up-queue", tags=["Follow-up Queue"])


def get_use_case() -> GetFollowUpQueueUseCase:
    return GetFollowUpQueueUseCase(PostgresFollowUpQueueRepository())


def get_global_use_case() -> GetGlobalFollowUpQueueUseCase:
    return GetGlobalFollowUpQueueUseCase(PostgresFollowUpQueueRepository())


def get_update_use_case() -> UpdateFollowUpEntryUseCase:
    return UpdateFollowUpEntryUseCase(PostgresFollowUpQueueRepository())


def get_customer_name_lookup() -> Callable[[str], str | None]:
    return get_customer_name


def _validate_status(status: str | None) -> None:
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status inválido: {status!r} (esperado um de {VALID_STATUSES})",
        )


def _validate_outcome(outcome: str | None) -> None:
    if outcome is not None and outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"outcome inválido: {outcome!r} (esperado um de {VALID_OUTCOMES})",
        )


def _entry_to_dict(entry: FollowUpEntry, customer_name_lookup: Callable[[str], str | None]) -> dict:
    return {
        "id": entry.id,
        "tenant_id": entry.tenant_id,
        "base_thread_id": entry.base_thread_id,
        "customer_name": customer_name_lookup(entry.base_thread_id),
        "outcome": entry.outcome.value,
        "summary": entry.summary,
        "draft_message": entry.draft_message,
        "status": entry.status.value,
        "created_at": entry.created_at,
    }


@router.get("", response_model=FollowUpQueueResponse)
def get_follow_up_queue(
    tenant_id: str,
    status: str | None = Query(None),
    outcome: str | None = Query(None),
    use_case: GetFollowUpQueueUseCase = Depends(get_use_case),
    customer_name_lookup: Callable[[str], str | None] = Depends(get_customer_name_lookup),
):
    if not tenant_id or not tenant_id.strip():
        raise HTTPException(status_code=400, detail="É obrigatório informar o tenant_id.")
    _validate_status(status)
    _validate_outcome(outcome)

    entries = use_case.execute(tenant_id, status=status, outcome=outcome)
    return FollowUpQueueResponse(
        tenant_id=tenant_id,
        entries=[_entry_to_dict(e, customer_name_lookup) for e in entries],
    )


@router.patch("/{entry_id}", response_model=FollowUpEntryItem)
def update_follow_up_entry(
    tenant_id: str,
    entry_id: int,
    body: FollowUpQueueUpdateRequest,
    use_case: UpdateFollowUpEntryUseCase = Depends(get_update_use_case),
    customer_name_lookup: Callable[[str], str | None] = Depends(get_customer_name_lookup),
):
    if not tenant_id or not tenant_id.strip():
        raise HTTPException(status_code=400, detail="É obrigatório informar o tenant_id.")
    if body.status is None and body.draft_message is None:
        raise HTTPException(
            status_code=422, detail="Informe ao menos 'status' ou 'draft_message'."
        )
    _validate_status(body.status)

    try:
        entry = use_case.execute(
            tenant_id,
            entry_id,
            status=body.status,
            draft_message=body.draft_message,
            approved_by=body.approved_by,
        )
    except FollowUpEntryNotFoundError as exc:
        get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="follow_up_queue_api").warn(
            message=f"Follow-up entry not found: {exc}",
            method="app.api.v1.endpoints.follow_up_queue.update_follow_up_entry",
            line=126,
            thread_id="system",
            extra={"entry_id": entry_id},
        )
        raise HTTPException(status_code=404, detail=str(exc))

    return _entry_to_dict(entry, customer_name_lookup)


@global_router.get("", response_model=GlobalFollowUpQueueResponse)
def get_global_follow_up_queue(
    tenant_id: str | None = Query(None, description="Filtra por tenant; omitido, lista de todos."),
    status: str | None = Query(None),
    outcome: str | None = Query(None),
    use_case: GetGlobalFollowUpQueueUseCase = Depends(get_global_use_case),
    customer_name_lookup: Callable[[str], str | None] = Depends(get_customer_name_lookup),
):
    """Visão consolidada entre tenants para o painel admin (EDI-65). Sem
    restrição de acesso própria — mesma ausência de auth já aceita pelos outros
    endpoints desta feature (ver plan.md, Princípio IV); restringir a admin é
    responsabilidade da camada que consome este endpoint."""
    _validate_status(status)
    _validate_outcome(outcome)

    entries = use_case.execute(tenant_id=tenant_id, status=status, outcome=outcome)
    return GlobalFollowUpQueueResponse(
        entries=[_entry_to_dict(e, customer_name_lookup) for e in entries],
    )

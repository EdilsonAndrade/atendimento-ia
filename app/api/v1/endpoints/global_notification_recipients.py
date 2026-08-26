"""CRUD de e-mails internos da InterasisAI que recebem TODOS os alertas de
bloqueio (100%) de qualquer tenant (EDI-63).

Router simples o bastante (sem regra de negócio além de unicidade de e-mail)
para chamar `PostgresGlobalRecipients` diretamente, mesmo padrão de camadas já
aceito para CRUD administrativo simples no restante do projeto — a lógica de
negócio real (fallback e uso nas notificações) vive em
`modules/tenant_limits/application/notify_usage_milestones.py`.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.schemas.global_notification_recipient import (
    GlobalRecipientCreate,
    GlobalRecipientDeleteResponse,
    GlobalRecipientResponse,
    GlobalRecipientUpdate,
)
from app.schemas.prompt_manager import error_detail
from modules.tenant_limits.infrastructure.postgres_global_recipients import PostgresGlobalRecipients

router = APIRouter(prefix="/global-notification-recipients", tags=["Global Notification Recipients"])


def get_repository() -> PostgresGlobalRecipients:
    return PostgresGlobalRecipients()


@router.get("/", response_model=list[GlobalRecipientResponse])
def list_recipients(repository: PostgresGlobalRecipients = Depends(get_repository)):
    return repository.list_all()


@router.post("/", response_model=GlobalRecipientResponse, status_code=201)
def create_recipient(
    payload: GlobalRecipientCreate, repository: PostgresGlobalRecipients = Depends(get_repository)
):
    if repository.email_exists(payload.email):
        raise HTTPException(
            status_code=409,
            detail=error_detail("EMAIL_ALREADY_EXISTS", f"O e-mail {payload.email!r} já está cadastrado."),
        )
    return repository.create(payload.email)


@router.put("/{recipient_id}", response_model=GlobalRecipientResponse)
def update_recipient(
    recipient_id: int,
    payload: GlobalRecipientUpdate,
    repository: PostgresGlobalRecipients = Depends(get_repository),
):
    updated = repository.update(recipient_id, payload.active)
    if updated is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return updated


@router.delete("/{recipient_id}", response_model=GlobalRecipientDeleteResponse)
def delete_recipient(recipient_id: int, repository: PostgresGlobalRecipients = Depends(get_repository)):
    deleted_id = repository.delete(recipient_id)
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return {"id": deleted_id, "message": "Recipient deleted successfully"}

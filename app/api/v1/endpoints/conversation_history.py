"""Leitura do histórico consultável de conversa (EDI-53, FR-008).

Router simples o bastante para chamar o Use Case diretamente com um repositório
concreto, mesmo padrão de camadas já aceito para endpoints de leitura no restante
do projeto (ex.: GET /tenants/{id}/usage).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.conversation_history import ConversationHistoryResponse
from modules.conversation_history.application.get_conversation_history import (
    GetConversationHistoryUseCase,
)
from modules.conversation_history.infrastructure.postgres_conversation_message_repository import (
    PostgresConversationMessageRepository,
)

router = APIRouter(prefix="/tenants/{tenant_id}/conversation-history", tags=["Conversation History"])


def get_use_case() -> GetConversationHistoryUseCase:
    return GetConversationHistoryUseCase(PostgresConversationMessageRepository())


@router.get("/{base_thread_id}", response_model=ConversationHistoryResponse)
def get_conversation_history(
    tenant_id: str,
    base_thread_id: str,
    limit: int = Query(200, le=500, gt=0),
    before: datetime | None = None,
    use_case: GetConversationHistoryUseCase = Depends(get_use_case),
):
    if not tenant_id or not tenant_id.strip():
        raise HTTPException(status_code=400, detail="É obrigatório informar o tenant_id.")

    messages = use_case.execute(tenant_id, base_thread_id, limit=limit, before=before)
    return ConversationHistoryResponse(
        tenant_id=tenant_id,
        base_thread_id=base_thread_id,
        messages=[
            {"role": m.role, "content": m.content, "created_at": m.created_at} for m in messages
        ],
    )

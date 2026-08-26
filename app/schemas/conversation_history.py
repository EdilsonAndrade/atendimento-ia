from datetime import datetime

from pydantic import BaseModel, Field


class ConversationMessageItem(BaseModel):
    role: str = Field(..., description="'human' (cliente) ou 'ai' (atendente).")
    content: str = Field(..., description="Texto da mensagem.")
    created_at: datetime = Field(..., description="Data/hora em que a mensagem foi registrada.")


class ConversationHistoryResponse(BaseModel):
    tenant_id: str = Field(..., description="ID do tenant consultado.")
    base_thread_id: str = Field(..., description="Thread lógica do cliente consultada.")
    messages: list[ConversationMessageItem] = Field(
        default_factory=list, description="Mensagens em ordem cronológica ascendente."
    )

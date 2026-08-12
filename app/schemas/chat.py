# app/schemas/chat.py
from typing import Optional
from pydantic import BaseModel, Field

class MessageRequest(BaseModel):
    message: str = Field(
        ...,
        examples=["Qual o horário disponível para corte hoje?"], 
        description="Mensagem ou pergunta textual enviada pelo usuário final."
    )
    tenant_id: Optional[str] = Field(
        None,
        examples=["site-tenant-123", "cliente-abc"],
        description="Identificador do tenant quando a origem é uma plataforma externa, como o site."
    )
    thread_id: Optional[str] = Field(
        "default_session", 
        examples=["5511999998888"], 
        description="Identificador único da sessão/conversa (ex: WhatsApp do cliente)."
    )

class ChatResponse(BaseModel):
    tenant_id: str = Field(..., description="O ID do cliente que processou a requisição.")
    status: str = Field(..., description="Status da execução do motor")
    response: str = Field(..., description="Resposta limpa gerada pelo Grafo de Estados")
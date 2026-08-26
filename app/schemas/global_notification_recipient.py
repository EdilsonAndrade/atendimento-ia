from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class GlobalRecipientCreate(BaseModel):
    email: EmailStr = Field(..., description="E-mail interno da InterasisAI a receber alertas de bloqueio (100%).")


class GlobalRecipientUpdate(BaseModel):
    active: bool = Field(..., description="FALSE desativa o recebimento de alertas sem apagar o cadastro.")


class GlobalRecipientResponse(BaseModel):
    id: int = Field(..., description="ID do destinatário.")
    email: str = Field(..., description="E-mail cadastrado.")
    active: bool = Field(..., description="Se TRUE, recebe os alertas de 100% de qualquer tenant.")
    created_at: datetime = Field(..., description="Data e hora do cadastro.")


class GlobalRecipientDeleteResponse(BaseModel):
    id: int = Field(..., description="ID do destinatário excluído.")
    message: str = Field(..., description="Mensagem de confirmação da exclusão.")

from pydantic import BaseModel, Field
from datetime import datetime
class TenantRequest(BaseModel):
    tenant_id: str = Field(..., description="O ID do cliente que solicita a criação do tenant.")
    tenant_name: str = Field(..., description="O nome do cliente que solicita a criação do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    active: bool = Field(..., description="Indica se o tenant está ativo ou inativo.")
    created_at: datetime = Field(..., description="Data e hora de criação do tenant no formato ISO 8601.")
    updated_at: datetime | None = Field(None, description="Data e hora da última atualização do tenant no formato ISO 8601.")
    deleted_at: datetime | None = Field(None, description="Data e hora da exclusão do tenant no formato ISO 8601, se aplicável.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")

class TenantCreate(BaseModel):
    tenant_id: str = Field(..., description="O ID do cliente que solicita a criação do tenant.")
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")
    
class TenantUpdate(BaseModel):
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")

class TenantResponse(BaseModel):
    id: str = Field(..., description="O ID do tenant.")
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    created_at: datetime = Field(..., description="Data e hora de criação do tenant no formato ISO 8601.")
    updated_at: datetime | None = Field(None, description="Data e hora da última atualização do tenant no formato ISO 8601.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")
    deleted_at: datetime | None = Field(None, description="Data e hora da exclusão do tenant no formato ISO 8601, se aplicável.")


class DeleteResponse(BaseModel):
    id: str = Field(..., description="O ID do tenant excluído.")
    message: str = Field(..., description="Mensagem de confirmação da exclusão.")


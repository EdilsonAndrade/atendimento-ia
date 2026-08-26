from datetime import datetime

from pydantic import BaseModel, Field

VALID_STATUSES = ("pendente", "aprovado", "enviado", "descartado", "opt_out")
VALID_OUTCOMES = ("fechado", "pensando", "sem_resposta", "recusado", "em_andamento")


class FollowUpEntryItem(BaseModel):
    id: int = Field(..., description="ID do registro na fila.")
    tenant_id: str = Field(..., description="ID do tenant dono do registro.")
    base_thread_id: str = Field(..., description="Thread lógica do cliente.")
    customer_name: str | None = Field(
        None, description="Nome do cliente, quando já extraído do perfil (fatos_estruturados). Melhor esforço."
    )
    outcome: str = Field(..., description="fechado | pensando | sem_resposta | recusado | em_andamento.")
    summary: str = Field(..., description="Resumo da sessão.")
    draft_message: str | None = Field(None, description="Rascunho de follow-up (só para pensando/sem_resposta).")
    status: str = Field(..., description="pendente | aprovado | enviado | descartado | opt_out.")
    created_at: datetime = Field(..., description="Data/hora em que a sessão foi classificada.")


class FollowUpQueueResponse(BaseModel):
    tenant_id: str = Field(..., description="ID do tenant consultado.")
    entries: list[FollowUpEntryItem] = Field(default_factory=list, description="Registros da fila.")


class GlobalFollowUpQueueResponse(BaseModel):
    entries: list[FollowUpEntryItem] = Field(
        default_factory=list, description="Registros da fila entre tenants (painel admin, EDI-65)."
    )


class FollowUpQueueUpdateRequest(BaseModel):
    status: str | None = Field(
        None, description="Novo status: pendente | aprovado | enviado | descartado | opt_out."
    )
    draft_message: str | None = Field(
        None, description="Novo texto do rascunho (edição antes de aprovar)."
    )
    approved_by: str | None = Field(
        None, description="Identificação de quem aprovou/alterou (e-mail ou nome do admin)."
    )

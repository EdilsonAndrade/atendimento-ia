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
    # Obrigatório desde o EDI-43: um tenant sem prompt vinculado é erro de
    # configuração, e absorvê-lo em silêncio fazia o cliente receber o texto
    # genérico do projeto. Só o node_type 'operational' entra aqui — institutional
    # e chitchat resolvem pelas cadeias próprias.
    prompt_id: str = Field(
        ...,
        min_length=1,
        description="ID do prompt (node_type='operational') a ser vinculado ao tenant na criação.",
    )
    # Decide se o agente recebe tools de agendamento (agendar/consultar/cancelar)
    # para este tenant. Antes, isso era um efeito colateral de ter (ou não)
    # google_calendar_id preenchido: sem calendário, o tenant ainda assim recebia
    # as tools internas (static_tools), mesmo tendo um prompt puramente
    # institucional. Default TRUE para não quebrar o fluxo de cadastro atual —
    # tenants sem negócio de agendamento (ex: institucional puro) devem desmarcar.
    scheduling_enabled: bool = Field(
        True,
        description="Se TRUE, o agente oferece tools de agendamento (agendar/consultar/cancelar) a este tenant.",
    )

class TenantUpdate(BaseModel):
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")
    scheduling_enabled: bool = Field(
        True,
        description="Se TRUE, o agente oferece tools de agendamento (agendar/consultar/cancelar) a este tenant.",
    )

class TenantResponse(BaseModel):
    id: str = Field(..., description="O ID do tenant.")
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    created_at: datetime = Field(..., description="Data e hora de criação do tenant no formato ISO 8601.")
    updated_at: datetime | None = Field(None, description="Data e hora da última atualização do tenant no formato ISO 8601.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")
    deleted_at: datetime | None = Field(None, description="Data e hora da exclusão do tenant no formato ISO 8601, se aplicável.")
    scheduling_enabled: bool = Field(..., description="Se TRUE, o agente oferece tools de agendamento a este tenant.")


class DeleteResponse(BaseModel):
    id: str = Field(..., description="O ID do tenant excluído.")
    message: str = Field(..., description="Mensagem de confirmação da exclusão.")


# --- PRÉ-VISUALIZAÇÃO DE IMPACTO DA EXCLUSÃO (EDI-45) -----------------------
# Mesma classificação usada de fato por `DELETE /tenants/{id}` — nunca deve
# divergir do resultado real de uma exclusão (ver data-model.md / SC-002).

class PromptImpactItem(BaseModel):
    id: str = Field(..., description="ID do prompt.")
    titulo: str = Field(..., description="Título do prompt.")
    node_type: str = Field(..., description="node_type do prompt (operational/institutional/chitchat).")


class GuardrailImpactItem(BaseModel):
    id: str = Field(..., description="ID do guardrail.")
    titulo: str = Field(..., description="Título do guardrail.")
    is_global: bool = Field(..., description="Se o guardrail é aplicado globalmente a todos os tenants.")


class TenantListItemResponse(TenantResponse):
    prompts: list[PromptImpactItem] = Field(
        default_factory=list, description="Prompts com vínculo ativo a este tenant."
    )
    guardrails: list[GuardrailImpactItem] = Field(
        default_factory=list, description="Guardrails vinculados aos prompts ativos deste tenant."
    )


class TenantListResponse(BaseModel):
    items: list[TenantListItemResponse] = Field(..., description="Página de tenants.")
    total: int = Field(..., description="Total de tenants que casam com o filtro, ignorando paginação.")


class TenantDeleteImpactResponse(BaseModel):
    tenant_id: str = Field(..., description="ID do tenant consultado.")
    prompts_to_delete: list[PromptImpactItem] = Field(
        default_factory=list, description="Prompts que serão excluídos de fato (exclusivos deste tenant)."
    )
    prompts_to_unlink_only: list[PromptImpactItem] = Field(
        default_factory=list, description="Prompts que serão preservados; só o vínculo com este tenant desaparece."
    )
    guardrails_to_delete: list[GuardrailImpactItem] = Field(
        default_factory=list, description="Guardrails que serão excluídos de fato (exclusivos, não globais)."
    )
    guardrails_to_unlink_only: list[GuardrailImpactItem] = Field(
        default_factory=list, description="Guardrails preservados (globais ou usados por outro prompt)."
    )


from pydantic import BaseModel, EmailStr, Field
from datetime import date, datetime
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
    # EDI-63: teto agregado de chamadas de LLM/mês do tenant. NULL = sem limite
    # (comportamento atual preservado). Contagem por chamada de LLM, não por
    # mensagem real do cliente final — ver specs/010-tenant-message-limit/spec.md.
    monthly_message_limit: int | None = Field(
        None, description="Teto mensal de chamadas de LLM do tenant. NULL = sem limite."
    )
    notification_emails: list[EmailStr] = Field(
        default_factory=list,
        description="E-mails do tenant que recebem os avisos de 50/80/100%/reset do limite mensal.",
    )
    # EDI-53: oferta comercial vigente do tenant — única fonte permitida para o
    # rascunho de follow-up citar desconto/condição comercial (guardrail
    # anti-alucinação). Vigente só quando os dois campos estão preenchidos E
    # oferta_vigente_validade >= hoje.
    oferta_vigente_texto: str | None = Field(
        None, description="Texto livre da oferta/condição comercial vigente do tenant."
    )
    oferta_vigente_validade: date | None = Field(
        None, description="Data até quando a oferta vale. NULL = sem oferta vigente."
    )
    retention_days: int | None = Field(
        None, description="Dias de retenção de conversation_messages. NULL = sem expurgo automático."
    )

class TenantUpdate(BaseModel):
    name: str = Field(..., description="O nome do tenant.")
    google_calendar_id: str = Field(..., description="O ID do calendário do Google associado ao tenant.")
    allowed_domains: list[str] = Field(..., description="Lista de domínios autorizados para o tenant.")
    scheduling_enabled: bool = Field(
        True,
        description="Se TRUE, o agente oferece tools de agendamento (agendar/consultar/cancelar) a este tenant.",
    )
    monthly_message_limit: int | None = Field(
        None, description="Teto mensal de chamadas de LLM do tenant. NULL = sem limite."
    )
    notification_emails: list[EmailStr] = Field(
        default_factory=list,
        description="E-mails do tenant que recebem os avisos de 50/80/100%/reset do limite mensal.",
    )
    oferta_vigente_texto: str | None = Field(
        None, description="Texto livre da oferta/condição comercial vigente do tenant."
    )
    oferta_vigente_validade: date | None = Field(
        None, description="Data até quando a oferta vale. NULL = sem oferta vigente."
    )
    retention_days: int | None = Field(
        None, description="Dias de retenção de conversation_messages. NULL = sem expurgo automático."
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
    monthly_message_limit: int | None = Field(None, description="Teto mensal de chamadas de LLM do tenant. NULL = sem limite.")
    notification_emails: list[str] = Field(
        default_factory=list,
        description="E-mails do tenant que recebem os avisos de 50/80/100%/reset do limite mensal.",
    )
    oferta_vigente_texto: str | None = Field(
        None, description="Texto livre da oferta/condição comercial vigente do tenant."
    )
    oferta_vigente_validade: date | None = Field(
        None, description="Data até quando a oferta vale. NULL = sem oferta vigente."
    )
    retention_days: int | None = Field(
        None, description="Dias de retenção de conversation_messages. NULL = sem expurgo automático."
    )


class TenantUsageResponse(BaseModel):
    tenant_id: str = Field(..., description="ID do tenant consultado.")
    monthly_message_limit: int | None = Field(None, description="Teto mensal configurado, NULL se sem limite.")
    current_month_calls: int = Field(..., description="Chamadas de LLM contabilizadas no mês corrente.")
    percentage_used: float | None = Field(None, description="Percentual do limite consumido; NULL se sem limite.")
    blocked: bool = Field(..., description="Se TRUE, o tenant está bloqueado neste momento.")


class TenantMessageLimitConfigResponse(BaseModel):
    worst_case_calls_per_message: int = Field(
        ..., description="Chamadas de LLM no pior caso (todos os nós acionados) para 1 mensagem real."
    )
    average_calls_per_message: float = Field(
        ..., description="Chamadas de LLM médias estimadas para 1 mensagem real."
    )


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


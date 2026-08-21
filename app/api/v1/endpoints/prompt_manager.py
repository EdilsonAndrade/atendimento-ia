from typing import Optional

from fastapi import APIRouter, HTTPException

# Importa o método de conexão direto do seu módulo de banco
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import (
    DefaultPromptNotConfiguredError,
    PromptManagerService,
)
from modules.tenant.tenant_service import TenantService
from app.schemas.prompt_manager import (
    GuardrailCreateSchema,
    NodeType,
    PromptCreateSchema,
    TenantPromptLinkSchema,
    TenantPromptOverviewResponse,
)
router = APIRouter(prefix="/prompt-manager", tags=["Prompt Manager"])



# --- ENDPOINTS ---
@router.get("/guardrails")
def get_guardrails():
    service = PromptManagerService(get_db_connection)
    return service.list_guardrails()

@router.post("/guardrails")
def create_guardrail(payload: GuardrailCreateSchema):
    service = PromptManagerService(get_db_connection)
    return service.create_guardrail(payload.titulo, payload.conteudo, payload.is_global)

@router.get(
    "/prompts",
    summary="Lista prompts, opcionalmente filtrados por node_type (operational, institutional ou chitchat)",
)
def get_prompts(node_type: Optional[NodeType] = None):
    service = PromptManagerService(get_db_connection)
    return service.list_prompts(node_type=node_type)

@router.post(
    "/prompts",
    summary="Cria um prompt para um node_type (padrão: operational)",
)
def create_prompt(payload: PromptCreateSchema):
    service = PromptManagerService(get_db_connection)
    return service.create_prompt_with_relations(
        payload.titulo, payload.conteudo, payload.is_default, payload.guardrail_ids,
        node_type=payload.node_type,
    )

@router.post(
    "/link-tenant",
    summary="Vincula um tenant a um prompt; o node_type do vínculo é o do prompt informado e não afeta "
    "vínculos ativos de outros node_type do mesmo tenant",
)
def link_tenant(payload: TenantPromptLinkSchema):
    service = PromptManagerService(get_db_connection)
    return service.link_tenant_to_prompt(
        payload.tenant_id, payload.prompt_id, payload.custom_content_override
    )

@router.put(
    "/prompts/{prompt_id}",
    summary="Atualiza um prompt (substitui o estado completo, incluindo node_type)",
)
def update_prompt(prompt_id: str, payload: PromptCreateSchema):
    service = PromptManagerService(get_db_connection)
    updated_prompt = service.update_prompt_with_relations(
        prompt_id, payload.titulo, payload.conteudo, payload.is_default, payload.guardrail_ids,
        node_type=payload.node_type,
    )
    if not updated_prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    return updated_prompt

@router.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str):
    service = PromptManagerService(get_db_connection)
    deleted = service.delete_prompt(prompt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")


@router.put("/guardrails/{guardrail_id}")
def update_guardrail(guardrail_id: str, payload: GuardrailCreateSchema):
    service = PromptManagerService(get_db_connection)
    updated_guardrail = service.repository.update_guardrail(
        guardrail_id, payload.titulo, payload.conteudo, payload.is_global
    )
    if not updated_guardrail:
        raise HTTPException(status_code=404, detail="Guardrail não encontrado")
    return updated_guardrail

@router.delete("/guardrails/{guardrail_id}", status_code=204)
def delete_guardrail(guardrail_id: str):
    service = PromptManagerService(get_db_connection)
    deleted = service.delete_guardrail(guardrail_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Guardrail não encontrado")

@router.get(
    "/tenant/{tenant_id}",
    response_model=TenantPromptOverviewResponse,
    summary="Prompt e guardrails vinculados a um tenant, para um node_type (com fallback em cascata)",
)
def get_tenant_prompt_details(tenant_id: str, node_type: NodeType = "operational"):
    tenant_service = TenantService()
    if tenant_service.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    service = PromptManagerService(get_db_connection)
    try:
        return service.get_tenant_prompt_details(tenant_id, node_type=node_type)
    except DefaultPromptNotConfiguredError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
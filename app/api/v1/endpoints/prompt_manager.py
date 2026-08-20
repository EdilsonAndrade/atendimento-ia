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

@router.get("/prompts")
def get_prompts():
    service = PromptManagerService(get_db_connection)
    return service.list_prompts()

@router.post("/prompts")
def create_prompt(payload: PromptCreateSchema):
    service = PromptManagerService(get_db_connection)
    return service.create_prompt_with_relations(
        payload.titulo, payload.conteudo, payload.is_default, payload.guardrail_ids
    )

@router.post("/link-tenant")
def link_tenant(payload: TenantPromptLinkSchema):
    service = PromptManagerService(get_db_connection)
    return service.link_tenant_to_prompt(
        payload.tenant_id, payload.prompt_id, payload.custom_content_override
    )
    
@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: str, payload: PromptCreateSchema):
    service = PromptManagerService(get_db_connection)
    updated_prompt = service.update_prompt_with_relations(
        prompt_id, payload.titulo, payload.conteudo, payload.is_default, payload.guardrail_ids
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

@router.get(
    "/tenant/{tenant_id}",
    response_model=TenantPromptOverviewResponse,
    summary="Prompt e guardrails vinculados a um tenant (com fallback para o prompt padrão)",
)
def get_tenant_prompt_details(tenant_id: str):
    tenant_service = TenantService()
    if tenant_service.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    service = PromptManagerService(get_db_connection)
    try:
        return service.get_tenant_prompt_details(tenant_id)
    except DefaultPromptNotConfiguredError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
from fastapi import APIRouter, HTTPException

# Importa o método de conexão direto do seu módulo de banco
from infrastructure.connection import get_db_connection 
from modules.prompt_manager.prompt_manager_service import PromptManagerService
from app.schemas.prompt_manager import GuardrailCreateSchema, PromptCreateSchema, TenantPromptLinkSchema
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

@router.put("/guardrails/{guardrail_id}")
def update_guardrail(guardrail_id: str, payload: GuardrailCreateSchema):
    service = PromptManagerService(get_db_connection)
    updated_guardrail = service.repository.update_guardrail(
        guardrail_id, payload.titulo, payload.conteudo, payload.is_global
    )
    if not updated_guardrail:
        raise HTTPException(status_code=404, detail="Guardrail não encontrado")
    return updated_guardrail

@router.get("/tenant/{tenant_id}")
def get_tenant_prompt_details(tenant_id: str):
    service = PromptManagerService(get_db_connection)
    details = service.get_tenant_prompt_details(tenant_id)
    if not details:
        raise HTTPException(
            status_code=404, 
            detail=f"Nenhum prompt personalizado ou vínculo ativo encontrado para o tenant '{tenant_id}'."
        )
    return details
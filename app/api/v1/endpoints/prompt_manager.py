from typing import Optional

from fastapi import APIRouter, HTTPException

# Importa o método de conexão direto do seu módulo de banco
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import (
    DefaultPromptNotConfiguredError,
    PromptManagerService,
    PromptNotFoundError,
    ResourceInUseError,
    TenantsNotFoundError,
)
from modules.tenant.tenant_service import TenantService
from app.schemas.prompt_manager import (
    BulkTenantPromptLinkResponse,
    BulkTenantPromptLinkSchema,
    GuardrailCreateSchema,
    NodeType,
    PromptCreateSchema,
    PromptTenantsResponse,
    TenantPromptLinkSchema,
    TenantPromptOverviewResponse,
    error_detail,
)
from modules.observability.interface.logger_factory import get_logger
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
    try:
        deleted = service.delete_prompt(prompt_id)
    except ResourceInUseError as exc:
        # 409: o prompt está vinculado a tenants ativos. Devolve os bloqueadores
        # para a UI listar quem precisa ser realocado antes.
        get_logger(tenant_id="system", tenant_name="system", agent="prompt_manager_api").warn(
            message=f"Prompt deletion blocked: {exc}",
            method="app.api.v1.endpoints.prompt_manager.delete_prompt",
            line=91,
            thread_id="system",
            extra={"error": exc.code, "prompt_id": prompt_id},
        )
        raise HTTPException(
            status_code=409,
            detail=error_detail(exc.code, str(exc), exc.blockers),
        )
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
    try:
        deleted = service.delete_guardrail(guardrail_id)
    except ResourceInUseError as exc:
        # 409 com dois códigos distintos: GUARDRAIL_IS_GLOBAL (desmarcar global
        # primeiro) e GUARDRAIL_IN_USE_BY_TENANTS (desassociar dos prompts). A
        # ação que o admin precisa tomar é diferente em cada caso.
        get_logger(tenant_id="system", tenant_name="system", agent="prompt_manager_api").warn(
            message=f"Guardrail deletion blocked: {exc}",
            method="app.api.v1.endpoints.prompt_manager.delete_guardrail",
            line=117,
            thread_id="system",
            extra={"error": exc.code, "guardrail_id": guardrail_id},
        )
        raise HTTPException(
            status_code=409,
            detail=error_detail(exc.code, str(exc), exc.blockers),
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Guardrail não encontrado")


@router.get(
    "/prompts/{prompt_id}/tenants",
    response_model=PromptTenantsResponse,
    summary="Lista os tenants atualmente vinculados a um prompt",
)
def list_tenants_by_prompt(prompt_id: str):
    service = PromptManagerService(get_db_connection)
    try:
        return service.list_tenants_by_prompt(prompt_id)
    except PromptNotFoundError as exc:
        get_logger(tenant_id="system", tenant_name="system", agent="prompt_manager_api").warn(
            message=f"Prompt not found: {exc}",
            method="app.api.v1.endpoints.prompt_manager.list_tenants_by_prompt",
            line=138,
            thread_id="system",
            extra={"error": exc.code, "prompt_id": prompt_id},
        )
        raise HTTPException(status_code=404, detail=error_detail(exc.code, str(exc)))


@router.post(
    "/link-tenants",
    response_model=BulkTenantPromptLinkResponse,
    summary="Vincula um prompt a vários tenants numa única operação (all-or-nothing)",
)
def link_tenants_bulk(payload: BulkTenantPromptLinkSchema):
    service = PromptManagerService(get_db_connection)
    try:
        return service.link_tenants_bulk(
            payload.prompt_id, payload.tenant_ids, payload.custom_content_override
        )
    except PromptNotFoundError as exc:
        get_logger(tenant_id="system", tenant_name="system", agent="prompt_manager_api").warn(
            message=f"Prompt not found for bulk link: {exc}",
            method="app.api.v1.endpoints.prompt_manager.link_tenants_bulk",
            line=153,
            thread_id="system",
            extra={"error": exc.code, "prompt_id": payload.prompt_id},
        )
        raise HTTPException(status_code=404, detail=error_detail(exc.code, str(exc)))
    except TenantsNotFoundError as exc:
        get_logger(tenant_id="system", tenant_name="system", agent="prompt_manager_api").warn(
            message=f"Tenants not found for bulk link: {exc}",
            method="app.api.v1.endpoints.prompt_manager.link_tenants_bulk",
            line=155,
            thread_id="system",
            extra={"error": exc.code, "prompt_id": payload.prompt_id},
        )
        raise HTTPException(status_code=404, detail=error_detail(exc.code, str(exc), exc.blockers))

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
        get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_manager_api").error(
            message=f"Default prompt not configured: {exc}",
            method="app.api.v1.endpoints.prompt_manager.get_tenant_prompt_details",
            line=170,
            thread_id="system",
            extra={"error": "DEFAULT_PROMPT_NOT_CONFIGURED", "node_type": str(node_type)},
        )
        raise HTTPException(status_code=500, detail=str(exc))
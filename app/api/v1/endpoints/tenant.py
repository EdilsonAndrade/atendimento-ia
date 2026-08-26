import os

from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.tenant import (
    DeleteResponse,
    TenantCreate,
    TenantDeleteImpactResponse,
    TenantListResponse,
    TenantMessageLimitConfigResponse,
    TenantResponse,
    TenantUpdate,
    TenantUsageResponse,
)
from app.schemas.prompt_manager import error_detail
from modules.tenant.tenant_service import (
    PromptNodeTypeInvalidError,
    PromptNotFoundError,
    TenantService,
)
from modules.tenant_limits.domain.usage_policy import is_over_limit, percentage_used
from modules.tenant_limits.infrastructure.postgres_tenant_limit_config import PostgresTenantLimitConfig
from modules.tenant_limits.infrastructure.postgres_usage_counter import PostgresUsageCounter
from modules.observability.interface.logger_factory import get_logger

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def get_tenant_limit_config() -> PostgresTenantLimitConfig:
    return PostgresTenantLimitConfig()


def get_usage_counter() -> PostgresUsageCounter:
    return PostgresUsageCounter()


@router.get("", response_model=list[TenantResponse], summary="Buscar tenants por nome ou id")
def search_tenants(
    q: str | None = Query(None, min_length=1, description="Termo de busca — casado parcialmente contra id/name. Omitido, lista todos."),
    limit: int = Query(20, ge=1, le=100),
    tenant_service: TenantService = Depends(),
):
    return tenant_service.search_tenants(q, limit)


@router.get(
    "/list",
    response_model=TenantListResponse,
    summary="Listar tenants paginado, com tags de prompt/guardrail (grid da tela de Tenants, EDI-46)",
)
def list_tenants(
    q: str | None = Query(None, min_length=1, description="Termo de busca — casado parcialmente contra id/name. Omitido, lista todos."),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant_service: TenantService = Depends(),
):
    return tenant_service.list_tenants(q, limit, offset)


@router.get(
    "/message-limit-config",
    response_model=TenantMessageLimitConfigResponse,
    summary="Razão de chamadas de LLM por mensagem real — base da calculadora de dimensionamento de plano (EDI-63)",
)
def get_message_limit_config():
    """Registrado ANTES de `/{tenant_id}` de propósito — senão `/message-limit-config`
    seria capturado como um `tenant_id` literal (mesmo motivo de `/list` vir antes)."""
    return TenantMessageLimitConfigResponse(
        worst_case_calls_per_message=int(os.getenv("TENANT_LIMIT_WORST_CASE_CALLS_PER_MESSAGE", "3")),
        average_calls_per_message=float(os.getenv("TENANT_LIMIT_AVERAGE_CALLS_PER_MESSAGE", "3")),
    )


@router.post("/", response_model=TenantResponse)
def create_tenant(tenant_data: TenantCreate, tenant_service: TenantService = Depends()):
    """Cria o tenant já vinculado a um prompt operacional (EDI-43).

    O `prompt_id` é obrigatório no schema, então a ausência dele é barrada pelo
    Pydantic com 422 (formato de lista) antes de chegar aqui. Os dois erros
    abaixo são de regra de negócio e usam o envelope estruturado.
    """
    try:
        return tenant_service.create_tenant(tenant_data.dict())
    except PromptNotFoundError as exc:
        get_logger(tenant_id=tenant_data.tenant_id, tenant_name=tenant_data.tenant_id, agent="tenant_api").error(
            message=f"Tenant creation failed: prompt not found: {exc}",
            method="app.api.v1.endpoints.tenant.create_tenant",
            line=81,
            thread_id="system",
            extra={"error": "PROMPT_NOT_FOUND"},
        )
        raise HTTPException(status_code=404, detail=error_detail("PROMPT_NOT_FOUND", str(exc)))
    except PromptNodeTypeInvalidError as exc:
        get_logger(tenant_id=tenant_data.tenant_id, tenant_name=tenant_data.tenant_id, agent="tenant_api").error(
            message=f"Tenant creation failed: invalid node type: {exc}",
            method="app.api.v1.endpoints.tenant.create_tenant",
            line=81,
            thread_id="system",
            extra={"error": "PROMPT_NODE_TYPE_INVALID"},
        )
        raise HTTPException(
            status_code=400, detail=error_detail("PROMPT_NODE_TYPE_INVALID", str(exc))
        )


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, tenant_service: TenantService = Depends()):
    # Logic to retrieve a tenant by ID using the service
    tenant = tenant_service.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: str, tenant_data: TenantUpdate, tenant_service: TenantService = Depends()):
    # Logic to update an existing tenant using the service
    updated_tenant = tenant_service.update_tenant(tenant_id, tenant_data.dict())
    if updated_tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return updated_tenant

@router.get("/{tenant_id}/usage", response_model=TenantUsageResponse)
def get_tenant_usage(
    tenant_id: str,
    tenant_service: TenantService = Depends(),
    tenant_limit_config: PostgresTenantLimitConfig = Depends(get_tenant_limit_config),
    usage_counter: PostgresUsageCounter = Depends(get_usage_counter),
):
    """Consumo do mês corrente — base do indicador visual da UI admin (EDI-63)."""
    if tenant_service.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    monthly_message_limit, _ = tenant_limit_config.get_limit_and_emails(tenant_id)
    current_month_calls = usage_counter.count_current_month(tenant_id)

    return TenantUsageResponse(
        tenant_id=tenant_id,
        monthly_message_limit=monthly_message_limit,
        current_month_calls=current_month_calls,
        percentage_used=percentage_used(current_month_calls, monthly_message_limit),
        blocked=is_over_limit(current_month_calls, monthly_message_limit),
    )


@router.get("/{tenant_id}/delete-impact", response_model=TenantDeleteImpactResponse)
def get_tenant_delete_impact(tenant_id: str, tenant_service: TenantService = Depends()):
    """Pré-visualização do que `DELETE /{tenant_id}` faria agora — o que seria
    excluído de fato versus apenas desvinculado (EDI-45)."""
    impact = tenant_service.get_delete_impact(tenant_id)
    if impact is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"tenant_id": tenant_id, **impact}


@router.delete("/{tenant_id}", response_model=DeleteResponse)
def delete_tenant(tenant_id: str, tenant_service: TenantService = Depends()):
    """Exclui o tenant em cascata: prompts/guardrails exclusivos dele são
    excluídos de fato; compartilhados ou globais são só desvinculados (EDI-45)."""
    deleted_tenant_id = tenant_service.delete_tenant_cascade(tenant_id)
    if deleted_tenant_id is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"id": deleted_tenant_id, "message": "Tenant deleted successfully"}




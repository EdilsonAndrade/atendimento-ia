from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, DeleteResponse
from app.schemas.prompt_manager import error_detail
from modules.tenant.tenant_service import (
    PromptNodeTypeInvalidError,
    PromptNotFoundError,
    TenantService,
)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("", response_model=list[TenantResponse], summary="Buscar tenants por nome ou id")
def search_tenants(
    q: str = Query(..., min_length=1, description="Termo de busca — casado parcialmente contra id/name"),
    limit: int = Query(20, ge=1, le=100),
    tenant_service: TenantService = Depends(),
):
    return tenant_service.search_tenants(q, limit)


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
        raise HTTPException(status_code=404, detail=error_detail("PROMPT_NOT_FOUND", str(exc)))
    except PromptNodeTypeInvalidError as exc:
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

@router.delete("/{tenant_id}", response_model=DeleteResponse)
def delete_tenant(tenant_id: str, tenant_service: TenantService = Depends()):
    # Logic to delete a tenant using the service
    deleted_tenant_id = tenant_service.delete_tenant(tenant_id)
    if deleted_tenant_id is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"id": deleted_tenant_id, "message": "Tenant deleted successfully"}




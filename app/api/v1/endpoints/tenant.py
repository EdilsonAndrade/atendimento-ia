from fastapi import APIRouter, Depends, HTTPException
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, DeleteResponse
from modules.tenant.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("/", response_model=TenantResponse)
def create_tenant(tenant_data: TenantCreate, tenant_service: TenantService = Depends()):
    # Logic to create a new tenant using the service
    created_tenant = tenant_service.create_tenant(tenant_data.dict())
    return created_tenant


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




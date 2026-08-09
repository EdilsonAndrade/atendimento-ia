from modules.tenant.tenant_repository import TenantRepository

class TenantService:
    def __init__(self):
        self.tenant_repository = TenantRepository()

    def create_tenant(self, tenant_data: dict) -> dict:
        # Logic to create a new tenant using the repository
        return self.tenant_repository.create_tenant(tenant_data)

    def get_tenant(self, tenant_id: str) -> dict | None:
        # Logic to retrieve a tenant by ID using the repository
        return self.tenant_repository.get_tenant(tenant_id)

    def get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Alias for get_tenant — used by Google Calendar tools."""
        return self.get_tenant(tenant_id)

    def update_tenant(self, tenant_id: str, tenant_data: dict) -> dict | None:
        # Logic to update an existing tenant using the repository
        return self.tenant_repository.update_tenant(tenant_id, tenant_data)

    def delete_tenant(self, tenant_id: str) -> int | None:
        # Logic to delete a tenant using the repository
        return self.tenant_repository.delete_tenant(tenant_id)
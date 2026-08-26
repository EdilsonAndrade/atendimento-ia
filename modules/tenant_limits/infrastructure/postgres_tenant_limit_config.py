"""Adapter Postgres de `TenantLimitConfigPort` — Infrastructure layer.

`tenant/` é um módulo legado (grandfathered, ver constituição > Governance >
Legacy Migration Policy): em vez de ler a tabela `tenants` diretamente aqui,
reaproveitamos `TenantService.get_tenant_by_id`, seu método público já existente.
"""
from modules.tenant.tenant_service import TenantService


class PostgresTenantLimitConfig:
    def __init__(self, tenant_service: TenantService | None = None):
        self._tenant_service = tenant_service or TenantService()

    def get_limit_and_emails(self, tenant_id: str) -> tuple[int | None, list[str]]:
        tenant = self._tenant_service.get_tenant_by_id(tenant_id)
        if not tenant:
            return None, []
        return tenant.get("monthly_message_limit"), tenant.get("notification_emails") or []

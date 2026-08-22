from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository
from modules.tenant.tenant_repository import TenantRepository


class PromptNotFoundError(Exception):
    """O prompt informado no cadastro do tenant não existe."""

    def __init__(self, prompt_id: str):
        self.prompt_id = prompt_id
        super().__init__(f"Prompt {prompt_id!r} não encontrado.")


class PromptNodeTypeInvalidError(Exception):
    """O prompt existe, mas não é do node_type exigido pelo cadastro."""

    def __init__(self, prompt_id: str, node_type: str, esperado: str = "operational"):
        self.prompt_id = prompt_id
        self.node_type = node_type
        self.esperado = esperado
        super().__init__(
            f"O prompt informado é do tipo {node_type!r}. "
            f"O cadastro de tenant exige um prompt do tipo {esperado!r}."
        )


class TenantService:
    def __init__(self):
        self.tenant_repository = TenantRepository()
        self.prompt_repository = PromptManagerRepository(get_db_connection)

    def create_tenant(self, tenant_data: dict) -> dict:
        """Cria o tenant exigindo o vínculo com um prompt operacional (EDI-43).

        A validação do prompt vem ANTES de qualquer escrita: assim os dois erros
        comuns (prompt inexistente, node_type errado) nunca deixam resíduo no
        banco. A criação em si é atômica no repositório.
        """
        prompt_id = tenant_data["prompt_id"]
        prompt = self.prompt_repository.get_prompt_by_id(prompt_id)

        if not prompt:
            raise PromptNotFoundError(prompt_id)

        if prompt["node_type"] != "operational":
            raise PromptNodeTypeInvalidError(prompt_id, prompt["node_type"])

        return self.tenant_repository.create_tenant_with_prompt(tenant_data, prompt_id)

    def get_tenant(self, tenant_id: str) -> dict | None:
        # Logic to retrieve a tenant by ID using the repository
        return self.tenant_repository.get_tenant(tenant_id)

    def get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Alias for get_tenant — used by Google Calendar tools."""
        return self.get_tenant(tenant_id)

    def search_tenants(self, term: str, limit: int = 20) -> list:
        return self.tenant_repository.search_tenants(term, limit)

    def update_tenant(self, tenant_id: str, tenant_data: dict) -> dict | None:
        # Logic to update an existing tenant using the repository
        return self.tenant_repository.update_tenant(tenant_id, tenant_data)

    def delete_tenant(self, tenant_id: str) -> int | None:
        # Logic to delete a tenant using the repository
        return self.tenant_repository.delete_tenant(tenant_id)
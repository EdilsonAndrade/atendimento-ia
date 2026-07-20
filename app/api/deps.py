# Injeção de Dependências comuns (ex: extração de Tenant)
from fastapi import Header, HTTPException, status

async def get_tenant_id(x_tenant_id: str= Header(...,alias="X-Tenant-ID", description="Identificador único e exclusivo do cliente assinante do SaaS")) -> str:
    """
    Dependência mestre para extração e validação do Tenant.
    No futuro, este bloco consultará o banco central PostgreSQL para verificar se o ID do
    cliente está ativo e com a assinatura paga.
    """
    if not x_tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O cabeçalho X-Tenant-ID não pode ser uma string vazia."
        )
    return x_tenant_id
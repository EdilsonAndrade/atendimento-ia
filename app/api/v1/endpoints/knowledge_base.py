from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.schemas.knowledge_base import (
    KnowledgeBaseDeleteResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpsertRequest,
)
from modules.knowledge_base.application.use_cases import (
    DeleteTenantKnowledgeBase,
    GetTenantKnowledgeBase,
    ReindexTenantKnowledgeBase,
    UpsertTenantKnowledgeBase,
)
from modules.knowledge_base.domain.knowledge_base_document import EmptyKnowledgeBaseContentError
from modules.knowledge_base.infrastructure.pgvector_knowledge_base_adapter import (
    PgVectorKnowledgeBaseAdapter,
)
from modules.knowledge_base.infrastructure.postgres_knowledge_base_repository import (
    PostgresKnowledgeBaseRepository,
)
from modules.tenant.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["Knowledge Base"])


def get_knowledge_base_repository() -> PostgresKnowledgeBaseRepository:
    return PostgresKnowledgeBaseRepository()


def get_vector_store() -> PgVectorKnowledgeBaseAdapter:
    return PgVectorKnowledgeBaseAdapter()


def _ensure_tenant_exists(tenant_id: str, tenant_service: TenantService) -> None:
    if tenant_service.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")


@router.get(
    "/{tenant_id}/knowledge-base",
    response_model=KnowledgeBaseResponse,
    summary="Ver o conteúdo atual da base de conhecimento de um tenant",
)
def get_tenant_knowledge_base(
    tenant_id: str,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseRepository = Depends(get_knowledge_base_repository),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    document = GetTenantKnowledgeBase(repository).execute(tenant_id)
    if document is None:
        return KnowledgeBaseResponse(tenant_id=tenant_id, content=None, updated_at=None)

    return KnowledgeBaseResponse(
        tenant_id=document.tenant_id, content=document.content, updated_at=document.updated_at
    )


@router.put(
    "/{tenant_id}/knowledge-base",
    response_model=KnowledgeBaseResponse,
    summary="Criar ou editar (upsert) a base de conhecimento de um tenant",
)
def upsert_tenant_knowledge_base(
    tenant_id: str,
    payload: KnowledgeBaseUpsertRequest,
    background_tasks: BackgroundTasks,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
):
    """Upsert único: cria a base de conhecimento quando o tenant não tem uma, ou substitui
    a existente — a distinção é invisível para quem chama (mesmo request/response)."""
    _ensure_tenant_exists(tenant_id, tenant_service)

    try:
        document = UpsertTenantKnowledgeBase(repository).execute(tenant_id, payload.content)
    except EmptyKnowledgeBaseContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Revetorização roda em background — nunca bloqueia a resposta (Princípio V da constituição).
    background_tasks.add_task(
        ReindexTenantKnowledgeBase(vector_store).execute, tenant_id, document.content
    )

    return KnowledgeBaseResponse(
        tenant_id=document.tenant_id, content=document.content, updated_at=document.updated_at
    )


@router.delete(
    "/{tenant_id}/knowledge-base",
    response_model=KnowledgeBaseDeleteResponse,
    summary="Excluir a base de conhecimento de um tenant",
)
def delete_tenant_knowledge_base(
    tenant_id: str,
    background_tasks: BackgroundTasks,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    deleted = DeleteTenantKnowledgeBase(repository).execute(tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Nenhuma base de conhecimento encontrada para este tenant"
        )

    background_tasks.add_task(ReindexTenantKnowledgeBase(vector_store).execute_delete, tenant_id)

    return KnowledgeBaseDeleteResponse(
        tenant_id=tenant_id, message="Base de conhecimento removida com sucesso."
    )

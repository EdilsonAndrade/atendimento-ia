import json
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.knowledge_base import (
    DuplicateConflictResponse,
    DuplicateResolutionRequest,
    KnowledgeBaseDeleteResponse,
    KnowledgeBaseIngestResponse,
    KnowledgeBaseItemDetailResponse,
    KnowledgeBaseItemResponse,
    KnowledgeBaseItemSummary,
    KnowledgeBaseItemUpdateRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseUpsertRequest,
)
from modules.knowledge_base.application.use_cases import (
    DeleteTenantKnowledgeBase,
    DeleteTenantKnowledgeBaseItem,
    DuplicateConflictError,
    DuplicateResolution,
    GetTenantKnowledgeBase,
    GetTenantKnowledgeBaseItem,
    IngestKnowledgeBaseItems,
    ItemNotFoundError,
    ListTenantKnowledgeBaseItems,
    NewItemInput,
    ReindexTenantKnowledgeBase,
    ReindexTenantKnowledgeBaseItem,
    ReplaceTenantKnowledgeBaseItemFile,
    UpdateTenantKnowledgeBaseItemContent,
    UpsertTenantKnowledgeBase,
)
from modules.knowledge_base.domain.knowledge_base_document import EmptyKnowledgeBaseContentError
from modules.knowledge_base.domain.knowledge_base_item import UnsupportedFileTypeError
from modules.knowledge_base.infrastructure.file_text_extractor_adapter import FileTextExtractorAdapter
from modules.knowledge_base.infrastructure.pgvector_knowledge_base_adapter import (
    PgVectorKnowledgeBaseAdapter,
)
from modules.knowledge_base.infrastructure.postgres_knowledge_base_items_repository import (
    PostgresKnowledgeBaseItemsRepository,
)
from modules.knowledge_base.infrastructure.postgres_knowledge_base_repository import (
    PostgresKnowledgeBaseRepository,
)
from modules.tenant.tenant_service import TenantService
from modules.observability.interface.logger_factory import get_logger

router = APIRouter(prefix="/tenants", tags=["Knowledge Base"])


def get_knowledge_base_repository() -> PostgresKnowledgeBaseRepository:
    return PostgresKnowledgeBaseRepository()


def get_knowledge_base_items_repository() -> PostgresKnowledgeBaseItemsRepository:
    return PostgresKnowledgeBaseItemsRepository()


def get_vector_store() -> PgVectorKnowledgeBaseAdapter:
    return PgVectorKnowledgeBaseAdapter()


def get_file_text_extractor() -> FileTextExtractorAdapter:
    return FileTextExtractorAdapter()


def _ensure_tenant_exists(tenant_id: str, tenant_service: TenantService) -> None:
    if tenant_service.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")


def _to_item_response(item) -> KnowledgeBaseItemResponse:
    return KnowledgeBaseItemResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        source_type=item.source_type,
        filename=item.filename,
        content_preview=item.content_preview,
        content_length=len(item.content),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_item_detail_response(item) -> KnowledgeBaseItemDetailResponse:
    return KnowledgeBaseItemDetailResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        source_type=item.source_type,
        filename=item.filename,
        content=item.content,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


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
    summary="Substituir toda a base de conhecimento de um tenant por um único texto",
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
    a existente — a distinção é invisível para quem chama (mesmo request/response).

    Equivale a `POST .../knowledge-base/items` com `mode=replace` e um único item de
    texto: todos os itens anteriores do tenant são descartados."""
    _ensure_tenant_exists(tenant_id, tenant_service)

    try:
        document = UpsertTenantKnowledgeBase(repository).execute(tenant_id, payload.content)
    except EmptyKnowledgeBaseContentError as exc:
        get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="knowledge_base_api").warn(
            message=f"Knowledge base upsert rejected: {exc}",
            method="app.api.v1.endpoints.knowledge_base.upsert_tenant_knowledge_base",
            line=79,
            thread_id="system",
            extra={"error": "EMPTY_CONTENT"},
        )
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


@router.get(
    "/{tenant_id}/knowledge-base/items",
    response_model=List[KnowledgeBaseItemResponse],
    summary="Listar os itens (arquivos e textos) da base de conhecimento de um tenant",
)
def list_tenant_knowledge_base_items(
    tenant_id: str,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    items = ListTenantKnowledgeBaseItems(repository).execute(tenant_id)
    return [_to_item_response(item) for item in items]


@router.get(
    "/{tenant_id}/knowledge-base/items/{item_id}",
    response_model=KnowledgeBaseItemDetailResponse,
    summary="Ver o conteúdo completo de um item da base de conhecimento",
)
def get_tenant_knowledge_base_item(
    tenant_id: str,
    item_id: str,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    item = GetTenantKnowledgeBaseItem(repository).execute(tenant_id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado para este tenant")

    return _to_item_detail_response(item)


@router.post(
    "/{tenant_id}/knowledge-base/items",
    response_model=KnowledgeBaseIngestResponse,
    status_code=201,
    responses={409: {"model": DuplicateConflictResponse}},
    summary="Enviar novos arquivos e/ou textos para a base de conhecimento de um tenant",
)
def ingest_tenant_knowledge_base_items(
    tenant_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    texts: List[str] = Form(default=[]),
    duplicate_resolutions: Optional[str] = Form(default=None),
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
    extractor: FileTextExtractorAdapter = Depends(get_file_text_extractor),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    if mode not in ("append", "replace"):
        raise HTTPException(status_code=422, detail="mode deve ser 'append' ou 'replace'")

    if not files and not texts:
        raise HTTPException(status_code=422, detail="Envie ao menos um arquivo ou um texto")

    resolutions = []
    if duplicate_resolutions:
        try:
            raw_resolutions = json.loads(duplicate_resolutions)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=422, detail="duplicate_resolutions deve ser um JSON válido")
        for raw in raw_resolutions:
            parsed = DuplicateResolutionRequest(**raw)
            resolutions.append(
                DuplicateResolution(
                    filename=parsed.filename, action=parsed.action, existing_item_id=parsed.existing_item_id
                )
            )

    new_items = []
    for text in texts:
        new_items.append(NewItemInput(source_type="texto", content=text, filename=None))

    for upload in files:
        try:
            content = extractor.extract(upload.file, upload.filename)
        except UnsupportedFileTypeError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        if not content or not content.strip():
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Não foi possível extrair texto de '{upload.filename}'. O arquivo pode ser um "
                    "PDF digitalizado (imagem, sem camada de texto — OCR não é suportado), uma "
                    "planilha vazia, ou estar corrompido."
                ),
            )
        new_items.append(NewItemInput(source_type="file", content=content, filename=upload.filename))

    try:
        result = IngestKnowledgeBaseItems(repository).execute(
            tenant_id, new_items, mode=mode, duplicate_resolutions=resolutions
        )
    except DuplicateConflictError as exc:
        return JSONResponse(
            status_code=409,
            content=DuplicateConflictResponse(detail=str(exc), conflicts=exc.conflicts).model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    for item in [*result.created, *result.replaced]:
        background_tasks.add_task(
            ReindexTenantKnowledgeBaseItem(vector_store).execute, tenant_id, item.id, item.content
        )

    return KnowledgeBaseIngestResponse(
        created=[
            KnowledgeBaseItemSummary(id=item.id, filename=item.filename, source_type=item.source_type)
            for item in result.created
        ],
        replaced=[
            KnowledgeBaseItemSummary(id=item.id, filename=item.filename, source_type=item.source_type)
            for item in result.replaced
        ],
    )


@router.put(
    "/{tenant_id}/knowledge-base/items/{item_id}",
    response_model=KnowledgeBaseItemDetailResponse,
    summary="Editar manualmente o texto de um item da base de conhecimento",
)
def update_tenant_knowledge_base_item(
    tenant_id: str,
    item_id: str,
    payload: KnowledgeBaseItemUpdateRequest,
    background_tasks: BackgroundTasks,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    try:
        item = UpdateTenantKnowledgeBaseItemContent(repository).execute(tenant_id, item_id, payload.content)
    except ItemNotFoundError:
        raise HTTPException(status_code=404, detail="Item não encontrado para este tenant")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    background_tasks.add_task(
        ReindexTenantKnowledgeBaseItem(vector_store).execute, tenant_id, item.id, item.content
    )

    return _to_item_detail_response(item)


@router.put(
    "/{tenant_id}/knowledge-base/items/{item_id}/file",
    response_model=KnowledgeBaseItemDetailResponse,
    summary="Substituir o arquivo de um item existente, enviando um novo arquivo por cima",
)
def replace_tenant_knowledge_base_item_file(
    tenant_id: str,
    item_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
    extractor: FileTextExtractorAdapter = Depends(get_file_text_extractor),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    try:
        content = extractor.extract(file.file, file.filename)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not content or not content.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Não foi possível extrair texto de '{file.filename}'. O arquivo pode ser um "
                "PDF digitalizado (imagem, sem camada de texto — OCR não é suportado), uma "
                "planilha vazia, ou estar corrompido."
            ),
        )

    try:
        item = ReplaceTenantKnowledgeBaseItemFile(repository).execute(
            tenant_id, item_id, file.filename, content
        )
    except ItemNotFoundError:
        raise HTTPException(status_code=404, detail="Item não encontrado para este tenant")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    background_tasks.add_task(
        ReindexTenantKnowledgeBaseItem(vector_store).execute, tenant_id, item.id, item.content
    )

    return _to_item_detail_response(item)


@router.delete(
    "/{tenant_id}/knowledge-base/items/{item_id}",
    status_code=204,
    summary="Excluir um item individual da base de conhecimento, mantendo os demais",
)
def delete_tenant_knowledge_base_item(
    tenant_id: str,
    item_id: str,
    background_tasks: BackgroundTasks,
    tenant_service: TenantService = Depends(),
    repository: PostgresKnowledgeBaseItemsRepository = Depends(get_knowledge_base_items_repository),
    vector_store: PgVectorKnowledgeBaseAdapter = Depends(get_vector_store),
):
    _ensure_tenant_exists(tenant_id, tenant_service)

    deleted = DeleteTenantKnowledgeBaseItem(repository).execute(tenant_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item não encontrado para este tenant")

    background_tasks.add_task(
        ReindexTenantKnowledgeBaseItem(vector_store).execute_delete, tenant_id, item_id
    )

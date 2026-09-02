from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class KnowledgeBaseResponse(BaseModel):
    tenant_id: str
    content: Optional[str] = None
    updated_at: Optional[datetime] = None


class KnowledgeBaseUpsertRequest(BaseModel):
    content: str = Field(..., min_length=1)


class KnowledgeBaseDeleteResponse(BaseModel):
    tenant_id: str
    message: str


class KnowledgeBaseItemResponse(BaseModel):
    """Linha da grid de itens (EDI-39) — preview limitado, nunca o conteúdo completo."""

    id: str
    tenant_id: str
    source_type: Literal["file", "texto"]
    filename: Optional[str] = None
    content_preview: str
    content_length: int
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseItemDetailResponse(BaseModel):
    """Conteúdo completo de um item, para o modal com scroll."""

    id: str
    tenant_id: str
    source_type: Literal["file", "texto"]
    filename: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseItemUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class KnowledgeBaseItemSummary(BaseModel):
    id: str
    filename: Optional[str] = None
    source_type: Literal["file", "texto"]


class KnowledgeBaseIngestResponse(BaseModel):
    created: List[KnowledgeBaseItemSummary] = Field(default_factory=list)
    replaced: List[KnowledgeBaseItemSummary] = Field(default_factory=list)


class DuplicateResolutionRequest(BaseModel):
    filename: str
    action: Literal["replace", "keep_both"]
    existing_item_id: Optional[str] = None


class DuplicateConflictItem(BaseModel):
    filename: str
    existing_item_id: str


class DuplicateConflictResponse(BaseModel):
    detail: str
    conflicts: List[DuplicateConflictItem]

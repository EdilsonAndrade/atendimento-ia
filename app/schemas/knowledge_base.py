from datetime import datetime
from typing import Optional

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

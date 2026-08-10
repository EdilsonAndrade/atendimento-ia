# --- SCHEMAS (PYDANTIC) ---
from typing import List, Optional

from pydantic import BaseModel

class GuardrailCreateSchema(BaseModel):
    titulo: str
    conteudo: str
    is_global: bool = False

class PromptCreateSchema(BaseModel):
    titulo: str
    conteudo: str
    is_default: bool = False
    guardrail_ids: List[str] = []

class TenantPromptLinkSchema(BaseModel):
    tenant_id: str
    prompt_id: str
    custom_content_override: Optional[str] = None

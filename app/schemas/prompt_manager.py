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

class GuardrailAssociadoSchema(BaseModel):
    id: str
    titulo: str
    conteudo: str
    is_global: bool

class TenantPromptOverviewResponse(BaseModel):
    tenant_id: str
    prompt_id: str
    prompt_titulo: str
    prompt_conteudo: str
    custom_content_override: Optional[str] = None
    is_default_prompt: bool
    guardrails_associados: List[GuardrailAssociadoSchema]

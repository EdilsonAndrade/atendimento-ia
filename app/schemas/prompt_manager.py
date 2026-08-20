# --- SCHEMAS (PYDANTIC) ---
from typing import List, Literal, Optional

from pydantic import BaseModel

NodeType = Literal["operational", "institutional", "chitchat"]

class GuardrailCreateSchema(BaseModel):
    titulo: str
    conteudo: str
    is_global: bool = False

class PromptCreateSchema(BaseModel):
    titulo: str
    conteudo: str
    is_default: bool = False
    node_type: NodeType = "operational"
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
    node_type: NodeType
    prompt_id: str
    prompt_titulo: str
    prompt_conteudo: str
    custom_content_override: Optional[str] = None
    is_default_prompt: bool
    is_active: bool
    guardrails_associados: List[GuardrailAssociadoSchema]

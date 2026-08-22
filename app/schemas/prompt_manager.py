# --- SCHEMAS (PYDANTIC) ---
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

NodeType = Literal["operational", "institutional", "chitchat"]

# --- ENVELOPE DE ERRO ESTRUTURADO (EDI-43 / contrato do EDI-44) ---
# Erros de REGRA DE NEGÓCIO passam `detail` como objeto, para o frontend decidir
# pelo `code` (estável, é o contrato) em vez de parsear o `message` (texto de UI,
# pode mudar). Erros de VALIDAÇÃO DE SCHEMA mantêm o formato de lista nativo do
# Pydantic — uniformizá-los exigiria um exception handler global, que mudaria o
# formato de erro de todos os endpoints do projeto.

ErrorCode = Literal[
    "PROMPT_NOT_FOUND",
    "PROMPT_NODE_TYPE_INVALID",
    "PROMPT_IN_USE_BY_TENANTS",
    "GUARDRAIL_IS_GLOBAL",
    "GUARDRAIL_IN_USE_BY_TENANTS",
    "TENANT_NOT_FOUND",
]


class ErrorBlocker(BaseModel):
    """Um item que impede a operação, para a UI listar o caminho de saída em vez
    de só exibir 'não é possível'."""

    type: Literal["tenant", "prompt"]
    id: str
    name: Optional[str] = None
    tenant_count: Optional[int] = None


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    blockers: List[ErrorBlocker] = Field(default_factory=list)


def error_detail(code: str, message: str, blockers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Monta o `detail` do HTTPException. `blockers` vem sempre como lista —
    nunca ausente ou None — para o consumidor não precisar tratar os dois casos."""
    return {"code": code, "message": message, "blockers": blockers or []}

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


class BulkTenantPromptLinkSchema(BaseModel):
    """Associa UM prompt a N tenants numa única operação (EDI-43 / FR-019).

    O modelo N:N `tenant_prompts` já suportava isto sem migração; faltava a
    operação em lote. All-or-nothing: se qualquer tenant não existir, nenhum
    vínculo é aplicado.
    """

    prompt_id: str
    tenant_ids: List[str] = Field(..., min_length=1)
    # Aplicado a TODOS os tenants da lista. Para conteúdo distinto por tenant, o
    # endpoint singular /link-tenant continua sendo o caminho.
    custom_content_override: Optional[str] = None


class TenantResumoSchema(BaseModel):
    id: str
    name: Optional[str] = None


class PromptTenantsResponse(BaseModel):
    """Tenants vinculados a um prompt — sustenta a tela de associação em massa,
    onde o admin precisa ver quem já usa o prompt antes de aplicá-lo a outros."""

    prompt_id: str
    prompt_titulo: str
    node_type: NodeType
    tenant_count: int
    tenants: List[TenantResumoSchema]


class BulkTenantPromptLinkResponse(BaseModel):
    prompt_id: str
    node_type: NodeType
    linked_count: int
    tenant_ids: List[str]

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

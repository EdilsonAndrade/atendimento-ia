"""Entidade de Domínio: uma mensagem individual de uma conversa (EDI-53).

Framework-free (Princípio III) — nenhuma dependência de FastAPI/psycopg/LangChain.
"""
from dataclasses import dataclass, field
from datetime import datetime

VALID_ROLES = ("human", "ai")


@dataclass
class ConversationMessage:
    tenant_id: str
    base_thread_id: str
    active_thread_id: str
    role: str
    content: str
    created_at: datetime | None = field(default=None)

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"role inválido: {self.role!r} (esperado um de {VALID_ROLES})")

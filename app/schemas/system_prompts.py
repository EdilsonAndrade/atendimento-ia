from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Conjunto fixo, semeado pela migration 0010_system_prompts — não há endpoint
# de criação, então o schema pode fechar os valores válidos aqui.
SystemPromptKey = Literal[
    "routing_agent",
    "groundedness_rule",
    "chitchat_no_knowledge_rule",
    "booking_integrity_rule",
]


class SystemPromptResponse(BaseModel):
    id: UUID
    prompt_key: str
    titulo: str
    current_version: str
    last_version: str
    created_at: datetime
    updated_at: datetime


class SystemPromptUpdateSchema(BaseModel):
    conteudo: str = Field(..., min_length=1, description="Novo conteúdo, vira current_version")

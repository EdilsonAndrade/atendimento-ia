from dataclasses import dataclass
from datetime import datetime


class EmptyKnowledgeBaseContentError(ValueError):
    """Levantado quando o conteúdo da base de conhecimento é vazio ou só espaços."""


@dataclass(frozen=True)
class KnowledgeBaseDocument:
    """Entidade de domínio: o conteúdo textual único de um tenant na base de conhecimento.

    Framework-free por design (Constituição, Princípio III) — sem imports de FastAPI, psycopg
    ou LangChain aqui.
    """

    tenant_id: str
    content: str
    updated_at: datetime

    def __post_init__(self):
        KnowledgeBaseDocument.validate_content(self.content)

    @staticmethod
    def validate_content(content: str) -> None:
        if not content or not content.strip():
            raise EmptyKnowledgeBaseContentError(
                "O conteúdo da base de conhecimento não pode ser vazio."
            )

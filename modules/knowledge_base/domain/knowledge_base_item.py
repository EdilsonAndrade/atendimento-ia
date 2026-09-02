from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

SourceType = Literal["file", "texto"]

SUPPORTED_FILE_EXTENSIONS = (".pdf", ".xls", ".xlsx", ".csv")

PREVIEW_LENGTH = 1000


class UnsupportedFileTypeError(ValueError):
    """Levantado quando o arquivo enviado não tem uma extensão suportada."""


@dataclass(frozen=True)
class KnowledgeBaseItem:
    """Entidade de domínio: um item individual (arquivo ou texto) da base de
    conhecimento de um tenant.

    Framework-free por design (Constituição, Princípio III) — sem imports de
    FastAPI, psycopg ou LangChain aqui.
    """

    id: str
    tenant_id: str
    source_type: SourceType
    filename: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        KnowledgeBaseItem.validate_content(self.content)

    @staticmethod
    def validate_content(content: str) -> None:
        if not content or not content.strip():
            raise ValueError("O conteúdo do item da base de conhecimento não pode ser vazio.")

    @property
    def content_preview(self) -> str:
        return self.content[:PREVIEW_LENGTH]

    @staticmethod
    def validate_filename_extension(filename: str) -> None:
        lower_name = filename.lower()
        if not lower_name.endswith(SUPPORTED_FILE_EXTENSIONS):
            raise UnsupportedFileTypeError(
                f"Extensão de arquivo não suportada em '{filename}'. "
                f"Extensões aceitas: {', '.join(SUPPORTED_FILE_EXTENSIONS)}."
            )

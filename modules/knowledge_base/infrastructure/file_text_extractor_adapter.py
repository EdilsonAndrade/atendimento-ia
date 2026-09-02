from typing import BinaryIO

from protocols.file_data_reader import extract_text_from_pdf, extract_text_from_table
from modules.knowledge_base.domain.knowledge_base_item import KnowledgeBaseItem


class FileTextExtractorAdapter:
    """Implementa FileTextExtractorPort reaproveitando os extratores de
    `protocols/file_data_reader.py` (pypdf + pandas), sem duplicar a lógica de parsing."""

    def extract(self, file: BinaryIO, filename: str) -> str:
        KnowledgeBaseItem.validate_filename_extension(filename)

        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            return extract_text_from_pdf(file)
        return extract_text_from_table(file, filename)

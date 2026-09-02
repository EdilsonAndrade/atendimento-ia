import io

import pandas as pd
import pytest
from pypdf import PdfWriter

from modules.knowledge_base.domain.knowledge_base_item import UnsupportedFileTypeError
from modules.knowledge_base.infrastructure.file_text_extractor_adapter import FileTextExtractorAdapter


def test_extract_rejects_unsupported_extension():
    extractor = FileTextExtractorAdapter()

    with pytest.raises(UnsupportedFileTypeError):
        extractor.extract(io.BytesIO(b"conteudo qualquer"), "documento.docx")


def test_extract_from_csv_produces_readable_rows():
    extractor = FileTextExtractorAdapter()
    csv_bytes = io.BytesIO("servico,preco\nCorte,30\nBarba,20\n".encode("utf-8"))

    result = extractor.extract(csv_bytes, "servicos.csv")

    assert "servicos.csv" in result
    assert "servico: Corte" in result
    assert "preco: 30" in result
    assert "servico: Barba" in result


def test_extract_from_xlsx_produces_readable_rows():
    extractor = FileTextExtractorAdapter()
    buffer = io.BytesIO()
    pd.DataFrame({"servico": ["Corte"], "preco": [30]}).to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)

    result = extractor.extract(buffer, "precos.xlsx")

    assert "precos.xlsx" in result
    assert "servico: Corte" in result
    assert "preco: 30" in result


def test_extract_from_xlsx_reads_all_sheets():
    extractor = FileTextExtractorAdapter()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"servico": ["Corte"], "preco": [30]}).to_excel(writer, sheet_name="Servicos", index=False)
        pd.DataFrame({"produto": ["Pomada"], "preco": [45]}).to_excel(writer, sheet_name="Produtos", index=False)
    buffer.seek(0)

    result = extractor.extract(buffer, "catalogo.xlsx")

    assert "aba: Servicos" in result
    assert "aba: Produtos" in result
    assert "servico: Corte" in result
    assert "produto: Pomada" in result


def test_extract_from_pdf_returns_a_string_without_raising():
    extractor = FileTextExtractorAdapter()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    result = extractor.extract(buffer, "documento.pdf")

    assert isinstance(result, str)

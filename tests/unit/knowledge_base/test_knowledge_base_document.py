from datetime import datetime, timezone

import pytest

from modules.knowledge_base.domain.knowledge_base_document import (
    EmptyKnowledgeBaseContentError,
    KnowledgeBaseDocument,
)


def test_creates_document_with_valid_content():
    document = KnowledgeBaseDocument(
        tenant_id="1234",
        content="Regra: o barbeiro Lucas atende de terça a sábado.",
        updated_at=datetime.now(timezone.utc),
    )

    assert document.tenant_id == "1234"
    assert document.content.startswith("Regra:")


def test_rejects_empty_content():
    with pytest.raises(EmptyKnowledgeBaseContentError):
        KnowledgeBaseDocument(tenant_id="1234", content="", updated_at=datetime.now(timezone.utc))


def test_rejects_whitespace_only_content():
    with pytest.raises(EmptyKnowledgeBaseContentError):
        KnowledgeBaseDocument(tenant_id="1234", content="   \n\t  ", updated_at=datetime.now(timezone.utc))


def test_validate_content_static_helper_rejects_blank_without_building_instance():
    with pytest.raises(EmptyKnowledgeBaseContentError):
        KnowledgeBaseDocument.validate_content("   ")

    # não levanta para conteúdo válido
    KnowledgeBaseDocument.validate_content("conteúdo válido")

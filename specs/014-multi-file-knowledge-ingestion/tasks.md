# Tasks: Ingestão de Dados por Múltiplos Arquivos

**Input**: plan.md, spec.md
**Tests**: incluídos (unit + integration), conforme Princípio VI da constituição.

## Phase 1: Migration & schema
- [X] T001 Migration `migrations/versions/0011_tenant_kb_items.py` — cria `tenant_knowledge_base_items` (id, tenant_id, source_type, filename, content, created_at, updated_at) + índice em `tenant_id`; backfill: 1 item `source_type='texto'` por linha já existente em `tenant_knowledge_base`; dropa a tabela antiga. Conferido `len("0011_tenant_kb_items") == 20` ≤ 32 (guardrail 6 do CLAUDE.md).

## Phase 2: Domain
- [X] T002 `modules/knowledge_base/domain/knowledge_base_item.py` — `KnowledgeBaseItem` (frozen dataclass) + `validate_content` + `content_preview`.
- [X] T003 `UnsupportedFileTypeError` (junto ao `EmptyKnowledgeBaseContentError` existente); `DuplicateConflictError` ficou na Application (é uma regra de orquestração entre itens, não um invariante de uma única entidade).

## Phase 3: Application (use cases + ports)
- [X] T004 `ports.py` — `FileTextExtractorPort`, `KnowledgeBaseItemsRepositoryPort`; `VectorStorePort` estendido com `reindex_item`/`delete_item`.
- [X] T005 `ListTenantKnowledgeBaseItems`, `GetTenantKnowledgeBaseItem`.
- [X] T006 `IngestKnowledgeBaseItems` — modos `append`/`replace`, detecção de duplicidade por `filename` (inclusive duplicidade dentro do próprio lote), `DuplicateConflictError` com lista de conflitos.
- [X] T007 `UpdateTenantKnowledgeBaseItemContent`, `ReplaceTenantKnowledgeBaseItemFile`, `DeleteTenantKnowledgeBaseItem`.
- [X] T008 `ReindexTenantKnowledgeBaseItem` — reindex escopado a um `item_id`.

## Phase 4: Infrastructure
- [X] T009 `postgres_knowledge_base_items_repository.py` — CRUD sobre `tenant_knowledge_base_items`, sempre filtrando por `(tenant_id, id)`.
- [X] T010 `file_text_extractor_adapter.py` — reaproveita `protocols/file_data_reader.py` (pypdf/pandas), adaptado para receber `BinaryIO`/`UploadFile.file`; `protocols/file_data_reader.py` refatorado para expor `extract_text_from_pdf`/`extract_text_from_table`/`extract_text_from_txt` reaproveitáveis (sem duplicar a lógica de parsing).
- [X] T011 Estendido `gerenciador_vetores.py`/`pgvector_knowledge_base_adapter.py` — metadado `item_id` nos chunks, `deletar_por_item`, `reindex_item`/`delete_item`.
- [X] T012 `postgres_knowledge_base_repository.py` (agregado) reescrito para ler/escrever via `tenant_knowledge_base_items` (concatenação dos itens), preservando o contrato de `GET/PUT/DELETE /tenants/{tenant_id}/knowledge-base`.

## Phase 5: API
- [X] T013 `app/schemas/knowledge_base.py` — novos schemas (`KnowledgeBaseItemResponse`, `KnowledgeBaseItemDetailResponse`, `KnowledgeBaseItemUpdateRequest`, `KnowledgeBaseIngestResponse`, `KnowledgeBaseItemSummary`, `DuplicateResolutionRequest`, `DuplicateConflictResponse`).
- [X] T014 `app/api/v1/endpoints/knowledge_base.py` — `GET/POST /items`, `GET/PUT/DELETE /items/{item_id}`, `PUT /items/{item_id}/file`. Router já registrado em `app/main.py` (mesmo objeto `router`, sem mudança necessária).

## Phase 6: Testes
- [X] T015 `tests/unit/knowledge_base/test_ingest_tenant_knowledge_base_items.py`
- [X] T016 `tests/unit/knowledge_base/test_update_and_delete_knowledge_base_item.py`
- [X] T017 `tests/unit/test_file_text_extractor_adapter.py`
- [X] T018 `tests/integration/test_tenant_knowledge_base_items_api.py` — happy path, isolamento entre tenants, 409 duplicidade (com e sem resolução), 422 payload inválido/extensão não suportada, preview de 1000 caracteres.
  - Nota: a regressão do `GET/DELETE` agregado (`/tenants/{tenant_id}/knowledge-base`) sobre a tabela nova não tem teste automatizado com Postgres real neste repo (nenhum teste existente aqui sobe banco de verdade — todos usam fakes injetados via `dependency_overrides`, mesmo padrão de `tests/integration/test_tenant_knowledge_base_api.py`). Verificação fica no Test Guide manual (curl) do fechamento do ticket.

## Phase 7: Fechamento
- [X] T019 Test Guide entregue ao usuário na resposta de fechamento (comando de teste automatizado + roteiro manual via curl), conforme MANDATORY rule 1 e Test Guide do CLAUDE.md.

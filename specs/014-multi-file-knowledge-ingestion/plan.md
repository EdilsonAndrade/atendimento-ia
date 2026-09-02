# Implementation Plan: Ingestão de Dados por Múltiplos Arquivos

**Branch**: `edilsonaandrade/edi-39-permitir-ingestao-de-dados-por-multiplos-arquivos` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/014-multi-file-knowledge-ingestion/spec.md`

## Summary

Backend-only (Princípio II — este repo não tem UI). Evolui `modules/knowledge_base` (já em Clean Architecture, criado na feature 001) de "um `content` de texto por tenant" para "N `KnowledgeBaseItem`s por tenant" (arquivo PDF/XLS/CSV ou texto colado). Nova tabela `tenant_knowledge_base_items` substitui `tenant_knowledge_base` como fonte de verdade; o endpoint agregado atual (`GET/DELETE /tenants/{tenant_id}/knowledge-base`) é preservado sem quebra de contrato, agora lendo/derivando de `tenant_knowledge_base_items`. A extração de PDF/XLS/CSV reaproveita a lógica já existente em `protocols/file_data_reader.py`, adaptada para `UploadFile` em vez de pasta em disco. O reindex vetorial (`PgVectorKnowledgeBaseAdapter`) ganha granularidade por item via metadado `item_id`, para editar/substituir/excluir um item sem afetar os vetores dos demais.

## Technical Context

**Language/Version**: Python 3.11+, FastAPI, psycopg3, Pydantic v2
**Storage**: PostgreSQL via Alembic (nova migration `migrations/versions/0011_tenant_kb_items.py`) + pgvector (`langchain_pg_embedding`, coleção `interasis_knowledge`)
**Parsing reaproveitado**: `protocols/file_data_reader.py` (pypdf + pandas) — adaptado para receber `UploadFile.file` em vez de `pasta_origem`
**Padrão de referência**: `modules/knowledge_base/` (Domain/Application/Infrastructure já existentes na feature 001) e `modules/system_prompts/` (repositório + service, feature 013)
**Project Type**: Serviço web (FastAPI backend) — sem UI neste repositório

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Multi-Tenant Isolation**: todo endpoint de item exige `tenant_id` no path; todo `SELECT/UPDATE/DELETE` de item filtra por `(tenant_id, item_id)` juntos — um `item_id` de outro tenant retorna 404, nunca vaza dado nem erro diferenciado. Vetores continuam isolados por `tenant_id` no metadado, com `item_id` como granularidade adicional dentro do mesmo tenant. ✅
- **II. API-First, Backend-Only**: nenhuma UI é criada neste repositório; a spec já documenta o contrato REST completo para o consumidor (Painel Admin). ✅
- **III. Modular Clean Architecture**: `modules/knowledge_base` já segue Domain/Application/Infrastructure/Interface (feature 001) — este trabalho ADICIONA `KnowledgeBaseItem` (Domain), novos use cases (Application) e um novo repositório/adapter (Infrastructure) na mesma estrutura, sem introduzir SQL ou regra de negócio no endpoint. ✅ NON-NEGOTIABLE, respeitado desde o desenho.
- **IV. Security & Guardrails**: sem mudança de guardrails de IA; a única superfície nova é upload de arquivo — validação de extensão/tamanho acontece na Interface antes de qualquer parsing. ✅
- **V. Async Processing**: toda revetorização (criação, edição, substituição, exclusão de item) roda em `BackgroundTasks`, nunca no caminho síncrono — mesmo padrão já usado por `ReindexTenantKnowledgeBase`. ✅ A extração de texto do arquivo (pypdf/pandas, não geração de embeddings) roda de forma síncrona antes de persistir o item — mesmo padrão já aceito hoje pelo `PUT /tenants/{tenant_id}/knowledge-base` (que valida/grava o `content` de forma síncrona, só a revetorização é assíncrona) e necessário aqui porque a API precisa do texto extraído já na resposta (detecção de duplicidade, `content` retornado). Bounded pelo limite de 10MB/arquivo (ver Assumptions do spec) para manter essa etapa rápida.
- **VI. Test-First Discipline**: cada use case novo ganha teste unitário (fakes de repositório/vector store) + os endpoints novos ganham teste de integração (happy path, isolamento entre tenants, erro de validação) em `tests/integration/`. ✅ planejado na seção Testes abaixo.

Nenhuma violação a justificar em Complexity Tracking.

## Design

### Migration `0011_tenant_kb_items` (revision id com 20 caracteres, dentro do limite de 32 da coluna `alembic_version.version_num`)

```sql
CREATE TABLE public.tenant_knowledge_base_items (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id text NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    source_type text NOT NULL CHECK (source_type IN ('file', 'texto')),
    filename text NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_tenant_kb_items_tenant_id ON public.tenant_knowledge_base_items (tenant_id);
```

A migration faz backfill: para cada linha existente em `tenant_knowledge_base`, cria 1 item (`source_type='texto'`, `filename=NULL`, `content=content` antigo), preservando o conteúdo já ingerido por qualquer tenant hoje. Como `PostgresKnowledgeBaseRepository` (a única leitora/escritora da tabela antiga) passa a operar inteiramente sobre `tenant_knowledge_base_items`, a tabela `tenant_knowledge_base` fica sem nenhum código que a use — a migration a **remove** (`DROP TABLE`) logo após o backfill, evitando schema morto. `downgrade()` reverte: recria `tenant_knowledge_base`, faz backfill inverso (1 linha por tenant, `content` = concatenação dos itens daquele tenant) e dropa `tenant_knowledge_base_items`.

### Domain (`modules/knowledge_base/domain/`)

- `knowledge_base_item.py` (novo): `@dataclass(frozen=True) KnowledgeBaseItem { id, tenant_id, source_type: Literal["file","texto"], filename: str | None, content: str, created_at, updated_at }`, com `validate_content` reaproveitando a mesma regra de "não vazio" já usada por `KnowledgeBaseDocument`.
- Erros novos: `UnsupportedFileTypeError`, `DuplicateFilenameError` (framework-free, levantados pela Application e traduzidos para HTTP na Interface).

### Application (`modules/knowledge_base/application/`)

Novos use cases, cada um dependendo só de ports (testáveis com fakes):

- `ListTenantKnowledgeBaseItems.execute(tenant_id) -> list[KnowledgeBaseItem]`
- `GetTenantKnowledgeBaseItem.execute(tenant_id, item_id) -> KnowledgeBaseItem | None`
- `IngestKnowledgeBaseItems.execute(tenant_id, extracted_items: list[NewItemInput], mode: Literal["append","replace"], duplicate_resolutions: list[DuplicateResolution]) -> IngestResult` — regra central:
  - `mode="replace"`: apaga todos os itens do tenant, cria os novos.
  - `mode="append"`: para cada novo item de arquivo, verifica colisão de `filename` contra itens existentes do tenant; sem resolução informada → acumula em `conflicts` (não persiste nada daquele lote parcialmente — ver Edge Cases); com resolução `"replace"` → atualiza o item existente; com `"keep_both"` → cria novo item mesmo com nome repetido.
  - Levanta `DuplicateConflictError(conflicts)` quando há conflitos sem resolução — a Interface traduz para 409.
- `UpdateTenantKnowledgeBaseItemContent.execute(tenant_id, item_id, content) -> KnowledgeBaseItem` — edição manual (US4).
- `ReplaceTenantKnowledgeBaseItemFile.execute(tenant_id, item_id, extracted: NewItemInput) -> KnowledgeBaseItem` — "enviar outro por cima" (US5).
- `DeleteTenantKnowledgeBaseItem.execute(tenant_id, item_id) -> bool` (US6).
- `ReindexTenantKnowledgeBaseItem` (novo, ao lado do já existente `ReindexTenantKnowledgeBase`): dispara reindexação escopada a um `item_id`.

Novo port em `ports.py`: `FileTextExtractorPort.extract(upload: BinaryIO, filename: str) -> str`, implementado na Infrastructure por um adapter que envolve a lógica hoje em `protocols/file_data_reader.py` (reaproveitada, não duplicada) — a Application nunca importa `pypdf`/`pandas` diretamente.

### Infrastructure (`modules/knowledge_base/infrastructure/`)

- `postgres_knowledge_base_items_repository.py`: CRUD sobre `tenant_knowledge_base_items`, sempre filtrando por `(tenant_id, id)` nas operações de item único (Princípio I).
- `file_text_extractor_adapter.py`: implementa `FileTextExtractorPort` chamando as funções de extração já existentes (refatoradas de `protocols/file_data_reader.py` para aceitar um `BinaryIO`/`UploadFile.file` além de caminho em disco — sem duplicar a lógica de parsing de PDF/XLS/CSV).
- `pgvector_knowledge_base_adapter.py` (existente, estendido): `criar_banco_com_textos`/`GerenciadorVetores` passam a receber `item_id` e gravá-lo em `cmetadata`; novo método `deletar_por_item(tenant_id, item_id)` (`DELETE ... WHERE cmetadata->>'item_id' = %s AND cmetadata->>'tenant_id' = %s`); `reindex_item(tenant_id, item_id, content)` = deletar_por_item + inserir. O `reindex(tenant_id, content)` existente (usado pelo endpoint agregado) continua funcionando para o caso "substituir tudo".

### Interface (`app/api/v1/endpoints/knowledge_base.py`, `app/schemas/knowledge_base.py`)

Endpoints novos (contrato já validado com o time de front no ticket EDI-39):

1. `GET /api/v1/tenants/{tenant_id}/knowledge-base/items` — lista com `content_preview` (1000 chars).
2. `GET /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}` — conteúdo completo.
3. `POST /api/v1/tenants/{tenant_id}/knowledge-base/items` — `multipart/form-data` (`files`, `texts`, `mode`, `duplicate_resolutions`); 201 sucesso, 409 conflito de nome, 422 payload inválido.
4. `PUT /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}` — edição manual do texto (`{"content": str}`).
5. `PUT /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}/file` — substitui o arquivo de um item.
6. `DELETE /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}` — exclui um item.

Endpoints existentes (contrato preservado, implementação realocada para ler/escrever via itens):

7. `GET /api/v1/tenants/{tenant_id}/knowledge-base` — `content` = concatenação (`"\n\n".join`) dos itens do tenant em ordem de criação.
8. `DELETE /api/v1/tenants/{tenant_id}/knowledge-base` — apaga todos os itens do tenant (equivalente a "substituir tudo" por nada).
9. `PUT /api/v1/tenants/{tenant_id}/knowledge-base` (existente) — mantido como está, mas passa a ser tratado como um caso particular: substitui todos os itens por um único item de texto (`mode=replace` com 1 texto). Não removido, para não quebrar nenhum consumidor atual que ainda use só o texto agregado.

Schemas Pydantic novos em `app/schemas/knowledge_base.py`: `KnowledgeBaseItemResponse`, `KnowledgeBaseItemDetailResponse`, `KnowledgeBaseItemUpdateRequest`, `KnowledgeBaseIngestResponse`, `DuplicateResolutionRequest`, `DuplicateConflictResponse`.

## Testes

- `tests/unit/knowledge_base/test_ingest_tenant_knowledge_base_items.py` — modo append/replace, detecção de duplicidade (com/sem resolução), erro de conteúdo vazio.
- `tests/unit/knowledge_base/test_update_and_delete_knowledge_base_item.py` — edição, substituição de arquivo, exclusão individual (fakes de repositório e vector store).
- `tests/unit/test_file_text_extractor_adapter.py` — extração de `.pdf`/`.xls`/`.xlsx`/`.csv` a partir de `UploadFile`, extensão não suportada.
- `tests/integration/test_tenant_knowledge_base_items_api.py` — happy path de todos os 6 endpoints novos; isolamento entre tenants (item de um tenant não é acessível/editável/excluível via `tenant_id` de outro); 409 de duplicidade; 422 de payload inválido; `GET/DELETE /knowledge-base` (agregado) continuam passando após a migração de dados.

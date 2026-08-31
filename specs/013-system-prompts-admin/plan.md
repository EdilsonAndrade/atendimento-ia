# Implementation Plan: Painel Admin — Prompts do Sistema

**Branch**: `013-system-prompts-admin` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/013-system-prompts-admin/spec.md`

## Summary

Backend-only (este repo não tem UI — Principle II do projeto). Nova tabela `system_prompts` (colunas `current_version`/`last_version`) para os 4 prompts hoje hardcoded em `modules/ia/agent_graph.py`. Endpoints REST para listar, editar (com versionamento automático) e fazer rollback. `agent_graph.py` passa a ler do banco a cada turno via um novo módulo `prompts/system_prompt_loader.py`, com fallback para o texto hardcoded local em caso de falha de infraestrutura — mesmo padrão já usado por `prompts/load_prompt.py` para os prompts por tenant.

## Technical Context

**Language/Version**: Python 3.11+, FastAPI, psycopg3
**Storage**: PostgreSQL via Alembic migration (`migrations/versions/0010_system_prompts.py`)
**Padrão de referência**: `modules/prompt_manager/` (repository/service) e `prompts/load_prompt.py` (fallback local em caso de erro de infraestrutura)
**Project Type**: Serviço web (FastAPI backend) — sem UI neste repositório

## Design

### Tabela `system_prompts`
```
id              uuid PK default uuid_generate_v4()
prompt_key      text UNIQUE NOT NULL  -- routing_agent | groundedness_rule | chitchat_no_knowledge_rule | booking_integrity_rule
titulo          text NOT NULL         -- nome de exibição (nome da constante/função em agent_graph.py)
current_version text NOT NULL
last_version    text NOT NULL
created_at      timestamptz NOT NULL DEFAULT NOW()
updated_at      timestamptz NOT NULL DEFAULT NOW()
```
Migration faz seed com o conteúdo hardcoded atual (current_version = last_version) para os 4 `prompt_key`s — nunca há rollback para versão nula (FR-002).

### Módulos novos
- `modules/system_prompts/system_prompts_repository.py` — acesso a dados (get_all, get_by_key, update_current_version, rollback).
- `modules/system_prompts/system_prompts_service.py` — regras (validação de conteúdo vazio, `PromptKeyNotFoundError`).
- `app/schemas/system_prompts.py` — schemas Pydantic (request/response).
- `app/api/v1/endpoints/system_prompts.py` — router `/system-prompts`.
- `prompts/system_prompt_loader.py` — funções chamadas pelo runtime do agente (`carregar_groundedness_rule()`, `carregar_chitchat_no_knowledge_rule()`, `carregar_booking_integrity_rule()`, `carregar_routing_agent_template()`), cada uma tentando o banco e caindo no texto hardcoded local (mantido como constante `_FALLBACK_*` no próprio loader) em caso de exceção.

### Mudança em `modules/ia/agent_graph.py`
- `GROUNDEDNESS_RULE`, `CHITCHAT_NO_KNOWLEDGE_RULE`, `BOOKING_INTEGRITY_RULE` deixam de ser usadas diretamente nos nós; cada ponto de uso passa a chamar a função loader correspondente.
- O prompt do `routing_agent` (hoje uma string grande montada inline) vira um template com placeholder `{previous_turn_intent}`, carregado via `carregar_routing_agent_template()` e renderizado com `.format_map` tolerante a chaves desconhecidas (mesma técnica de `_render_prompt` em `prompts/load_prompt.py`, reimplementada localmente no loader para não acoplar aos tipos tenant-scoped de `prompt_resolver.py`).
- As constantes hardcoded viram o fallback local dentro do loader (não removidas — fora de escopo remover fallback).

### Endpoints (contrato para o front-end)
- `GET /api/v1/system-prompts` — lista os 4 prompts.
- `GET /api/v1/system-prompts/{prompt_key}` — detalhe de um prompt.
- `PUT /api/v1/system-prompts/{prompt_key}` — body `{"conteudo": str}` → grava nova `current_version`, desloca a anterior para `last_version`. 400 se `conteudo` vazio/blank.
- `POST /api/v1/system-prompts/{prompt_key}/rollback` — troca `current_version` ↔ `last_version`.
- 404 com `prompt_key` inexistente (os 4 chaves são fixas, sem POST de criação).

## Testes
- `tests/unit/test_system_prompts_service.py` — validação de conteúdo vazio, rollback.
- `tests/unit/test_system_prompt_loader_fallback.py` — loader cai no fallback local quando o banco lança exceção (mesmo padrão de `tests/unit/test_prompt_manager_fallback.py`).
- `tests/integration/test_system_prompts_api.py` — CRUD + rollback via TestClient.

# Tasks: Painel Admin — Prompts do Sistema

**Input**: plan.md, spec.md
**Tests**: incluídos (unit + integration), conforme padrão do repositório para módulos de prompt.

## Phase 1: Migration & schema
- [X] T001 Migration `migrations/versions/0010_system_prompts.py` — cria `system_prompts` e faz seed com os 4 prompt_keys usando o conteúdo hardcoded atual de `modules/ia/agent_graph.py` (current_version = last_version).

## Phase 2: Módulo de dados
- [X] T002 `modules/system_prompts/system_prompts_repository.py` — get_all, get_by_key, update_current_version (desloca current→last), rollback (swap).
- [X] T003 `modules/system_prompts/system_prompts_service.py` — validação de conteúdo vazio, `PromptKeyNotFoundError`.

## Phase 3: API
- [X] T004 `app/schemas/system_prompts.py` — schemas de request/response.
- [X] T005 `app/api/v1/endpoints/system_prompts.py` — router GET list, GET by key, PUT, POST rollback.
- [X] T006 Registrar router em `app/main.py`.

## Phase 4: Runtime do agente
- [X] T007 `prompts/system_prompt_loader.py` — loaders com fallback local para os 4 prompts, incluindo render do template do routing_agent.
- [X] T008 Atualizar `modules/ia/agent_graph.py` para consumir os loaders nos pontos de uso (routing_agent, operational_node, chitchat_node).

## Phase 5: Testes
- [X] T009 `tests/unit/test_system_prompt_loader_fallback.py`
- [X] T010 `tests/unit/test_system_prompts_service.py`
- [X] T011 `tests/integration/test_system_prompts_api.py`

## Phase 6: Documentação para o front-end
- [X] T012 Resumo de endpoints entregue ao usuário no fechamento do ticket (MANDATORY rule 2 do CLAUDE.md).

from fastapi import APIRouter, HTTPException

from infrastructure.connection import get_db_connection
from modules.system_prompts.system_prompts_service import (
    SystemPromptContentEmptyError,
    SystemPromptNotFoundError,
    SystemPromptsService,
)
from app.schemas.system_prompts import (
    SystemPromptKey,
    SystemPromptResponse,
    SystemPromptUpdateSchema,
)

router = APIRouter(prefix="/system-prompts", tags=["System Prompts"])


@router.get(
    "",
    response_model=list[SystemPromptResponse],
    summary="Lista os prompts de sistema hoje hardcoded em modules/ia/agent_graph.py",
)
def list_system_prompts():
    service = SystemPromptsService(get_db_connection)
    return service.list_prompts()


@router.get(
    "/{prompt_key}",
    response_model=SystemPromptResponse,
    summary="Detalhe de um prompt de sistema (current_version + last_version)",
)
def get_system_prompt(prompt_key: SystemPromptKey):
    service = SystemPromptsService(get_db_connection)
    try:
        return service.get_prompt(prompt_key)
    except SystemPromptNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put(
    "/{prompt_key}",
    response_model=SystemPromptResponse,
    summary="Salva novo conteúdo como current_version, deslocando a versão vigente para last_version",
)
def update_system_prompt(prompt_key: SystemPromptKey, payload: SystemPromptUpdateSchema):
    service = SystemPromptsService(get_db_connection)
    try:
        return service.update_prompt(prompt_key, payload.conteudo)
    except SystemPromptNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SystemPromptContentEmptyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/{prompt_key}/rollback",
    response_model=SystemPromptResponse,
    summary="Troca current_version <-> last_version (reversível)",
)
def rollback_system_prompt(prompt_key: SystemPromptKey):
    service = SystemPromptsService(get_db_connection)
    try:
        return service.rollback_prompt(prompt_key)
    except SystemPromptNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

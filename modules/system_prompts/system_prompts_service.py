from typing import Any, Dict, List

from modules.system_prompts.system_prompts_repository import SystemPromptsRepository


class SystemPromptNotFoundError(Exception):
    code = "SYSTEM_PROMPT_NOT_FOUND"

    def __init__(self, prompt_key: str):
        self.prompt_key = prompt_key
        super().__init__(f"System prompt {prompt_key!r} não encontrado.")


class SystemPromptContentEmptyError(Exception):
    code = "SYSTEM_PROMPT_CONTENT_EMPTY"

    def __init__(self):
        super().__init__("O conteúdo do prompt não pode ser vazio.")


class SystemPromptsService:
    def __init__(self, get_connection_func):
        self.repository = SystemPromptsRepository(get_connection_func)

    def list_prompts(self) -> List[Dict[str, Any]]:
        return self.repository.get_all()

    def get_prompt(self, prompt_key: str) -> Dict[str, Any]:
        prompt = self.repository.get_by_key(prompt_key)
        if not prompt:
            raise SystemPromptNotFoundError(prompt_key)
        return prompt

    def update_prompt(self, prompt_key: str, conteudo: str) -> Dict[str, Any]:
        if not conteudo or not conteudo.strip():
            raise SystemPromptContentEmptyError()

        # Garante 404 (em vez de UPDATE silencioso de 0 linhas) quando o
        # prompt_key não existe — o conjunto de chaves é fixo pela migration.
        self.get_prompt(prompt_key)

        return self.repository.update_current_version(prompt_key, conteudo)

    def rollback_prompt(self, prompt_key: str) -> Dict[str, Any]:
        self.get_prompt(prompt_key)
        return self.repository.rollback(prompt_key)

import pytest

from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository


@pytest.fixture
def repo():
    return PromptManagerRepository(get_db_connection)


class _DbCleanup:
    """Rastreia registros criados por um teste de integração (prompts, guardrails,
    tenants) e apaga tudo ao final — mesmo se o teste falhar num assert — para não
    poluir o banco compartilhado de desenvolvimento."""

    def __init__(self, repo):
        self._repo = repo
        self._tenant_ids = set()
        self._prompt_ids = set()
        self._guardrail_ids = set()

    def track_tenant(self, tenant_id):
        self._tenant_ids.add(tenant_id)
        return tenant_id

    def track_prompt(self, prompt):
        self._prompt_ids.add(prompt["id"] if isinstance(prompt, dict) else prompt)
        return prompt

    def track_guardrail(self, guardrail):
        self._guardrail_ids.add(guardrail["id"] if isinstance(guardrail, dict) else guardrail)
        return guardrail

    def run(self):
        if not (self._tenant_ids or self._prompt_ids or self._guardrail_ids):
            return
        with self._repo.get_connection() as conn:
            with conn.cursor() as cur:
                if self._tenant_ids:
                    cur.execute(
                        "DELETE FROM tenant_prompts WHERE tenant_id = ANY(%s)",
                        (list(self._tenant_ids),),
                    )
                if self._prompt_ids:
                    prompt_ids = list(self._prompt_ids)
                    cur.execute("DELETE FROM tenant_prompts WHERE prompt_id = ANY(%s)", (prompt_ids,))
                    cur.execute("DELETE FROM prompt_guardrails WHERE prompt_id = ANY(%s)", (prompt_ids,))
                    cur.execute("DELETE FROM prompts WHERE id = ANY(%s)", (prompt_ids,))
                if self._guardrail_ids:
                    guardrail_ids = list(self._guardrail_ids)
                    cur.execute("DELETE FROM prompt_guardrails WHERE guardrail_id = ANY(%s)", (guardrail_ids,))
                    cur.execute("DELETE FROM guardrails WHERE id = ANY(%s)", (guardrail_ids,))


@pytest.fixture
def db_cleanup(repo):
    cleanup = _DbCleanup(repo)
    yield cleanup
    cleanup.run()

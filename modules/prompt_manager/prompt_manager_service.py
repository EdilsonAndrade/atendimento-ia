from typing import Any, Dict, List, Optional
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository


class DefaultPromptNotConfiguredError(Exception):
    """Levantada quando um tenant não tem vínculo ativo e não existe nenhum
    prompt marcado como is_default=TRUE para servir de fallback."""


class PromptManagerService:
    def __init__(self, get_connection_func):
        self.repository = PromptManagerRepository(get_connection_func)

    def list_guardrails(self):
        return self.repository.get_all_guardrails()

    def create_guardrail(self, titulo: str, conteudo: str, is_global: bool = False):
        return self.repository.create_guardrail(titulo, conteudo, is_global)

    def list_prompts(self):
        return self.repository.get_all_prompts()

    def create_prompt_with_relations(
        self, 
        titulo: str, 
        conteudo: str, 
        is_default: bool, 
        guardrail_ids: List[str]
    ):
        prompt = self.repository.create_prompt(titulo, conteudo, is_default)
        if guardrail_ids:
            self.repository.sync_prompt_guardrails(prompt["id"], guardrail_ids)
        return prompt

    def link_tenant_to_prompt(self, tenant_id: str, prompt_id: str, custom_override: Optional[str] = None):
        self.repository.sync_tenant_prompt(tenant_id, prompt_id, custom_override)
        return {"status": "success", "message": f"Tenant {tenant_id} vinculado ao prompt {prompt_id}"}

    def build_system_prompt_for_tenant(self, tenant_id: str, fallback_prompt_str: str, **kwargs) -> str:
        """
        Monta o prompt para o runtime do Agente:
        1. Se existir vínculo no banco para o tenant, pega o prompt e seus guardrails da N:N.
        2. Se NÃO existir vínculo no banco, usa a string do prompt local que você passar como fallback.
        """
        active_prompt_data = self.repository.get_active_prompt_by_tenant(tenant_id)

        if active_prompt_data:
            prompt_template = active_prompt_data["conteudo"]
            prompt_id = active_prompt_data["id"]
            
            # Carrega apenas os guardrails explicitamente vinculados na tabela N:N
            guardrails_list = self.repository.get_guardrails_by_prompt(prompt_id)
            guardrails_str = "\n\n".join([g["conteudo"] for g in guardrails_list])
        else:
            # Fallback para o prompt local
            prompt_template = fallback_prompt_str
            guardrails_str = ""

        # Formatação das variáveis do prompt
        return prompt_template.format(
            tenant_id=tenant_id,
            guardrails=guardrails_str,
            **kwargs
        )
        
    def delete_prompt(self, prompt_id: str) -> bool:
        return self.repository.delete_prompt(prompt_id)

    def update_prompt_with_relations(
        self, 
        prompt_id: str,
        titulo: str, 
        conteudo: str, 
        is_default: bool, 
        guardrail_ids: List[str]
    ):
        prompt = self.repository.update_prompt(prompt_id, titulo, conteudo, is_default)
        if not prompt:
            return None
        
        # Re-sincroniza as associações N:N na tabela prompt_guardrails
        self.repository.sync_prompt_guardrails(prompt_id, guardrail_ids)
        return prompt

    def get_tenant_prompt_details(self, tenant_id: str) -> Dict[str, Any]:
        """Retorna o prompt + guardrails do tenant para exibição no Painel Administrador.

        Se o tenant tiver um vínculo ativo em tenant_prompts, retorna esse prompt
        personalizado. Caso contrário, cai no prompt padrão (is_default=TRUE) e nos
        guardrails globais — nunca retorna vazio silenciosamente nem 404 por falta
        de personalização (essa decisão é responsabilidade do endpoint, que checa a
        existência do tenant antes de chamar este método).
        """
        details = self.repository.get_tenant_prompt_details(tenant_id)
        if details:
            return {
                "tenant_id": details["tenant_id"],
                "prompt_id": str(details["prompt_id"]),
                "prompt_titulo": details["prompt_titulo"],
                "prompt_conteudo": details["prompt_conteudo_base"],
                "custom_content_override": details["custom_content_override"],
                "is_default_prompt": False,
                "guardrails_associados": self._stringify_guardrail_ids(details["guardrails_associados"]),
            }

        default_prompt = self.repository.get_default_prompt()
        if not default_prompt:
            raise DefaultPromptNotConfiguredError(
                "Nenhum prompt padrão (is_default=TRUE) está configurado."
            )

        return {
            "tenant_id": tenant_id,
            "prompt_id": str(default_prompt["id"]),
            "prompt_titulo": default_prompt["titulo"],
            "prompt_conteudo": default_prompt["conteudo"],
            "custom_content_override": None,
            "is_default_prompt": True,
            "guardrails_associados": self._stringify_guardrail_ids(self.repository.get_global_guardrails()),
        }

    @staticmethod
    def _stringify_guardrail_ids(guardrails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # O driver do Postgres devolve `id` como uuid.UUID; a API expõe ids como string.
        return [{**guardrail, "id": str(guardrail["id"])} for guardrail in guardrails]
from typing import Any, Dict, List, Optional
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository


class DefaultPromptNotConfiguredError(Exception):
    """Levantada quando um tenant não tem vínculo ativo e não existe nenhum
    prompt marcado como is_default=TRUE para servir de fallback."""


class ResourceInUseError(Exception):
    """Base das recusas de exclusão do EDI-43.

    Carrega os `blockers` — os itens que impedem a operação — para o endpoint
    devolvê-los ao frontend. Sem eles o admin veria apenas 'não é possível' e
    teria que descobrir sozinho o que desfazer primeiro.
    """

    code = "RESOURCE_IN_USE"

    def __init__(self, message: str, blockers: Optional[List[Dict[str, Any]]] = None):
        self.blockers = blockers or []
        super().__init__(message)


class PromptInUseByTenantsError(ResourceInUseError):
    code = "PROMPT_IN_USE_BY_TENANTS"


class GuardrailIsGlobalError(ResourceInUseError):
    code = "GUARDRAIL_IS_GLOBAL"


class GuardrailInUseByTenantsError(ResourceInUseError):
    code = "GUARDRAIL_IN_USE_BY_TENANTS"


class PromptNotFoundError(Exception):
    code = "PROMPT_NOT_FOUND"

    def __init__(self, prompt_id: str):
        self.prompt_id = prompt_id
        super().__init__(f"Prompt {prompt_id!r} não encontrado.")


class TenantsNotFoundError(Exception):
    code = "TENANT_NOT_FOUND"

    def __init__(self, tenant_ids: List[str]):
        self.tenant_ids = tenant_ids
        self.blockers = [{"type": "tenant", "id": tid} for tid in tenant_ids]
        super().__init__(
            f"{len(tenant_ids)} tenants informados não existem. Nenhum vínculo foi aplicado."
        )


class PromptManagerService:
    def __init__(self, get_connection_func):
        self.repository = PromptManagerRepository(get_connection_func)

    def list_guardrails(self):
        return self.repository.get_all_guardrails()

    def create_guardrail(self, titulo: str, conteudo: str, is_global: bool = False):
        return self.repository.create_guardrail(titulo, conteudo, is_global)

    def delete_guardrail(self, guardrail_id: str) -> bool:
        """Recusa a exclusão de um guardrail global ou em uso (FR-023/FR-024/FR-025).

        O teste de `is_global` é indispensável e vem PRIMEIRO. Um guardrail global
        não tem linha em prompt_guardrails — ele alcança os tenants pela cláusula
        `WHERE g.is_global = TRUE`. Um critério baseado só em associação deixaria
        justamente o guardrail que protege todos como o mais fácil de apagar.

        A precedência do global também é prática: enquanto ele for global,
        desassociá-lo dos prompts não muda nada, porque o alcance independe da
        associação. Então esse é o passo que o admin precisa dar primeiro.
        """
        guardrail = self.repository.get_guardrail_by_id(guardrail_id)
        if not guardrail:
            return False

        if guardrail["is_global"]:
            raise GuardrailIsGlobalError(
                "Este guardrail é global e se aplica a todos os tenants. "
                "Desmarque 'global' antes de excluir."
            )

        blockers = self.repository.get_prompts_blocking_guardrail(guardrail_id)
        if blockers:
            raise GuardrailInUseByTenantsError(
                f"Este guardrail está associado a {len(blockers)} prompt(s) em uso por tenants. "
                "Remova a associação antes de excluir.",
                blockers=[
                    {
                        "type": "prompt",
                        "id": str(b["id"]),
                        "name": b["name"],
                        "tenant_count": b["tenant_count"],
                    }
                    for b in blockers
                ],
            )

        return self.repository.delete_guardrail(guardrail_id)

    def list_prompts(self, node_type: Optional[str] = None):
        return self.repository.get_all_prompts(node_type=node_type)

    def create_prompt_with_relations(
        self,
        titulo: str,
        conteudo: str,
        is_default: bool,
        guardrail_ids: List[str],
        node_type: str = "operational",
    ):
        prompt = self.repository.create_prompt(titulo, conteudo, is_default, node_type=node_type)
        if guardrail_ids:
            self.repository.sync_prompt_guardrails(prompt["id"], guardrail_ids)
        return prompt

    def link_tenant_to_prompt(self, tenant_id: str, prompt_id: str, custom_override: Optional[str] = None):
        self.repository.sync_tenant_prompt(tenant_id, prompt_id, custom_override)

    def list_tenants_by_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """Tenants atualmente vinculados a um prompt (EDI-44).

        Sustenta a tela de associação em massa: antes de aplicar um prompt a N
        tenants, o admin precisa ver quem já o usa. É a mesma informação que
        aparece nos `blockers` do 409 de exclusão, disponibilizada sem exigir que
        o admin tente excluir para descobrir.
        """
        prompt = self.repository.get_prompt_by_id(prompt_id)
        if not prompt:
            raise PromptNotFoundError(prompt_id)

        tenants = self.repository.get_tenants_by_prompt(prompt_id)

        return {
            "prompt_id": str(prompt["id"]),
            "prompt_titulo": prompt["titulo"],
            "node_type": prompt["node_type"],
            "tenant_count": len(tenants),
            "tenants": [{"id": str(t["id"]), "name": t["name"]} for t in tenants],
        }

    def link_tenants_bulk(
        self, prompt_id: str, tenant_ids: List[str], custom_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Associa um prompt a vários tenants numa única operação (FR-019).

        Valida tudo ANTES de escrever: prompt existe, e todos os tenants existem.
        A alternativa — aplicar o que der e reportar o resto — deixaria o admin
        com um estado parcial que ele não pediu e teria que auditar manualmente.
        """
        prompt = self.repository.get_prompt_by_id(prompt_id)
        if not prompt:
            raise PromptNotFoundError(prompt_id)

        existentes = set(self.repository.get_existing_tenant_ids(tenant_ids))
        faltantes = [tid for tid in tenant_ids if tid not in existentes]
        if faltantes:
            raise TenantsNotFoundError(faltantes)

        self.repository.link_tenants_bulk(prompt_id, tenant_ids, custom_override)

        return {
            "prompt_id": str(prompt["id"]),
            "node_type": prompt["node_type"],
            "linked_count": len(tenant_ids),
            "tenant_ids": list(tenant_ids),
        }
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
        """Recusa a exclusão de um prompt com vínculo ativo (FR-022).

        Antes, delete_prompt apagava tenant_prompts em cascata: excluir um prompt
        usado por 10 tenants deixava os 10 órfãos, em silêncio. Era o buraco que
        reabria o invariante fechado pelo cadastro obrigatório e pelo backfill.
        """
        blockers = self.repository.get_tenants_blocking_prompt(prompt_id)
        if blockers:
            raise PromptInUseByTenantsError(
                f"Este prompt está em uso por {len(blockers)} tenant(s) e não pode ser excluído. "
                "Vincule outro prompt a esses tenants antes de excluir.",
                blockers=[
                    {"type": "tenant", "id": str(b["id"]), "name": b["name"]} for b in blockers
                ],
            )
        return self.repository.delete_prompt(prompt_id)

    def update_prompt_with_relations(
        self,
        prompt_id: str,
        titulo: str,
        conteudo: str,
        is_default: bool,
        guardrail_ids: List[str],
        node_type: str = "operational",
    ):
        prompt = self.repository.update_prompt(prompt_id, titulo, conteudo, is_default, node_type=node_type)
        if not prompt:
            return None

        # Re-sincroniza as associações N:N na tabela prompt_guardrails
        self.repository.sync_prompt_guardrails(prompt_id, guardrail_ids)
        return prompt

    def get_tenant_prompt_details(self, tenant_id: str, node_type: str = "operational") -> Dict[str, Any]:
        """Retorna o prompt + guardrails do tenant, para o node_type pedido, para exibição
        no Painel Administrador.

        Cadeia de resolução (ver data-model.md):
        1. Vínculo ativo do tenant nesse node_type → retorna esse prompt personalizado.
        2. Sem vínculo e node_type='institutional' → cai no resultado já resolvido do
           operational_node desse tenant (FR-004), preservando node_type='institutional' na resposta.
        3. Sem vínculo (operational ou chitchat) → cai no prompt is_default=TRUE desse node_type
           + guardrails globais.

        Nunca retorna vazio silenciosamente nem 404 por falta de personalização (essa decisão é
        responsabilidade do endpoint, que checa a existência do tenant antes de chamar este método).
        """
        details = self.repository.get_tenant_prompt_details(tenant_id, node_type=node_type)
        if details:
            return {
                "tenant_id": details["tenant_id"],
                "node_type": node_type,
                "prompt_id": str(details["prompt_id"]),
                "prompt_titulo": details["prompt_titulo"],
                "prompt_conteudo": details["prompt_conteudo_base"],
                "custom_content_override": details["custom_content_override"],
                "is_default_prompt": False,
                "is_active": details["is_active"],
                "guardrails_associados": self._stringify_guardrail_ids(details["guardrails_associados"]),
            }

        if node_type == "institutional":
            # FR-004: sem vínculo institucional próprio, usa a resolução completa do operational_node
            fallback = self.get_tenant_prompt_details(tenant_id, node_type="operational")
            return {**fallback, "node_type": "institutional"}

        default_prompt = self.repository.get_default_prompt(node_type=node_type)
        if not default_prompt:
            raise DefaultPromptNotConfiguredError(
                f"Nenhum prompt padrão (is_default=TRUE) está configurado para o nó '{node_type}'."
            )

        return {
            "tenant_id": tenant_id,
            "node_type": node_type,
            "prompt_id": str(default_prompt["id"]),
            "prompt_titulo": default_prompt["titulo"],
            "prompt_conteudo": default_prompt["conteudo"],
            "custom_content_override": None,
            "is_default_prompt": True,
            "is_active": True,
            "guardrails_associados": self._stringify_guardrail_ids(self.repository.get_global_guardrails()),
        }

    @staticmethod
    def _stringify_guardrail_ids(guardrails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # O driver do Postgres devolve `id` como uuid.UUID; a API expõe ids como string.
        return [{**guardrail, "id": str(guardrail["id"])} for guardrail in guardrails]
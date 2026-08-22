import contextlib
from typing import Any, Dict, List, Optional

from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository
from modules.tenant.tenant_repository import TenantRepository


class PromptNotFoundError(Exception):
    """O prompt informado no cadastro do tenant não existe."""

    def __init__(self, prompt_id: str):
        self.prompt_id = prompt_id
        super().__init__(f"Prompt {prompt_id!r} não encontrado.")


class PromptNodeTypeInvalidError(Exception):
    """O prompt existe, mas não é do node_type exigido pelo cadastro."""

    def __init__(self, prompt_id: str, node_type: str, esperado: str = "operational"):
        self.prompt_id = prompt_id
        self.node_type = node_type
        self.esperado = esperado
        super().__init__(
            f"O prompt informado é do tipo {node_type!r}. "
            f"O cadastro de tenant exige um prompt do tipo {esperado!r}."
        )


class TenantService:
    def __init__(self):
        self.tenant_repository = TenantRepository()
        self.prompt_repository = PromptManagerRepository(get_db_connection)

    def create_tenant(self, tenant_data: dict) -> dict:
        """Cria o tenant exigindo o vínculo com um prompt operacional (EDI-43).

        A validação do prompt vem ANTES de qualquer escrita: assim os dois erros
        comuns (prompt inexistente, node_type errado) nunca deixam resíduo no
        banco. A criação em si é atômica no repositório.
        """
        prompt_id = tenant_data["prompt_id"]
        prompt = self.prompt_repository.get_prompt_by_id(prompt_id)

        if not prompt:
            raise PromptNotFoundError(prompt_id)

        if prompt["node_type"] != "operational":
            raise PromptNodeTypeInvalidError(prompt_id, prompt["node_type"])

        return self.tenant_repository.create_tenant_with_prompt(tenant_data, prompt_id)

    def get_tenant(self, tenant_id: str) -> dict | None:
        # Logic to retrieve a tenant by ID using the repository
        return self.tenant_repository.get_tenant(tenant_id)

    def get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Alias for get_tenant — used by Google Calendar tools."""
        return self.get_tenant(tenant_id)

    def search_tenants(self, term: str, limit: int = 20) -> list:
        """`GET /tenants` original (EDI-43 e anteriores) — array puro, sem
        paginação nem tags. Não tocar: é consumido hoje pela busca de tenant
        da Base de Conhecimento (`searchTenants`/`useTenantSearch` no front)."""
        return self.tenant_repository.list_tenants(term, limit, offset=0)

    def list_tenants(
        self, term: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        """Lista tenants paginada, com as tags de prompt/guardrail já embutidas
        (grid da tela de Tenants, EDI-46) — evita o front ter que chamar
        `GET /prompt-manager/tenant/{id}` uma vez por linha.

        Sem `term`, devolve a listagem completa (ordenada por nome). O custo é
        1 query de página + 1 de contagem + 1 por tenant (prompts ativos) + 1
        por prompt ativo (guardrails do prompt) — aceitável para uma tela
        administrativa paginada (20/página); não vale a complexidade de uma
        única query agregada para este volume.
        """
        tenants = self.tenant_repository.list_tenants(term, limit, offset)
        total = self.tenant_repository.count_tenants(term)

        items = []
        for tenant in tenants:
            prompts = [
                {**p, "id": str(p["id"])}
                for p in self.prompt_repository.get_prompts_linked_to_tenant_active(tenant["id"])
            ]
            guardrails: Dict[str, Dict[str, Any]] = {}
            for prompt in prompts:
                for guardrail in self.prompt_repository.get_guardrail_links_for_prompt(prompt["id"]):
                    guardrail_id = str(guardrail["id"])
                    guardrails[guardrail_id] = {**guardrail, "id": guardrail_id}
            items.append({**tenant, "prompts": prompts, "guardrails": list(guardrails.values())})

        return {"items": items, "total": total}

    def update_tenant(self, tenant_id: str, tenant_data: dict) -> dict | None:
        # Logic to update an existing tenant using the repository
        return self.tenant_repository.update_tenant(tenant_id, tenant_data)

    # --- EXCLUSÃO EM CASCATA (EDI-45) ---------------------------------------

    def _compute_delete_plan(
        self, tenant_id: str, prompt_repo: PromptManagerRepository
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Decide, para cada prompt/guardrail vinculado ATIVAMENTE ao tenant, se
        deve ser excluído de fato (exclusivo) ou apenas desvinculado
        (compartilhado com outro tenant/prompt, ou global).

        Único lugar onde a regra de negócio mora — tanto `delete_tenant_cascade`
        (escrita) quanto `get_delete_impact` (leitura) chamam esta função, para
        a pré-visualização nunca divergir do resultado real (SC-002).

        `prompt_repo` é recebido já vinculado à conexão certa: a de uma
        transação compartilhada (exclusão de verdade) ou a conexão avulsa
        default de `self.prompt_repository` (pré-visualização, somente leitura).
        """
        active_prompts = prompt_repo.get_prompts_linked_to_tenant_active(tenant_id)

        prompts_to_delete: List[Dict[str, Any]] = []
        prompts_to_unlink_only: List[Dict[str, Any]] = []
        exclusive_prompt_ids: set[str] = set()

        for raw_prompt in active_prompts:
            prompt_id = str(raw_prompt["id"])
            prompt = {**raw_prompt, "id": prompt_id}
            outros_tenants = [
                t
                for t in prompt_repo.get_tenants_blocking_prompt(prompt_id)
                if str(t["id"]) != str(tenant_id)
            ]
            if outros_tenants:
                prompts_to_unlink_only.append(prompt)
            else:
                prompts_to_delete.append(prompt)
                exclusive_prompt_ids.add(prompt_id)

        # Guardrails são avaliados só a partir dos prompts que VÃO ser
        # excluídos — um prompt preservado (compartilhado) continua precisando
        # dos guardrails dele, então nada muda para eles.
        guardrails_to_delete: Dict[str, Dict[str, Any]] = {}
        guardrails_to_unlink_only: Dict[str, Dict[str, Any]] = {}

        for prompt in prompts_to_delete:
            prompt_id = str(prompt["id"])
            for guardrail in prompt_repo.get_guardrail_links_for_prompt(prompt_id):
                guardrail_id = str(guardrail["id"])
                if guardrail_id in guardrails_to_delete or guardrail_id in guardrails_to_unlink_only:
                    continue  # já classificado via outro prompt exclusivo deste mesmo tenant

                if guardrail["is_global"]:
                    guardrails_to_unlink_only[guardrail_id] = {**guardrail, "id": guardrail_id}
                    continue

                # Exclui TODOS os prompts exclusivos deste tenant da checagem —
                # não só o prompt atual. Dois prompts exclusivos do mesmo tenant
                # podem compartilhar um guardrail entre si; nenhum dos dois
                # sobrevive, então o guardrail não pode se apoiar num vizinho
                # que também está prestes a desaparecer.
                outros_prompts = [
                    p
                    for p in prompt_repo.get_prompts_blocking_guardrail(guardrail_id)
                    if str(p["id"]) not in exclusive_prompt_ids
                ]
                if outros_prompts:
                    guardrails_to_unlink_only[guardrail_id] = {**guardrail, "id": guardrail_id}
                else:
                    guardrails_to_delete[guardrail_id] = {**guardrail, "id": guardrail_id}

        return {
            "prompts_to_delete": prompts_to_delete,
            "prompts_to_unlink_only": prompts_to_unlink_only,
            "guardrails_to_delete": list(guardrails_to_delete.values()),
            "guardrails_to_unlink_only": list(guardrails_to_unlink_only.values()),
        }

    def get_delete_impact(self, tenant_id: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Pré-visualização somente-leitura do que `delete_tenant_cascade`
        faria agora. Devolve `None` se o tenant não existir."""
        if self.tenant_repository.get_tenant(tenant_id) is None:
            return None
        return self._compute_delete_plan(tenant_id, self.prompt_repository)

    def delete_tenant_cascade(self, tenant_id: str) -> Optional[str]:
        """Exclui o tenant e, na mesma transação, os prompts/guardrails que só
        pertenciam a ele — preservando os que são compartilhados ou globais
        (EDI-45). Devolve `None` se o tenant não existir (nada é alterado).

        `get_db_connection()` abre conexões com `autocommit=True`; o bloco
        `conn.transaction()` do psycopg3 cria uma transação real por cima disso
        (research.md §3). `PromptManagerRepository` é instanciado sobre a MESMA
        conexão, via uma fábrica que devolve `contextlib.nullcontext(conn)` em
        vez de abrir uma conexão nova a cada chamada — assim os métodos já
        existentes (`delete_prompt`, `delete_guardrail`, os bloqueios de
        exclusão) são reaproveitados sem duplicar SQL nem furar a fronteira
        entre módulos (research.md §4).
        """
        conn = get_db_connection()
        try:
            with conn.transaction():
                shared_prompt_repo = PromptManagerRepository(lambda: contextlib.nullcontext(conn))
                plan = self._compute_delete_plan(tenant_id, shared_prompt_repo)

                for guardrail in plan["guardrails_to_delete"]:
                    shared_prompt_repo.delete_guardrail(str(guardrail["id"]))

                for prompt in plan["prompts_to_delete"]:
                    shared_prompt_repo.delete_prompt(str(prompt["id"]))

                deleted_tenant_id = TenantRepository(connection=conn).delete_tenant(tenant_id)

            return deleted_tenant_id
        finally:
            conn.close()
"""`TenantService.list_tenants` — grid da tela de Tenants (EDI-46).

Endpoint próprio (`GET /tenants/list`), separado de `search_tenants`
(contrato antigo intacto, usado pela Base de Conhecimento). Agrega prompts e
guardrails ativos por tenant via os métodos já existentes do EDI-45.
"""

from modules.tenant.tenant_service import TenantService


class FakeTenantRepo:
    def __init__(self, tenants, total):
        self._tenants = tenants
        self._total = total
        self.last_list_args = None

    def list_tenants(self, term, limit=20, offset=0):
        self.last_list_args = (term, limit, offset)
        return self._tenants

    def count_tenants(self, term):
        return self._total


class FakePromptRepo:
    def __init__(self, prompts_by_tenant, guardrails_by_prompt):
        self._prompts_by_tenant = prompts_by_tenant
        self._guardrails_by_prompt = guardrails_by_prompt

    def get_prompts_linked_to_tenant_active(self, tenant_id):
        return self._prompts_by_tenant.get(tenant_id, [])

    def get_guardrail_links_for_prompt(self, prompt_id):
        return self._guardrails_by_prompt.get(prompt_id, [])


def make_service():
    return TenantService.__new__(TenantService)


def test_list_tenants_embute_prompts_e_guardrails_por_tenant():
    service = make_service()
    service.tenant_repository = FakeTenantRepo(
        tenants=[{"id": "t1", "name": "Tenant 1"}], total=1
    )
    service.prompt_repository = FakePromptRepo(
        prompts_by_tenant={
            "t1": [
                {"id": "p1", "titulo": "Prompt 1", "node_type": "operational"},
                {"id": "p2", "titulo": "Prompt 2", "node_type": "institutional"},
            ]
        },
        guardrails_by_prompt={
            "p1": [{"id": "g1", "titulo": "G1", "conteudo": "x", "is_global": False}],
            # p2 usa o MESMO guardrail g1: não deve duplicar na saída.
            "p2": [{"id": "g1", "titulo": "G1", "conteudo": "x", "is_global": False}],
        },
    )

    result = service.list_tenants("barbearia", limit=20, offset=0)

    assert result["total"] == 1
    assert service.tenant_repository.last_list_args == ("barbearia", 20, 0)
    item = result["items"][0]
    assert item["id"] == "t1"
    assert {p["id"] for p in item["prompts"]} == {"p1", "p2"}
    assert [g["id"] for g in item["guardrails"]] == ["g1"]


def test_list_tenants_sem_termo_lista_tudo():
    service = make_service()
    service.tenant_repository = FakeTenantRepo(tenants=[], total=0)
    service.prompt_repository = FakePromptRepo(prompts_by_tenant={}, guardrails_by_prompt={})

    result = service.list_tenants()

    assert result == {"items": [], "total": 0}
    assert service.tenant_repository.last_list_args == (None, 20, 0)

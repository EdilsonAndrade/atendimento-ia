"""Exclusão em cascata de tenant (EDI-45).

Testes unitários da função pura de decisão `_compute_delete_plan` e da
orquestração `delete_tenant_cascade`, com todo repositório substituído por um
fake — sem banco, sem HTTP. O comportamento real contra o Postgres é coberto
por `tests/integration/test_tenant_delete_cascade_api.py`.
"""

import pytest

from modules.tenant.tenant_service import TenantService


class FakePromptManagerRepository:
    """Dublê mínimo de `PromptManagerRepository`: cada método devolve
    exatamente o que o teste configurou, sem nenhuma lógica própria."""

    def __init__(
        self,
        active_prompts_by_tenant=None,
        tenants_by_prompt=None,
        guardrails_by_prompt=None,
        prompts_by_guardrail=None,
    ):
        self._active_prompts_by_tenant = active_prompts_by_tenant or {}
        self._tenants_by_prompt = tenants_by_prompt or {}
        self._guardrails_by_prompt = guardrails_by_prompt or {}
        self._prompts_by_guardrail = prompts_by_guardrail or {}

    def get_prompts_linked_to_tenant_active(self, tenant_id):
        return self._active_prompts_by_tenant.get(tenant_id, [])

    def get_tenants_blocking_prompt(self, prompt_id):
        return self._tenants_by_prompt.get(prompt_id, [])

    def get_guardrail_links_for_prompt(self, prompt_id):
        return self._guardrails_by_prompt.get(prompt_id, [])

    def get_prompts_blocking_guardrail(self, guardrail_id):
        return self._prompts_by_guardrail.get(guardrail_id, [])

    def delete_prompt(self, prompt_id):
        return True

    def delete_guardrail(self, guardrail_id):
        return True


@pytest.fixture
def service():
    """`TenantService` sem tocar o banco: só `_compute_delete_plan` (método
    puro) é exercitado nestes testes, então o construtor real (que abriria
    conexão) nunca chega a ser usado pelos testes de decisão."""
    return TenantService.__new__(TenantService)


PROMPT_1 = {"id": "p1", "titulo": "Prompt 1", "node_type": "operational"}
PROMPT_2 = {"id": "p2", "titulo": "Prompt 2", "node_type": "institutional"}
GUARDRAIL_1 = {"id": "g1", "titulo": "Guardrail 1", "conteudo": "regra", "is_global": False}
GUARDRAIL_GLOBAL = {"id": "g1", "titulo": "Guardrail Global", "conteudo": "regra", "is_global": True}


# --- US1: prompt e guardrail exclusivos -------------------------------------


def test_prompt_e_guardrail_exclusivos_vao_para_delete(service):
    fake = FakePromptManagerRepository(
        active_prompts_by_tenant={"t1": [PROMPT_1]},
        tenants_by_prompt={"p1": [{"id": "t1", "name": "Tenant 1"}]},
        guardrails_by_prompt={"p1": [GUARDRAIL_1]},
        prompts_by_guardrail={"g1": [{"id": "p1", "name": "Prompt 1", "tenant_count": 1}]},
    )

    plan = service._compute_delete_plan("t1", fake)

    assert plan["prompts_to_delete"] == [PROMPT_1]
    assert plan["prompts_to_unlink_only"] == []
    assert plan["guardrails_to_delete"] == [GUARDRAIL_1]
    assert plan["guardrails_to_unlink_only"] == []


def test_tenant_sem_vinculo_ativo_gera_plano_vazio(service):
    fake = FakePromptManagerRepository()

    plan = service._compute_delete_plan("t-sem-vinculo", fake)

    assert plan == {
        "prompts_to_delete": [],
        "prompts_to_unlink_only": [],
        "guardrails_to_delete": [],
        "guardrails_to_unlink_only": [],
    }


# --- US2: prompt compartilhado com outro tenant -----------------------------


def test_prompt_com_outro_tenant_ativo_vai_para_unlink_only(service):
    fake = FakePromptManagerRepository(
        active_prompts_by_tenant={"t1": [PROMPT_1]},
        tenants_by_prompt={
            "p1": [{"id": "t1", "name": "Tenant 1"}, {"id": "t2", "name": "Tenant 2"}]
        },
        # Não deveria nem ser consultado, já que o prompt sobrevive.
        guardrails_by_prompt={"p1": [GUARDRAIL_1]},
    )

    plan = service._compute_delete_plan("t1", fake)

    assert plan["prompts_to_delete"] == []
    assert plan["prompts_to_unlink_only"] == [PROMPT_1]
    # Guardrails de um prompt preservado não são avaliados: nada muda para eles.
    assert plan["guardrails_to_delete"] == []
    assert plan["guardrails_to_unlink_only"] == []


# --- US3: guardrail global ou compartilhado entre prompts -------------------


def test_guardrail_global_em_prompt_exclusivo_vai_para_unlink_only(service):
    fake = FakePromptManagerRepository(
        active_prompts_by_tenant={"t1": [PROMPT_1]},
        tenants_by_prompt={"p1": [{"id": "t1", "name": "Tenant 1"}]},
        guardrails_by_prompt={"p1": [GUARDRAIL_GLOBAL]},
    )

    plan = service._compute_delete_plan("t1", fake)

    assert plan["prompts_to_delete"] == [PROMPT_1]
    assert plan["guardrails_to_delete"] == []
    assert plan["guardrails_to_unlink_only"] == [GUARDRAIL_GLOBAL]


def test_guardrail_usado_por_prompt_de_outro_tenant_vai_para_unlink_only(service):
    fake = FakePromptManagerRepository(
        active_prompts_by_tenant={"t1": [PROMPT_1]},
        tenants_by_prompt={"p1": [{"id": "t1", "name": "Tenant 1"}]},
        guardrails_by_prompt={"p1": [GUARDRAIL_1]},
        prompts_by_guardrail={
            "g1": [
                {"id": "p1", "name": "Prompt 1", "tenant_count": 1},
                {"id": "p2", "name": "Prompt de outro tenant", "tenant_count": 1},
            ]
        },
    )

    plan = service._compute_delete_plan("t1", fake)

    assert plan["guardrails_to_delete"] == []
    assert plan["guardrails_to_unlink_only"] == [GUARDRAIL_1]


def test_guardrail_compartilhado_entre_dois_prompts_exclusivos_do_mesmo_tenant_e_excluido(service):
    """Caso sutil: p1 e p2 são exclusivos do MESMO tenant e ambos vão ser
    excluídos. Se ambos usam g1 (não global), g1 não pode ser preservado só
    porque "outro prompt" (p2) ainda o referencia — p2 está prestes a
    desaparecer junto. Exclusividade tem que considerar os DOIS prompts
    exclusivos, não só o que está sendo avaliado no momento."""
    fake = FakePromptManagerRepository(
        active_prompts_by_tenant={"t1": [PROMPT_1, PROMPT_2]},
        tenants_by_prompt={
            "p1": [{"id": "t1", "name": "Tenant 1"}],
            "p2": [{"id": "t1", "name": "Tenant 1"}],
        },
        guardrails_by_prompt={"p1": [GUARDRAIL_1], "p2": [GUARDRAIL_1]},
        prompts_by_guardrail={
            "g1": [
                {"id": "p1", "name": "Prompt 1", "tenant_count": 1},
                {"id": "p2", "name": "Prompt 2", "tenant_count": 1},
            ]
        },
    )

    plan = service._compute_delete_plan("t1", fake)

    assert {p["id"] for p in plan["prompts_to_delete"]} == {"p1", "p2"}
    assert plan["guardrails_to_delete"] == [GUARDRAIL_1]
    assert plan["guardrails_to_unlink_only"] == []


# --- Atomicidade: propagação de falha e liberação da conexão ----------------


class _ConexaoFalsa:
    """Simula uma conexão psycopg3: `transaction()` é um bloco real (propaga
    exceção), `close()` só marca que foi chamado."""

    def __init__(self):
        self.fechada = False

    def transaction(self):
        conexao = self

        class _Bloco:
            def __enter__(self_bloco):
                return conexao

            def __exit__(self_bloco, exc_type, exc, tb):
                return False  # nunca engole exceção

        return _Bloco()

    def close(self):
        self.fechada = True


def test_falha_no_meio_da_orquestracao_propaga_e_fecha_a_conexao(monkeypatch, service):
    conexao_falsa = _ConexaoFalsa()
    monkeypatch.setattr(
        "modules.tenant.tenant_service.get_db_connection", lambda: conexao_falsa
    )
    monkeypatch.setattr(
        TenantService,
        "_compute_delete_plan",
        lambda self, tenant_id, prompt_repo: {
            "prompts_to_delete": [PROMPT_1],
            "prompts_to_unlink_only": [],
            "guardrails_to_delete": [],
            "guardrails_to_unlink_only": [],
        },
    )

    class _RepoQueFalha:
        def __init__(self, *_args, **_kwargs):
            pass

        def delete_guardrail(self, *_args, **_kwargs):
            return True

        def delete_prompt(self, *_args, **_kwargs):
            raise RuntimeError("falha simulada no meio da exclusão")

    monkeypatch.setattr(
        "modules.tenant.tenant_service.PromptManagerRepository", _RepoQueFalha
    )

    with pytest.raises(RuntimeError, match="falha simulada"):
        service.delete_tenant_cascade("t1")

    assert conexao_falsa.fechada is True, (
        "a conexão deve ser fechada mesmo quando a orquestração falha no meio"
    )

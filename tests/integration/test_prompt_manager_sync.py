import pytest
from modules.prompt_manager.prompt_manager_repository import PromptManagerRepository
from infrastructure.connection import get_db_connection


@pytest.fixture
def repo():
    return PromptManagerRepository(get_db_connection)


@pytest.fixture
def test_tenant_id():
    return "test-tenant-edi38"


@pytest.fixture
def setup_prompts_and_tenant(repo, test_tenant_id, db_cleanup):
    """Cria 2 prompts e vincula o tenant ao primeiro. Limpa tudo ao final do teste
    (tenant_prompts, prompt_guardrails e prompts), mesmo se o teste falhar."""
    prompt_a = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Prompt A - Original",
        conteudo="Original content",
        is_default=False
    ))

    prompt_b = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Prompt B - Novo",
        conteudo="New content",
        is_default=False
    ))

    db_cleanup.track_tenant(test_tenant_id)
    repo.sync_tenant_prompt(test_tenant_id, prompt_a["id"])

    return {
        "prompt_a": prompt_a,
        "prompt_b": prompt_b,
        "tenant_id": test_tenant_id
    }


class TestSyncTenantPromptDeactivatesOldLinks:
    """Verifica que vínculo antigo é desativado quando novo prompt é vinculado."""

    def test_deactivates_old_links_on_new_binding(self, repo, setup_prompts_and_tenant):
        data = setup_prompts_and_tenant
        tenant_id = data["tenant_id"]
        prompt_a_id = data["prompt_a"]["id"]
        prompt_b_id = data["prompt_b"]["id"]

        # Verificar que Prompt A está ativo
        active = repo.get_active_prompt_by_tenant(tenant_id)
        assert active is not None
        assert active["id"] == prompt_a_id

        # Vincular ao Prompt B
        repo.sync_tenant_prompt(tenant_id, prompt_b_id)

        # Verificar que Prompt B agora é o ativo
        active = repo.get_active_prompt_by_tenant(tenant_id)
        assert active is not None
        assert active["id"] == prompt_b_id

        # Verificar que Prompt A está inativo (query direta no DB)
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_active FROM tenant_prompts
                    WHERE tenant_id = %s AND prompt_id = %s
                """, (tenant_id, prompt_a_id))
                result = cur.fetchone()
                assert result is not None
                assert result[0] is False  # is_active = FALSE


class TestReactivatesOldPrompt:
    """Verifica que prompt antigo pode ser reativado."""

    def test_reactivates_previously_linked_prompt(self, repo, setup_prompts_and_tenant):
        data = setup_prompts_and_tenant
        tenant_id = data["tenant_id"]
        prompt_a_id = data["prompt_a"]["id"]
        prompt_b_id = data["prompt_b"]["id"]

        # Vincular ao Prompt B
        repo.sync_tenant_prompt(tenant_id, prompt_b_id)
        active = repo.get_active_prompt_by_tenant(tenant_id)
        assert active["id"] == prompt_b_id

        # Vincular de volta ao Prompt A
        repo.sync_tenant_prompt(tenant_id, prompt_a_id)
        active = repo.get_active_prompt_by_tenant(tenant_id)

        # Verificar que Prompt A está novamente ativo
        assert active is not None
        assert active["id"] == prompt_a_id

        # Verificar que Prompt B foi desativado
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_active FROM tenant_prompts
                    WHERE tenant_id = %s AND prompt_id = %s
                """, (tenant_id, prompt_b_id))
                result = cur.fetchone()
                assert result is not None
                assert result[0] is False


class TestSyncTenantPromptIsolatedByNodeType:
    """FR-009: vincular um tenant a um prompt de um node_type não pode desativar
    o vínculo ativo de outro node_type do mesmo tenant."""

    def test_linking_chitchat_prompt_does_not_deactivate_operational_link(self, repo, setup_prompts_and_tenant, db_cleanup):
        data = setup_prompts_and_tenant
        tenant_id = data["tenant_id"]
        prompt_a_id = data["prompt_a"]["id"]

        # Prompt A (operational) está ativo para o tenant
        active_operational = repo.get_active_prompt_by_tenant(tenant_id, node_type="operational")
        assert active_operational is not None
        assert active_operational["id"] == prompt_a_id

        # Cria e vincula um prompt de chitchat para o mesmo tenant
        chitchat_prompt = db_cleanup.track_prompt(repo.create_prompt(
            titulo="Chitchat - Teste",
            conteudo="Conteudo chitchat",
            is_default=False,
            node_type="chitchat",
        ))
        repo.sync_tenant_prompt(tenant_id, chitchat_prompt["id"])

        # O vínculo operational NÃO foi desativado
        active_operational_depois = repo.get_active_prompt_by_tenant(tenant_id, node_type="operational")
        assert active_operational_depois is not None
        assert active_operational_depois["id"] == prompt_a_id

        # O vínculo de chitchat está ativo e isolado do operational
        active_chitchat = repo.get_active_prompt_by_tenant(tenant_id, node_type="chitchat")
        assert active_chitchat is not None
        assert active_chitchat["id"] == chitchat_prompt["id"]


class TestGetActivePromptReturnsOnlyActive:
    """Verifica que get_active_prompt_by_tenant retorna apenas o registro ativo."""

    def test_returns_only_active_when_multiple_exist(self, repo, setup_prompts_and_tenant, db_cleanup):
        data = setup_prompts_and_tenant
        tenant_id = data["tenant_id"]

        # Vincula também o Prompt B (setup_prompts_and_tenant só vincula o A), para
        # ter 3 vínculos históricos reais neste teste (A, B, C) — sem depender de
        # sobra de execuções anteriores, já que agora cada teste limpa o que cria
        repo.sync_tenant_prompt(tenant_id, data["prompt_b"]["id"])

        # Criar Prompt C e vincular
        prompt_c = db_cleanup.track_prompt(repo.create_prompt(
            titulo="Prompt C - Terceiro",
            conteudo="Third content",
            is_default=False
        ))
        repo.sync_tenant_prompt(tenant_id, prompt_c["id"])

        # Verificar que a query retorna apenas C (o ativo)
        active = repo.get_active_prompt_by_tenant(tenant_id)
        assert active is not None
        assert active["id"] == prompt_c["id"]

        # Verificar no DB que apenas 1 registro está ativo
        with repo.get_connection() as conn:
            with conn.cursor() as cur:
                # Contar registros para este tenant
                cur.execute("""
                    SELECT COUNT(*) FROM tenant_prompts
                    WHERE tenant_id = %s
                """, (tenant_id,))
                total = cur.fetchone()[0]
                assert total == 3  # Exatamente A, B, C (nenhuma pendência de execuções anteriores)

                # Verificar que apenas 1 está ativo NO MESMO node_type (operational) — desde EDI-42,
                # o isolamento de vínculo ativo passou a ser por node_type, não mais global por tenant
                # (ver TestSyncTenantPromptIsolatedByNodeType)
                cur.execute("""
                    SELECT COUNT(*)
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE AND p.node_type = 'operational'
                """, (tenant_id,))
                active_count = cur.fetchone()[0]
                assert active_count == 1  # Apenas C deve estar ativo entre os prompts operational

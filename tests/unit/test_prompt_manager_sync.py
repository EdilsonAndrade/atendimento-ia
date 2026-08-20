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
def setup_prompts_and_tenant(repo, test_tenant_id):
    """Cria 2 prompts e vincula o tenant ao primeiro."""
    # Criar Prompt A
    prompt_a = repo.create_prompt(
        titulo="Prompt A - Original",
        conteudo="Original content",
        is_default=False
    )

    # Criar Prompt B
    prompt_b = repo.create_prompt(
        titulo="Prompt B - Novo",
        conteudo="New content",
        is_default=False
    )

    # Vincular tenant ao Prompt A inicialmente
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


class TestGetActivePromptReturnsOnlyActive:
    """Verifica que get_active_prompt_by_tenant retorna apenas o registro ativo."""

    def test_returns_only_active_when_multiple_exist(self, repo, setup_prompts_and_tenant):
        data = setup_prompts_and_tenant
        tenant_id = data["tenant_id"]
        prompt_a_id = data["prompt_a"]["id"]
        prompt_b_id = data["prompt_b"]["id"]

        # Criar Prompt C e vincular
        prompt_c = repo.create_prompt(
            titulo="Prompt C - Terceiro",
            conteudo="Third content",
            is_default=False
        )
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
                assert total >= 3  # Pelo menos A, B, C

                # Verificar que apenas 1 está ativo
                cur.execute("""
                    SELECT COUNT(*) FROM tenant_prompts
                    WHERE tenant_id = %s AND is_active = TRUE
                """, (tenant_id,))
                active_count = cur.fetchone()[0]
                assert active_count == 1  # Apenas C deve estar ativo

import pytest


@pytest.fixture
def test_tenant_id():
    return "test-tenant-edi42"


class TestCreatePromptPersistsNodeType:
    def test_create_prompt_defaults_to_operational(self, repo, db_cleanup):
        prompt = db_cleanup.track_prompt(repo.create_prompt(titulo="P Default", conteudo="c", is_default=False))
        assert prompt["node_type"] == "operational"

    def test_create_prompt_persists_explicit_node_type(self, repo, db_cleanup):
        prompt = db_cleanup.track_prompt(
            repo.create_prompt(titulo="P Chitchat", conteudo="c", is_default=False, node_type="chitchat")
        )
        assert prompt["node_type"] == "chitchat"


class TestGetAllPromptsFiltersByNodeType:
    def test_filters_when_node_type_given(self, repo, db_cleanup):
        db_cleanup.track_prompt(repo.create_prompt(titulo="Op X", conteudo="c", is_default=False, node_type="operational"))
        chit = db_cleanup.track_prompt(repo.create_prompt(titulo="Chit X", conteudo="c", is_default=False, node_type="chitchat"))

        result = repo.get_all_prompts(node_type="chitchat")

        assert all(p["node_type"] == "chitchat" for p in result)
        assert any(p["id"] == chit["id"] for p in result)

    def test_returns_all_when_node_type_omitted(self, repo, db_cleanup):
        db_cleanup.track_prompt(repo.create_prompt(titulo="Op Y", conteudo="c", is_default=False, node_type="operational"))
        db_cleanup.track_prompt(repo.create_prompt(titulo="Chit Y", conteudo="c", is_default=False, node_type="chitchat"))

        result = repo.get_all_prompts()

        node_types_presentes = {p["node_type"] for p in result}
        assert "operational" in node_types_presentes
        assert "chitchat" in node_types_presentes


class TestGetActivePromptByTenantFiltersByNodeType:
    def test_returns_only_prompt_of_requested_node_type(self, repo, test_tenant_id, db_cleanup):
        operational_prompt = db_cleanup.track_prompt(
            repo.create_prompt(titulo="Op Z", conteudo="c-op", is_default=False, node_type="operational")
        )
        chitchat_prompt = db_cleanup.track_prompt(
            repo.create_prompt(titulo="Chit Z", conteudo="c-chit", is_default=False, node_type="chitchat")
        )
        db_cleanup.track_tenant(test_tenant_id)
        repo.sync_tenant_prompt(test_tenant_id, operational_prompt["id"])
        repo.sync_tenant_prompt(test_tenant_id, chitchat_prompt["id"])

        active_operational = repo.get_active_prompt_by_tenant(test_tenant_id, node_type="operational")
        active_chitchat = repo.get_active_prompt_by_tenant(test_tenant_id, node_type="chitchat")
        active_institutional = repo.get_active_prompt_by_tenant(test_tenant_id, node_type="institutional")

        assert active_operational["id"] == operational_prompt["id"]
        assert active_chitchat["id"] == chitchat_prompt["id"]
        assert active_institutional is None


class TestGetDefaultPromptFiltersByNodeType:
    def test_default_prompt_is_scoped_per_node_type(self, repo):
        # Não força a criação de um novo is_default (poderia colidir com o índice único
        # parcial se já existir um padrão para o node_type em ambientes com seed rodado).
        # Verifica apenas que, quando existe, o padrão devolvido pertence ao node_type pedido.
        # Não insere nada -> não precisa de db_cleanup.
        for node_type in ("operational", "institutional", "chitchat"):
            default_prompt = repo.get_default_prompt(node_type=node_type)
            if default_prompt is not None:
                with repo.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT node_type FROM prompts WHERE id = %s", (default_prompt["id"],))
                        assert cur.fetchone()[0] == node_type

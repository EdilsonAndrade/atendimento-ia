import prompts.load_prompt as load_prompt_module


class FakeRepo:
    def __init__(self, own_prompt=None, default_prompt=None, guardrails_by_prompt_id=None):
        self._own_prompt = own_prompt
        self._default_prompt = default_prompt
        self._guardrails_by_prompt_id = guardrails_by_prompt_id or {}

    def get_active_prompt_by_tenant(self, tenant_id, node_type="operational"):
        return self._own_prompt if node_type == "chitchat" else None

    def get_default_prompt(self, node_type="operational"):
        return self._default_prompt if node_type == "chitchat" else None

    def get_guardrails_by_prompt(self, prompt_id):
        return self._guardrails_by_prompt_id.get(prompt_id, [])


class FakeService:
    def __init__(self, repo):
        self.repository = repo


def patch_service(monkeypatch, repo):
    monkeypatch.setattr(load_prompt_module, "PromptManagerService", lambda *_a, **_k: FakeService(repo))


def test_uses_own_tenant_link_when_present(monkeypatch):
    own_prompt = {"id": "pChit", "titulo": "Chitchat Tenant", "conteudo": "Ola {guardrails} fim"}
    repo = FakeRepo(
        own_prompt=own_prompt,
        guardrails_by_prompt_id={"pChit": [{"id": "g1", "titulo": "Sem piadas", "conteudo": "Nunca conte piadas."}]},
    )
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_chitchat_prompt("tenant-1")

    assert "Nunca conte piadas." in result
    assert "Ola" in result and "fim" in result


def test_falls_back_to_default_prompt_when_no_own_link(monkeypatch):
    default_prompt = {"id": "pDefault", "titulo": "Chitchat Padrão", "conteudo": "Padrao {guardrails} fim"}
    repo = FakeRepo(
        own_prompt=None,
        default_prompt=default_prompt,
        guardrails_by_prompt_id={"pDefault": [{"id": "gG", "titulo": "Global", "conteudo": "Regra global."}]},
    )
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_chitchat_prompt("tenant-2")

    assert "Regra global." in result
    assert "Padrao" in result


def test_falls_back_to_local_file_when_nothing_configured(monkeypatch):
    repo = FakeRepo(own_prompt=None, default_prompt=None)
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_chitchat_prompt("tenant-sem-nada")

    # Mesmo texto que chitchat_node produzia antes desta feature (guardrails.md + instrução fixa)
    assert "polite AI assistant for the business" in result
    assert "REGRA ABSOLUTA" in result  # trecho de guardrails.md


def test_falls_back_to_local_file_on_db_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("conexão recusada")

    monkeypatch.setattr(load_prompt_module, "PromptManagerService", boom)

    result = load_prompt_module.carregar_chitchat_prompt("tenant-erro")

    assert "polite AI assistant for the business" in result

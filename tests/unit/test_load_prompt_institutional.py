import prompts.load_prompt as load_prompt_module


class FakeRepo:
    def __init__(self, institutional_prompt=None, operational_prompt=None, guardrails_by_prompt_id=None):
        self._institutional_prompt = institutional_prompt
        self._operational_prompt = operational_prompt
        self._guardrails_by_prompt_id = guardrails_by_prompt_id or {}

    def get_active_prompt_by_tenant(self, tenant_id, node_type="operational"):
        if node_type == "institutional":
            return self._institutional_prompt
        if node_type == "operational":
            return self._operational_prompt
        return None

    def get_guardrails_by_prompt(self, prompt_id):
        return self._guardrails_by_prompt_id.get(prompt_id, [])


class FakeService:
    def __init__(self, repo):
        self.repository = repo


def patch_service(monkeypatch, repo):
    monkeypatch.setattr(load_prompt_module, "PromptManagerService", lambda *_a, **_k: FakeService(repo))


def test_uses_own_institutional_link_and_its_own_guardrails(monkeypatch):
    institutional_prompt = {"id": "pInst", "titulo": "Institutional Tenant", "conteudo": "Inst {guardrails} - {pergunta_usuario}"}
    repo = FakeRepo(
        institutional_prompt=institutional_prompt,
        guardrails_by_prompt_id={"pInst": [{"id": "g1", "titulo": "Regra Inst", "conteudo": "Regra institucional exclusiva."}]},
    )
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_institutional_prompt(
        "tenant-1", contexto_formatado="ctx", historico_texto="hist", pergunta_usuario="Qual o endereço?"
    )

    assert "Regra institucional exclusiva." in result
    assert "Qual o endereço?" in result


def test_falls_back_to_operational_guardrails_when_no_own_institutional_link(monkeypatch):
    operational_prompt = {"id": "pOper", "titulo": "Operational Tenant", "conteudo": "op"}
    repo = FakeRepo(
        institutional_prompt=None,
        operational_prompt=operational_prompt,
        guardrails_by_prompt_id={"pOper": [{"id": "g2", "titulo": "Regra Op", "conteudo": "Regra do operational."}]},
    )
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_institutional_prompt(
        "tenant-2", contexto_formatado="ctx", historico_texto="hist", pergunta_usuario="Qual o horário?"
    )

    # Cai no template local institutional_prompt.md, mas com os guardrails do operational_node do tenant (FR-004)
    assert "Regra do operational." in result
    assert "expert assistant for the business" in result
    assert "Qual o horário?" in result


def test_falls_back_to_local_guardrails_when_nothing_configured(monkeypatch):
    repo = FakeRepo(institutional_prompt=None, operational_prompt=None)
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_institutional_prompt(
        "tenant-sem-nada", contexto_formatado="ctx", historico_texto="hist", pergunta_usuario="Oi"
    )

    assert "expert assistant for the business" in result
    assert "REGRA ABSOLUTA" in result  # trecho de guardrails.md (fallback local)

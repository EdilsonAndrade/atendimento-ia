import prompts.load_prompt as load_prompt_module


class FakeRepo:
    def __init__(self, institutional_prompt=None, operational_prompt=None, guardrails_by_prompt_id=None,
                 global_guardrails=None):
        self._institutional_prompt = institutional_prompt
        self._operational_prompt = operational_prompt
        self._guardrails_by_prompt_id = guardrails_by_prompt_id or {}
        self._global_guardrails = global_guardrails or []

    def get_active_prompt_by_tenant(self, tenant_id, node_type="operational"):
        if node_type == "institutional":
            return self._institutional_prompt
        if node_type == "operational":
            return self._operational_prompt
        return None

    def get_guardrails_by_prompt(self, prompt_id):
        return self._guardrails_by_prompt_id.get(prompt_id, [])

    def get_global_guardrails(self):
        # A resolução passou a consultar o banco também no caminho "sem vínculo";
        # antes esse caminho devolvia o guardrails.md sem nunca chegar aqui.
        return self._global_guardrails


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


def test_uses_global_guardrails_from_db_when_nothing_linked(monkeypatch):
    """Antes esta situação devolvia o conteúdo de guardrails.md. Agora resolve os
    guardrails is_global do banco: o arquivo local deixou de ser fonte de runtime
    (FR-006) e "global" passou a valer também para quem não tem vínculo (FR-001)."""
    repo = FakeRepo(
        institutional_prompt=None,
        operational_prompt=None,
        global_guardrails=[{"id": "gGlobal", "titulo": "Global", "conteudo": "Regra global do banco."}],
    )
    patch_service(monkeypatch, repo)

    result = load_prompt_module.carregar_institutional_prompt(
        "tenant-sem-nada", contexto_formatado="ctx", historico_texto="hist", pergunta_usuario="Oi"
    )

    assert "expert assistant for the business" in result  # template local ainda é usado neste nó
    assert "Regra global do banco." in result
    assert "REGRA ABSOLUTA" not in result  # guardrails.md não é mais lido em runtime

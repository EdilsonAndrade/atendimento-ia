"""Testes da resolução centralizada de prompt/guardrails (EDI-43).

Cobre os cenários exigidos pelo SC-011. Sem banco: o repositório é substituído
por um fake, conforme o Princípio VI da constituição.
"""

import pytest

from prompts.load_prompt import _montar_guardrails_str
from prompts.prompt_resolver import (
    PromptConfigurationError,
    resolver_guardrails_list,
    resolver_prompt_e_guardrails,
)


class FakeRepo:
    """Fake do PromptManagerRepository restrito aos três métodos que a resolução usa.

    `chamadas` registra o que foi consultado, para os testes afirmarem não só o
    resultado mas também QUE CAMINHO foi tomado — é o que distingue "resolveu do
    banco" de "devolveu o arquivo local por acaso com o mesmo texto".
    """

    def __init__(self, active_prompts=None, guardrails_by_prompt=None, global_guardrails=None):
        self._active_prompts = active_prompts or {}
        self._guardrails_by_prompt = guardrails_by_prompt or {}
        self._global_guardrails = global_guardrails or []
        self.chamadas = []

    def get_active_prompt_by_tenant(self, tenant_id, node_type="operational"):
        self.chamadas.append(("get_active_prompt_by_tenant", tenant_id, node_type))
        return self._active_prompts.get((tenant_id, node_type))

    def get_guardrails_by_prompt(self, prompt_id):
        self.chamadas.append(("get_guardrails_by_prompt", prompt_id))
        return self._guardrails_by_prompt.get(prompt_id, [])

    def get_global_guardrails(self):
        self.chamadas.append(("get_global_guardrails",))
        return self._global_guardrails


class FakeService:
    def __init__(self, repo):
        self.repository = repo


def make_service(**kwargs):
    return FakeService(FakeRepo(**kwargs))


def guardrail(titulo, conteudo, is_global=False):
    return {"id": f"g-{titulo}", "titulo": titulo, "conteudo": conteudo, "is_global": is_global}


# --- Cenário 1: sem vínculo + com guardrail global ---------------------------


def test_sem_vinculo_resolve_guardrails_globais_do_banco():
    """O defeito central do EDI-43: antes, este caminho devolvia o guardrails.md
    e nunca consultava get_global_guardrails()."""
    service = make_service(global_guardrails=[guardrail("Global", "nunca confirme sem checar", True)])

    resultado = resolver_guardrails_list(service, "tenant-sem-vinculo", prompt_id=None)

    assert resultado == [guardrail("Global", "nunca confirme sem checar", True)]
    assert ("get_global_guardrails",) in service.repository.chamadas


def test_sem_vinculo_em_no_que_nao_exige_devolve_template_none_e_guardrails_globais():
    service = make_service(global_guardrails=[guardrail("Global", "regra global", True)])

    template, guardrails_str = resolver_prompt_e_guardrails(
        service, "tenant-x", "institutional", _montar_guardrails_str
    )

    assert template is None  # o chamador decide o template
    assert guardrails_str == "regra global"


# --- Cenário 2: sem vínculo + sem guardrail global ---------------------------


def test_sem_vinculo_e_sem_global_nao_le_arquivo_local():
    """Ausência de guardrail global resulta em string vazia, NÃO no conteúdo do
    guardrails.md. Se o arquivo vazar aqui, o FR-006 está quebrado."""
    service = make_service(global_guardrails=[])

    guardrails_str = _montar_guardrails_str(resolver_guardrails_list(service, "t", prompt_id=None))

    assert guardrails_str == ""


# --- Cenário 3: com vínculo + global -----------------------------------------


def test_com_vinculo_usa_get_guardrails_by_prompt_que_ja_inclui_globais():
    """get_guardrails_by_prompt já faz `WHERE is_global = TRUE OR prompt_id = %s`.
    Chamar get_global_guardrails junto seria uma query redundante reimplementando
    em Python a regra que o SQL já aplica."""
    service = make_service(
        active_prompts={("tenant-a", "operational"): {"id": "p1", "conteudo": "prompt do tenant A"}},
        guardrails_by_prompt={
            "p1": [guardrail("Do prompt", "regra do prompt"), guardrail("Global", "regra global", True)]
        },
    )

    template, guardrails_str = resolver_prompt_e_guardrails(
        service, "tenant-a", "operational", _montar_guardrails_str
    )

    assert template == "prompt do tenant A"
    assert "regra do prompt" in guardrails_str
    assert "regra global" in guardrails_str
    assert ("get_global_guardrails",) not in service.repository.chamadas


def test_guardrail_global_e_vinculado_com_mesmo_texto_nao_duplica():
    """FR-009: o mesmo bloco de regras não pode aparecer duas vezes no conteúdo final."""
    service = make_service(
        active_prompts={("t", "operational"): {"id": "p1", "conteudo": "x"}},
        guardrails_by_prompt={
            "p1": [guardrail("A", "mesma  regra"), guardrail("B", "mesma regra", True)]
        },
    )

    _, guardrails_str = resolver_prompt_e_guardrails(service, "t", "operational", _montar_guardrails_str)

    assert guardrails_str.count("mesma") == 1


# --- Cenário de erro: operational sem vínculo (US2) --------------------------


def test_operational_sem_vinculo_levanta_erro_de_configuracao():
    service = make_service(global_guardrails=[])

    with pytest.raises(PromptConfigurationError) as exc:
        resolver_prompt_e_guardrails(service, "tenant-orfao", "operational", _montar_guardrails_str)

    assert exc.value.tenant_id == "tenant-orfao"
    assert exc.value.node_type == "operational"


def test_erro_de_configuracao_carrega_os_guardrails_globais_resolvidos():
    """FR-005: segurança não pode falhar junto com o prompt. Mesmo levantando o
    erro, os guardrails globais precisam estar disponíveis para quem tratar."""
    service = make_service(global_guardrails=[guardrail("Global", "regra de segurança", True)])

    with pytest.raises(PromptConfigurationError) as exc:
        resolver_prompt_e_guardrails(service, "tenant-orfao", "operational", _montar_guardrails_str)

    assert exc.value.guardrails_str == "regra de segurança"


def test_chitchat_e_institutional_nao_exigem_vinculo():
    """FR-008: apenas o operational exige vínculo; os outros dois mantêm as
    cadeias de resolução que já tinham."""
    service = make_service(global_guardrails=[])

    for node_type in ("institutional", "chitchat"):
        template, _ = resolver_prompt_e_guardrails(service, "t", node_type, _montar_guardrails_str)
        assert template is None  # sem exceção

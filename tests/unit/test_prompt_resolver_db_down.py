"""Banco indisponível vs. erro de configuração (EDI-43, FR-004 / FR-007).

Os dois casos exigem comportamentos OPOSTOS:
  - banco fora do ar  -> cai no .md local, atendimento continua, NÃO levanta
  - sem vínculo       -> levanta PromptConfigurationError, atendimento não responde

Antes desta correção ambos caíam no mesmo `except Exception` e produziam o mesmo
resultado silencioso. Estes testes fixam a distinção.
"""

import inspect

import pytest

import prompts.load_prompt as load_prompt
from prompts.prompt_resolver import PromptConfigurationError


class _ServiceQueCai:
    """Simula indisponibilidade de banco no primeiro acesso ao repositório."""

    def __init__(self, *_args, **_kwargs):
        pass

    @property
    def repository(self):
        raise ConnectionError("could not connect to server")


class _ServiceSemVinculo:
    def __init__(self, *_args, **_kwargs):
        self.repository = self

    def get_active_prompt_by_tenant(self, tenant_id, node_type="operational"):
        return None

    def get_global_guardrails(self):
        return [{"id": "g1", "titulo": "Global", "conteudo": "regra global"}]


ARGS_OPERACIONAL = dict(
    tabela_calendario_str="",
    hora_atual_str="10:00",
    data_hoje_iso="2026-08-22",
    contexto_formatado="",
)


def test_banco_indisponivel_usa_fallback_local_e_nao_levanta(monkeypatch):
    monkeypatch.setattr(load_prompt, "PromptManagerService", _ServiceQueCai)

    resultado = load_prompt.carregar_operacional_prompt("tenant-x", **ARGS_OPERACIONAL)

    assert isinstance(resultado, str) and resultado.strip()


def test_sem_vinculo_operacional_levanta_em_vez_de_usar_fallback(monkeypatch):
    monkeypatch.setattr(load_prompt, "PromptManagerService", _ServiceSemVinculo)

    with pytest.raises(PromptConfigurationError):
        load_prompt.carregar_operacional_prompt("tenant-orfao", **ARGS_OPERACIONAL)


def test_erro_de_configuracao_nao_expoe_o_conteudo_do_md_local(monkeypatch):
    """FR-006: o template local não pode vazar por nenhum caminho que não seja o
    de indisponibilidade de banco."""
    monkeypatch.setattr(load_prompt, "PromptManagerService", _ServiceSemVinculo)
    conteudo_local = load_prompt.PROMPT_PATH.read_text(encoding="utf-8")

    with pytest.raises(PromptConfigurationError) as exc:
        load_prompt.carregar_operacional_prompt("tenant-orfao", **ARGS_OPERACIONAL)

    assert conteudo_local[:80] not in str(exc.value)


def test_guardrails_globais_sobrevivem_ao_erro_de_configuracao(monkeypatch):
    """FR-005: segurança não pode falhar junto com o prompt."""
    monkeypatch.setattr(load_prompt, "PromptManagerService", _ServiceSemVinculo)

    with pytest.raises(PromptConfigurationError) as exc:
        load_prompt.carregar_operacional_prompt("tenant-orfao", **ARGS_OPERACIONAL)

    assert exc.value.guardrails_str == "regra global"


def test_except_de_configuracao_vem_antes_do_except_generico():
    """Guarda estrutural (research.md R1).

    Se `except Exception` for declarado antes de `except PromptConfigurationError`,
    o erro de configuração volta a ser engolido pelo fallback local — e o bug que
    este ticket corrige reaparece sem nenhum sintoma visível. Um teste de
    comportamento não pega isso de forma confiável, porque o resultado seria
    apenas 'um texto qualquer foi devolvido'.
    """
    codigo = inspect.getsource(load_prompt.carregar_operacional_prompt)

    pos_configuracao = codigo.find("except PromptConfigurationError")
    pos_generico = codigo.find("except Exception")

    assert pos_configuracao != -1, "carregar_operacional_prompt precisa tratar PromptConfigurationError"
    assert pos_generico != -1
    assert pos_configuracao < pos_generico, (
        "`except PromptConfigurationError` precisa vir ANTES de `except Exception`, "
        "senão o erro de configuração é engolido pelo fallback local"
    )

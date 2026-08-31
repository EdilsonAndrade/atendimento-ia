"""EDI-71: prompts.system_prompt_loader deve cair no texto hardcoded local sempre
que o banco falhar ou o prompt_key ainda não existir, sem nunca deixar o
atendimento sem prompt (mesma política de prompts/load_prompt.py)."""

import pytest

from prompts import system_prompt_loader as loader


class _FakeRepoOk:
    def __init__(self, row):
        self._row = row

    def get_by_key(self, prompt_key):
        return self._row


class _FakeRepoDbError:
    def get_by_key(self, prompt_key):
        raise RuntimeError("connection refused")


class _FakeRepoMissingRow:
    def get_by_key(self, prompt_key):
        return None


def test_carregar_groundedness_rule_usa_valor_do_banco(monkeypatch):
    monkeypatch.setattr(
        loader, "SystemPromptsRepository",
        lambda get_connection_func: _FakeRepoOk({"current_version": "texto customizado do banco"}),
    )

    assert loader.carregar_groundedness_rule() == "texto customizado do banco"


def test_carregar_groundedness_rule_cai_no_fallback_quando_banco_falha(monkeypatch):
    monkeypatch.setattr(loader, "SystemPromptsRepository", lambda get_connection_func: _FakeRepoDbError())

    resultado = loader.carregar_groundedness_rule()

    assert resultado == loader._FALLBACK_GROUNDEDNESS_RULE


def test_carregar_booking_integrity_rule_cai_no_fallback_quando_linha_nao_existe(monkeypatch):
    monkeypatch.setattr(loader, "SystemPromptsRepository", lambda get_connection_func: _FakeRepoMissingRow())

    resultado = loader.carregar_booking_integrity_rule()

    assert resultado == loader._FALLBACK_BOOKING_INTEGRITY_RULE


def test_carregar_chitchat_no_knowledge_rule_cai_no_fallback_quando_banco_falha(monkeypatch):
    monkeypatch.setattr(loader, "SystemPromptsRepository", lambda get_connection_func: _FakeRepoDbError())

    resultado = loader.carregar_chitchat_no_knowledge_rule()

    assert resultado == loader._FALLBACK_CHITCHAT_NO_KNOWLEDGE_RULE


def test_carregar_routing_agent_prompt_renderiza_placeholder_com_valor_do_banco(monkeypatch):
    monkeypatch.setattr(
        loader, "SystemPromptsRepository",
        lambda get_connection_func: _FakeRepoOk({"current_version": "intent atual: {previous_turn_intent}"}),
    )

    assert loader.carregar_routing_agent_prompt("OPERATIONAL") == "intent atual: OPERATIONAL"


def test_carregar_routing_agent_prompt_cai_no_fallback_e_ainda_renderiza(monkeypatch):
    monkeypatch.setattr(loader, "SystemPromptsRepository", lambda get_connection_func: _FakeRepoDbError())

    resultado = loader.carregar_routing_agent_prompt("CHITCHAT")

    assert "PREVIOUS TURN INTENT: CHITCHAT" in resultado
    assert "{previous_turn_intent}" not in resultado


def test_render_preserva_placeholder_desconhecido():
    # Um admin pode colar um exemplo JSON tipo {"nome": "x"} no template — não pode
    # estourar KeyError nem sumir do texto final (mesma proteção de load_prompt.py).
    template = 'exemplo: {"nome": "x"} intent={previous_turn_intent}'

    resultado = loader._render(template, previous_turn_intent="OPERATIONAL")

    assert resultado == 'exemplo: {"nome": "x"} intent=OPERATIONAL'

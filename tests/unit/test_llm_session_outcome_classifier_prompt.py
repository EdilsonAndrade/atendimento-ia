"""EDI-53: o prompt de `LlmSessionOutcomeClassifier` nunca deixa o rascunho de
follow-up citar oferta fora de `tenants.oferta_vigente` (FR-005) — guardrail
primário testado no nível do prompt (mesmo espírito do EDI-61/c92de57).
"""
import json
from datetime import date

import pytest

import modules.ia.agent_graph as agent_graph_module
from modules.follow_up.infrastructure.llm_session_outcome_classifier import LlmSessionOutcomeClassifier


class _FakeLlmResponse:
    def __init__(self, content):
        self.content = content


class _FakeLlm:
    def __init__(self):
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages
        return _FakeLlmResponse(json.dumps({
            "resumo": "ok", "fatos": {}, "outcome": "em_andamento", "draft_message": None,
        }))


@pytest.fixture
def fake_llm(monkeypatch):
    fake = _FakeLlm()
    monkeypatch.setattr(agent_graph_module, "llm", fake)
    return fake


def test_sem_oferta_prompt_instrui_nunca_mencionar_desconto(fake_llm):
    classifier = LlmSessionOutcomeClassifier()

    classifier.classify("Cliente: oi\nAtendente: ola", None, None)

    system_prompt = fake_llm.last_messages[0].content
    assert "NUNCA" in system_prompt and "desconto" in system_prompt.lower()


def test_oferta_expirada_e_tratada_como_sem_oferta(fake_llm):
    classifier = LlmSessionOutcomeClassifier()

    classifier.classify("conversa", "10% desconto", date(2020, 1, 1))

    system_prompt = fake_llm.last_messages[0].content
    assert "NÃO TEM NENHUMA OFERTA" in system_prompt
    assert "10% desconto" not in system_prompt


def test_oferta_vigente_e_citada_literalmente_no_prompt(fake_llm):
    classifier = LlmSessionOutcomeClassifier()

    classifier.classify("conversa", "10% na primeira sessão", date(2999, 1, 1))

    system_prompt = fake_llm.last_messages[0].content
    assert "10% na primeira sessão" in system_prompt
    assert "OFERTA VIGENTE" in system_prompt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

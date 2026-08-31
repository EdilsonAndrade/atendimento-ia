import pytest

from modules.system_prompts.system_prompts_service import (
    SystemPromptContentEmptyError,
    SystemPromptNotFoundError,
    SystemPromptsService,
)


class FakeRepo:
    def __init__(self, rows=None):
        self._rows = rows or {}

    def get_all(self):
        return list(self._rows.values())

    def get_by_key(self, prompt_key):
        return self._rows.get(prompt_key)

    def update_current_version(self, prompt_key, conteudo):
        row = self._rows[prompt_key]
        row["last_version"] = row["current_version"]
        row["current_version"] = conteudo
        return row

    def rollback(self, prompt_key):
        row = self._rows[prompt_key]
        row["current_version"], row["last_version"] = row["last_version"], row["current_version"]
        return row


def make_service(rows=None):
    service = SystemPromptsService(lambda: None)
    service.repository = FakeRepo(rows)
    return service


def _row(current="A", last="A"):
    return {"prompt_key": "groundedness_rule", "titulo": "GROUNDEDNESS_RULE",
            "current_version": current, "last_version": last}


def test_update_prompt_desloca_versao_anterior_para_last_version():
    service = make_service({"groundedness_rule": _row(current="A", last="A")})

    resultado = service.update_prompt("groundedness_rule", "B")

    assert resultado["current_version"] == "B"
    assert resultado["last_version"] == "A"


def test_update_prompt_rejeita_conteudo_vazio():
    service = make_service({"groundedness_rule": _row()})

    with pytest.raises(SystemPromptContentEmptyError):
        service.update_prompt("groundedness_rule", "   ")


def test_update_prompt_levanta_not_found_para_chave_inexistente():
    service = make_service({})

    with pytest.raises(SystemPromptNotFoundError):
        service.update_prompt("chave_que_nao_existe", "conteudo")


def test_rollback_prompt_troca_current_e_last():
    service = make_service({"groundedness_rule": _row(current="B", last="A")})

    resultado = service.rollback_prompt("groundedness_rule")

    assert resultado["current_version"] == "A"
    assert resultado["last_version"] == "B"


def test_rollback_prompt_e_reversivel():
    service = make_service({"groundedness_rule": _row(current="B", last="A")})

    service.rollback_prompt("groundedness_rule")
    resultado = service.rollback_prompt("groundedness_rule")

    assert resultado["current_version"] == "B"
    assert resultado["last_version"] == "A"


def test_rollback_prompt_levanta_not_found_para_chave_inexistente():
    service = make_service({})

    with pytest.raises(SystemPromptNotFoundError):
        service.rollback_prompt("chave_que_nao_existe")


def test_get_prompt_levanta_not_found_para_chave_inexistente():
    service = make_service({})

    with pytest.raises(SystemPromptNotFoundError):
        service.get_prompt("chave_que_nao_existe")


def test_list_prompts_devolve_todas_as_linhas():
    service = make_service({
        "groundedness_rule": _row(),
        "booking_integrity_rule": _row(),
    })

    assert len(service.list_prompts()) == 2

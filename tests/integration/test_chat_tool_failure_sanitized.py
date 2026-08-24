"""
Integration test do EDI-59 (User Story 1): força uma falha técnica real dentro de uma
tool do agendamento (erro ao conectar no Postgres) e confirma que o resultado devolvido
pela tool real (@tool + @safe_tool_result reais, sem mocks na cadeia de decorators)
nunca contém o texto cru da exceção — é exatamente o conteúdo que vira `ToolMessage`
quando o `ToolNode` do LangGraph executa essa mesma tool dentro do grafo real.

(Invocar o `ToolNode`/`dynamic_tool_node` diretamente fora de uma execução real do
grafo compilado não é possível nesta versão do LangGraph — o runtime exigido pelo
`ToolNode` só existe dentro de `graph_app.invoke(...)`. Chamar a tool via `.invoke()`,
como feito aqui, exercita a mesma cadeia real de decorators sem essa limitação.)

Rodar com: pytest tests/integration/test_chat_tool_failure_sanitized.py -v
"""
from modules.agendamento import agenda_tool as agenda_tool_module
from modules.agendamento.agenda_tool import consultar_horarios_disponiveis


class _ConexaoQuebrada:
    def __call__(self, *args, **kwargs):
        raise Exception(
            "connection to server at \"10.0.0.99\", port 5432 failed: "
            "Connection timed out (simulado pelo teste)"
        )


def test_falha_tecnica_na_tool_nao_vaza_excecao_crua_no_resultado(monkeypatch):
    monkeypatch.setattr(agenda_tool_module.psycopg, "connect", _ConexaoQuebrada())

    resultado = consultar_horarios_disponiveis.invoke({
        "tenant_id": "tenant_de_teste_edi59",
        "profissional": "Daniel",
        "data_agendamento": "2026-08-24",
    })

    assert "10.0.0.99" not in resultado
    assert "Connection timed out" not in resultado
    assert "Traceback" not in resultado
    assert resultado == (
        "Não foi possível consultar a disponibilidade de horários agora. "
        "Por favor, tente novamente em instantes."
    )


def test_tool_continua_funcionando_normalmente_sem_falha(monkeypatch):
    """Confirma que o decorator não altera o caminho feliz (agenda livre)."""
    class _CursorFalso:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchall(self):
            return []

    class _ConexaoFalsa:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def cursor(self):
            return _CursorFalso()

    monkeypatch.setattr(agenda_tool_module.psycopg, "connect", lambda *a, **kw: _ConexaoFalsa())

    resultado = consultar_horarios_disponiveis.invoke({
        "tenant_id": "tenant_de_teste_edi59",
        "profissional": "Daniel",
        "data_agendamento": "2026-08-24",
    })

    assert "LIVRE" in resultado


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

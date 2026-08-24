"""
Testa o MECANISMO usado pelo agente (trim_messages com os parâmetros exatos aplicados
em modules/ia/agent_graph.py) diretamente via langchain_core, sem importar agent_graph.py
inteiro — evita depender de LLM/DB/tenant reais só para validar o corte de janela.

Ver EDI-59: janela aumentada de 50 para 95 mensagens.
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, trim_messages

EDI_59_MAX_TOKENS = 95  # mesmo valor de modules/ia/agent_graph.py (linha do trim_messages)


def _trim(messages):
    return trim_messages(
        messages,
        strategy="last",
        token_counter=len,
        max_tokens=EDI_59_MAX_TOKENS,
        start_on="human",
        end_on=("human", "tool"),
        include_system=False,
    )


def _historico_alternado(total: int) -> list:
    """Gera `total` mensagens alternando Human/AI, sempre terminando em Human."""
    mensagens = []
    for i in range(total):
        if i % 2 == 0:
            mensagens.append(HumanMessage(content=f"pergunta {i}"))
        else:
            mensagens.append(AIMessage(content=f"resposta {i}"))
    if not isinstance(mensagens[-1], HumanMessage):
        mensagens.append(HumanMessage(content="última pergunta"))
    return mensagens


def test_historico_com_95_mensagens_preserva_todas():
    historico = _historico_alternado(EDI_59_MAX_TOKENS)

    resultado = _trim(historico)

    assert len(resultado) == len(historico)
    assert resultado[0].content == historico[0].content


def test_historico_maior_que_95_corta_mantendo_apenas_as_ultimas():
    historico = _historico_alternado(150)

    resultado = _trim(historico)

    assert len(resultado) <= EDI_59_MAX_TOKENS
    # As mensagens finais do histórico original devem estar presentes no resultado.
    assert resultado[-1].content == historico[-1].content
    # O corte nunca pode começar com uma ToolMessage órfã.
    assert isinstance(resultado[0], HumanMessage)


def test_corte_nunca_comeca_com_tool_message_orfa():
    historico = [
        HumanMessage(content="oi"),
        AIMessage(content="", tool_calls=[{"name": "consultar", "args": {}, "id": "call_1"}]),
        ToolMessage(content="resultado da tool", tool_call_id="call_1"),
        AIMessage(content="aqui está o resultado"),
    ] + _historico_alternado(EDI_59_MAX_TOKENS)

    resultado = _trim(historico)

    assert not isinstance(resultado[0], ToolMessage)

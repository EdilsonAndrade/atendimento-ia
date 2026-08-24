import json
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from modules.ia.thread_session import _summarize_session


class SummarizeSessionToolGroundingTest(unittest.TestCase):
    """EDI-61: o resumidor de sessão não pode persistir uma confirmação de
    agendamento que só existe no texto do Atendente (alucinação), sem uma
    ToolMessage real correspondente no histórico."""

    @patch("modules.ia.agent_graph.llm")
    def test_unfounded_claim_without_tool_message_gets_no_tool_evidence_in_prompt(self, mock_llm):
        # Não dá para testar a decisão semântica do LLM real sem chamá-lo de verdade —
        # este teste garante o que o código efetivamente controla: sem ToolMessage no
        # histórico, nenhuma linha de "Resultado real de ferramenta" é enviada ao LLM,
        # e o prompt do sistema instrui explicitamente a não confiar só no Atendente.
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "resumo": "Cliente tentou agendar.",
                "fatos": {"nome": "Chain", "interesse": None, "objecao": None, "resultado": None},
            })
        )
        messages = [
            HumanMessage(content="Pode ser às 9"),
            AIMessage(content="Tudo certo! Seu horário está reservado."),
        ]

        resultado = _summarize_session(messages)

        mensagens_enviadas = mock_llm.invoke.call_args[0][0]
        system_prompt = mensagens_enviadas[0].content
        conversa_enviada = mensagens_enviadas[1].content

        self.assertNotIn("Resultado real de ferramenta", conversa_enviada)
        self.assertIn("Atendente: Tudo certo! Seu horário está reservado.", conversa_enviada)
        self.assertIn("NUNCA confie apenas na palavra do Atendente", system_prompt)
        self.assertIsNone(resultado["fatos"]["resultado"])

    @patch("modules.ia.agent_graph.llm")
    def test_tool_message_evidence_is_included_as_separate_trusted_line(self, mock_llm):
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({
                "resumo": "Cliente agendou com sucesso.",
                "fatos": {"nome": "Chain", "interesse": None, "objecao": None, "resultado": "Agendamento confirmado"},
            })
        )
        messages = [
            HumanMessage(content="Pode ser às 9"),
            AIMessage(content="Tudo certo! Seu horário está reservado."),
            ToolMessage(
                content="Agendamento confirmado com sucesso no Google Calendar! ID do evento: abc123.",
                tool_call_id="1",
            ),
        ]

        resultado = _summarize_session(messages)

        conversa_enviada = mock_llm.invoke.call_args[0][0][1].content

        self.assertIn("Resultado real de ferramenta", conversa_enviada)
        self.assertIn("ID do evento: abc123", conversa_enviada)
        self.assertEqual(resultado["fatos"]["resultado"], "Agendamento confirmado")

    @patch("modules.ia.agent_graph.llm")
    def test_empty_conversation_short_circuits_without_calling_llm(self, mock_llm):
        resultado = _summarize_session([])

        mock_llm.invoke.assert_not_called()
        self.assertEqual(resultado, {"resumo": "", "fatos": {}})


if __name__ == "__main__":
    unittest.main()

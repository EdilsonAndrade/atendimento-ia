import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from util.time_helpers import get_tabela_dias

import modules.ia.agent_graph as agent_graph


class CalendarReferenceTimezoneTest(unittest.TestCase):
    def test_amanha_respects_brazil_timezone_near_midnight_utc(self):
        reference_now = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)

        tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(
            2,
            reference_now=reference_now,
        )

        self.assertEqual(data_hoje_iso, "2026-08-12")
        self.assertEqual(hora_atual_str, "23:30")
        self.assertIn("Hoje (quarta-feira): 12/08/2026 (ISO: '2026-08-12')", tabela_dias[0])
        self.assertIn("Amanhã (quinta-feira): 13/08/2026 (ISO: '2026-08-13')", tabela_dias[1])


class RespostaSemLastroDeToolTest(unittest.TestCase):
    """EDI-61: cobre a heurística usada tanto pelo operational_node quanto,
    agora, pelo redirecionamento de institutional_node/chitchat_node."""

    def test_confirmation_claim_without_tool_message_triggers_guardrail(self):
        resposta = AIMessage(content="Tudo certo! Seu horário está reservado.")
        historico = [HumanMessage(content="Pode ser às 9")]

        self.assertEqual(
            agent_graph._resposta_sem_lastro_de_tool(resposta, historico),
            "unfounded_claim",
        )

    def test_confirmation_claim_with_recent_tool_message_does_not_trigger(self):
        resposta = AIMessage(content="Tudo certo! Seu horário está reservado.")
        historico = [
            HumanMessage(content="Pode ser às 9"),
            ToolMessage(content="Agendamento confirmado com sucesso.", tool_call_id="1"),
        ]

        self.assertIsNone(agent_graph._resposta_sem_lastro_de_tool(resposta, historico))

    def test_plain_institutional_response_does_not_trigger(self):
        resposta = AIMessage(content="Nosso site é https://interasisai.com.br")

        self.assertIsNone(agent_graph._resposta_sem_lastro_de_tool(resposta, []))


class PreEndGuardrailRouterTest(unittest.TestCase):
    """EDI-61: institutional_node/chitchat_node não vão mais sempre para END —
    uma resposta com cara de confirmação de agenda sem tool real é redirecionada
    para operational_node, que tem as tools de calendário de verdade."""

    @staticmethod
    def _config(tenant_id="1234", thread_id="thread-abc"):
        return {"configurable": {"tenant_id": tenant_id, "thread_id": thread_id}}

    @patch.object(agent_graph, "get_active_tools")
    def test_redirects_to_operational_when_confirmation_without_tool_and_tenant_has_tools(
        self, mock_get_active_tools
    ):
        mock_get_active_tools.return_value = [MagicMock()]
        state = {
            "messages": [
                HumanMessage(content="chain@gmail.com"),
                AIMessage(content="Tudo certo! Seu horário está reservado."),
            ]
        }
        router = agent_graph._make_pre_end_guardrail_router("institutional_node")

        self.assertEqual(router(state, self._config()), "operational_node")

    @patch.object(agent_graph, "get_active_tools")
    def test_ends_when_tenant_has_no_calendar_tools(self, mock_get_active_tools):
        mock_get_active_tools.return_value = []
        state = {
            "messages": [
                HumanMessage(content="chain@gmail.com"),
                AIMessage(content="Tudo certo! Seu horário está reservado."),
            ]
        }
        router = agent_graph._make_pre_end_guardrail_router("institutional_node")

        self.assertEqual(router(state, self._config()), "end")

    @patch.object(agent_graph, "get_active_tools")
    def test_ends_when_response_has_no_confirmation_pattern(self, mock_get_active_tools):
        mock_get_active_tools.return_value = [MagicMock()]
        state = {
            "messages": [
                HumanMessage(content="qual o site da empresa?"),
                AIMessage(content="Nosso site é https://interasisai.com.br"),
            ]
        }
        router = agent_graph._make_pre_end_guardrail_router("chitchat_node")

        self.assertEqual(router(state, self._config()), "end")
        # Curto-circuito: sem guardrail acionado, nem precisa consultar as tools do tenant.
        mock_get_active_tools.assert_not_called()


class RoutingContinuationFallbackTest(unittest.TestCase):
    """EDI-61: o prompt do routing_agent agora permite a saída 'CONTINUATION'.
    Replica a lógica de parsing (mesma de routing_agent) para garantir que essa
    palavra nunca é capturada por engano pelos checks de OPERATIONAL/INSTITUTIONAL/
    CHITCHAT, caindo corretamente no fallback para a intenção anterior."""

    @staticmethod
    def _parse_decisao(decisao_bruta: str, intencao_anterior: str | None) -> str:
        if "OPERATIONAL" in decisao_bruta:
            return "OPERATIONAL"
        elif "INSTITUTIONAL" in decisao_bruta:
            return "INSTITUTIONAL"
        elif "CHITCHAT" in decisao_bruta:
            return "CHITCHAT"
        return intencao_anterior or "INSTITUTIONAL"

    def test_continuation_falls_back_to_previous_operational_intent(self):
        self.assertEqual(
            self._parse_decisao("CONTINUATION", "OPERATIONAL"),
            "OPERATIONAL",
        )

    def test_continuation_falls_back_to_previous_institutional_intent(self):
        self.assertEqual(
            self._parse_decisao("CONTINUATION", "INSTITUTIONAL"),
            "INSTITUTIONAL",
        )

    def test_continuation_without_previous_intent_defaults_to_institutional(self):
        self.assertEqual(self._parse_decisao("CONTINUATION", None), "INSTITUTIONAL")


if __name__ == "__main__":
    unittest.main()
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

    def test_confirmation_claim_matches_real_incident_phrasing(self):
        """EDI-72: 'agendamento FOI confirmado' (frase real vista em produção)
        não batia com o padrão antigo, que exigia adjacência estrita."""
        resposta = AIMessage(content="Seu agendamento foi confirmado com sucesso!")

        self.assertEqual(
            agent_graph._resposta_sem_lastro_de_tool(resposta, []),
            "unfounded_claim",
        )

    def test_cancellation_claim_without_tool_message_triggers_guardrail(self):
        resposta = AIMessage(content="Seu cancelamento foi confirmado com sucesso.")

        self.assertEqual(
            agent_graph._resposta_sem_lastro_de_tool(resposta, []),
            "unfounded_claim",
        )

    def test_reschedule_claim_without_tool_message_triggers_guardrail(self):
        resposta = AIMessage(content="Seu reagendamento foi confirmado com sucesso.")

        self.assertEqual(
            agent_graph._resposta_sem_lastro_de_tool(resposta, []),
            "unfounded_claim",
        )


class PreEndGuardrailRouterTest(unittest.TestCase):
    """EDI-61: institutional_node/chitchat_node não vão mais sempre para END —
    uma resposta com cara de confirmação de agenda sem tool real é redirecionada
    para operational_node, que tem as tools de calendário de verdade."""

    @staticmethod
    def _config(tenant_id="1234", thread_id="thread-abc"):
        return {"configurable": {"tenant_id": tenant_id, "thread_id": thread_id}}

    @patch.object(agent_graph, "get_active_tools")
    def test_redirects_to_calendar_judge_when_confirmation_without_tool_and_tenant_has_tools(
        self, mock_get_active_tools
    ):
        """EDI-72: o destino deixou de ser operational_node direto — agora passa
        por calendar_judge_agent, que verifica de fato contra o Google Calendar
        antes de decidir se libera a resposta ou redireciona para operational_node."""
        mock_get_active_tools.return_value = [MagicMock()]
        state = {
            "messages": [
                HumanMessage(content="chain@gmail.com"),
                AIMessage(content="Tudo certo! Seu horário está reservado."),
            ]
        }
        router = agent_graph._make_pre_end_guardrail_router("institutional_node")

        self.assertEqual(router(state, self._config()), "calendar_judge_agent")

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


class TipoAcaoAlegadaTest(unittest.TestCase):
    """EDI-72: classifica heuristicamente a ação alegada, só para decidir COMO
    verificar (não decide se o guardrail dispara — isso é _resposta_sem_lastro_de_tool)."""

    def test_detects_create_by_default(self):
        self.assertEqual(
            agent_graph._tipo_acao_alegada("Seu agendamento foi confirmado com sucesso!"),
            "create",
        )

    def test_detects_cancel(self):
        self.assertEqual(
            agent_graph._tipo_acao_alegada("Seu cancelamento foi confirmado com sucesso."),
            "cancel",
        )

    def test_detects_reschedule(self):
        self.assertEqual(
            agent_graph._tipo_acao_alegada("Seu reagendamento foi confirmado com sucesso."),
            "reschedule",
        )


class VerificarAcaoCalendarioTest(unittest.TestCase):
    """EDI-72: prova real contra o Google Calendar (tenant_id + telefone + período),
    não mais só a presença de um ToolMessage no estado local."""

    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_create_confirmed_when_event_found(self, mock_tenant_service, mock_calendar_service):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = [{"event_id": "abc"}]

        resultado = agent_graph._verificar_acao_calendario(
            "demo-clinica", "11987654321",
            "2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00", "create",
        )

        self.assertEqual(resultado, "confirmed")
        mock_calendar_service.list_events.assert_called_once_with(
            calendar_id="cal-1",
            start_time="2026-09-03T08:00:00-03:00",
            end_time="2026-09-03T08:30:00-03:00",
            query="11987654321",
            tenant_id="demo-clinica",
            thread_id="unknown",
        )

    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_create_not_confirmed_when_event_not_found(self, mock_tenant_service, mock_calendar_service):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = []

        resultado = agent_graph._verificar_acao_calendario(
            "demo-clinica", "11987654321",
            "2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00", "create",
        )

        self.assertEqual(resultado, "not_confirmed")

    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_cancel_confirmed_when_event_absent(self, mock_tenant_service, mock_calendar_service):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = []

        resultado = agent_graph._verificar_acao_calendario(
            "demo-clinica", "11987654321",
            "2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00", "cancel",
        )

        self.assertEqual(resultado, "confirmed")

    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_cancel_not_confirmed_when_event_still_present(self, mock_tenant_service, mock_calendar_service):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = [{"event_id": "abc"}]

        resultado = agent_graph._verificar_acao_calendario(
            "demo-clinica", "11987654321",
            "2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00", "cancel",
        )

        self.assertEqual(resultado, "not_confirmed")

    def test_missing_phone_fails_extraction(self):
        self.assertEqual(
            agent_graph._verificar_acao_calendario(
                "demo-clinica", None,
                "2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00", "create",
            ),
            "extraction_failed",
        )

    def test_missing_period_fails_extraction(self):
        self.assertEqual(
            agent_graph._verificar_acao_calendario(
                "demo-clinica", "11987654321", None, None, "create",
            ),
            "extraction_failed",
        )


class CalendarJudgeAgentTest(unittest.TestCase):
    """EDI-72: calendar_judge_agent verifica de fato contra o Google Calendar
    antes de liberar (judge_verdict='confirmed') ou redirecionar
    (judge_verdict='redirect') uma resposta sem tool_calls no turno."""

    @staticmethod
    def _config(tenant_id="demo-clinica", thread_id="thread-1"):
        return {"configurable": {"tenant_id": tenant_id, "thread_id": thread_id}}

    @patch.object(agent_graph, "_extrair_periodo_alegado")
    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_redirects_when_event_not_found(
        self, mock_tenant_service, mock_calendar_service, mock_extrair
    ):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = []
        mock_extrair.return_value = ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00")

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "redirect")
        self.assertEqual(resultado["judge_redirect_count"], 1)

    @patch.object(agent_graph, "_extrair_periodo_alegado")
    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_confirms_when_event_found_for_same_phone(
        self, mock_tenant_service, mock_calendar_service, mock_extrair
    ):
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_calendar_service.list_events.return_value = [{"event_id": "abc"}]
        mock_extrair.return_value = ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00")

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "confirmed")
        self.assertEqual(resultado["judge_redirect_count"], 0)

    @patch.object(agent_graph, "_extrair_periodo_alegado")
    @patch.object(agent_graph, "calendar_service")
    @patch.object(agent_graph, "tenant_service")
    def test_does_not_accept_another_customers_event_as_proof(
        self, mock_tenant_service, mock_calendar_service, mock_extrair
    ):
        """spec.md US1, cenário 3: evento do Cliente A não pode servir de prova
        para a confirmação do Cliente B no mesmo tenant/período."""
        mock_tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal-1"}
        mock_extrair.return_value = ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00")

        def _list_events(*, query, **kwargs):
            return [{"event_id": "abc"}] if query == "11900000000" else []

        mock_calendar_service.list_events.side_effect = _list_events

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),  # Cliente B, telefone diferente do A
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "redirect")

    @patch.object(agent_graph, "_verificar_acao_calendario")
    @patch.object(agent_graph, "_extrair_periodo_alegado")
    def test_cancel_redirects_when_event_still_present(self, mock_extrair, mock_verificar):
        mock_extrair.return_value = ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00")
        mock_verificar.return_value = "not_confirmed"

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu cancelamento foi confirmado com sucesso."),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "redirect")
        mock_verificar.assert_called_once()
        self.assertEqual(mock_verificar.call_args.args[4], "cancel")

    @patch.object(agent_graph, "_verificar_acao_calendario")
    @patch.object(agent_graph, "_extrair_periodo_alegado")
    def test_reschedule_confirms_when_old_absent_and_new_present(self, mock_extrair, mock_verificar):
        mock_extrair.side_effect = [
            ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00"),  # antigo
            ("2026-09-04T09:00:00-03:00", "2026-09-04T09:30:00-03:00"),  # novo
        ]
        mock_verificar.side_effect = ["confirmed", "confirmed"]  # antigo ausente, novo presente

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu reagendamento foi confirmado com sucesso."),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "confirmed")
        self.assertEqual(mock_verificar.call_count, 2)
        self.assertEqual(mock_verificar.call_args_list[0].args[4], "cancel")
        self.assertEqual(mock_verificar.call_args_list[1].args[4], "create")

    @patch.object(agent_graph, "_verificar_acao_calendario")
    @patch.object(agent_graph, "_extrair_periodo_alegado")
    def test_reschedule_redirects_when_old_still_present(self, mock_extrair, mock_verificar):
        mock_extrair.side_effect = [
            ("2026-09-03T08:00:00-03:00", "2026-09-03T08:30:00-03:00"),
            ("2026-09-04T09:00:00-03:00", "2026-09-04T09:30:00-03:00"),
        ]
        mock_verificar.side_effect = ["not_confirmed", "confirmed"]  # antigo ainda existe

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu reagendamento foi confirmado com sucesso."),
            ],
            "judge_redirect_count": 0,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "redirect")

    @patch.object(agent_graph, "_verificar_acao_calendario")
    @patch.object(agent_graph, "_extrair_periodo_alegado")
    def test_blocks_with_fallback_after_max_redirects(self, mock_extrair, mock_verificar):
        mock_extrair.return_value = (None, None)
        mock_verificar.return_value = "not_confirmed"

        state = {
            "messages": [
                HumanMessage(content="Telefone: 11987654321"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ],
            "judge_redirect_count": agent_graph.JUDGE_MAX_REDIRECTS,
        }

        resultado = agent_graph.calendar_judge_agent(state, self._config())

        self.assertEqual(resultado["judge_verdict"], "blocked")
        self.assertEqual(resultado["judge_redirect_count"], 0)
        self.assertEqual(len(resultado["messages"]), 1)
        self.assertIn("tive um problema", resultado["messages"][0].content)


class OperationalOutputRouterTest(unittest.TestCase):
    """EDI-72: operational_node não vai mais direto para END quando não há
    tool_calls pendentes — passa por calendar_judge_agent quando a resposta tem
    cara de confirmação sem lastro."""

    @staticmethod
    def _config(tenant_id="demo-clinica"):
        return {"configurable": {"tenant_id": tenant_id, "thread_id": "thread-1"}}

    def test_routes_to_tools_when_pending_tool_calls(self):
        state = {
            "messages": [
                HumanMessage(content="amanhã às 8"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "agendar_horario", "args": {}, "id": "1"}],
                ),
            ]
        }

        self.assertEqual(agent_graph._operational_output_router(state, self._config()), "tools")

    def test_routes_to_end_when_no_pending_tool_calls_and_no_confirmation_pattern(self):
        state = {
            "messages": [
                HumanMessage(content="qual dia você prefere?"),
                AIMessage(content="Qual dia você prefere, segunda ou quarta?"),
            ]
        }

        self.assertEqual(
            agent_graph._operational_output_router(state, self._config()), "end"
        )

    @patch.object(agent_graph, "get_active_tools")
    def test_routes_to_judge_when_confirmation_without_tool_calls(self, mock_get_active_tools):
        mock_get_active_tools.return_value = [MagicMock()]
        state = {
            "messages": [
                HumanMessage(content="sim"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ]
        }

        self.assertEqual(
            agent_graph._operational_output_router(state, self._config()), "calendar_judge_agent"
        )

    @patch.object(agent_graph, "get_active_tools")
    def test_routes_to_end_when_tenant_has_no_active_tools(self, mock_get_active_tools):
        mock_get_active_tools.return_value = []
        state = {
            "messages": [
                HumanMessage(content="sim"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ]
        }

        self.assertEqual(
            agent_graph._operational_output_router(state, self._config()), "end"
        )

    @patch.object(agent_graph, "get_logger")
    @patch.object(agent_graph, "get_active_tools")
    def test_logs_calendar_guardrail_redirect_when_routing_to_judge(
        self, mock_get_active_tools, mock_get_logger
    ):
        """Rastreabilidade (EDI-72): o disparo do juiz a partir de operational_node
        precisa ficar registrado com a MESMA tag [CALENDAR_GUARDRAIL_REDIRECT] já
        usada pelo redirecionamento de institutional_node/chitchat_node (EDI-61),
        para que um grep único encontre o gatilho independente de qual nó chamou."""
        mock_get_active_tools.return_value = [MagicMock()]
        mock_logger_instance = MagicMock()
        mock_get_logger.return_value = mock_logger_instance
        state = {
            "messages": [
                HumanMessage(content="sim"),
                AIMessage(content="Seu agendamento foi confirmado com sucesso!"),
            ]
        }

        resultado = agent_graph._operational_output_router(state, self._config())

        self.assertEqual(resultado, "calendar_judge_agent")
        mock_logger_instance.warn.assert_called_once()
        _, kwargs = mock_logger_instance.warn.call_args
        self.assertIn("Calendar guardrail redirect", kwargs["message"])
        self.assertEqual(kwargs["extra"]["redirected_to"], "calendar_judge_agent")


class PostJudgeRouterTest(unittest.TestCase):
    """EDI-72: aresta condicional pós calendar_judge_agent, lida com o veredito
    que o próprio nó gravou no state (não recalcula nada)."""

    def test_redirects_when_verdict_is_redirect(self):
        self.assertEqual(
            agent_graph._post_judge_router({"judge_verdict": "redirect"}), "operational_node"
        )

    def test_ends_when_verdict_is_confirmed(self):
        self.assertEqual(agent_graph._post_judge_router({"judge_verdict": "confirmed"}), "end")

    def test_ends_when_verdict_is_blocked(self):
        self.assertEqual(agent_graph._post_judge_router({"judge_verdict": "blocked"}), "end")


if __name__ == "__main__":
    unittest.main()
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from util.ai_helpers import (
    should_block_unverified_booking_response,
    should_retry_booking_tool_call,
)


class BookingGuardTest(unittest.TestCase):
    def test_retry_and_block_when_user_already_confirmed_but_no_tool_was_called(self):
        messages = [
            AIMessage(content="Perfeito! Vou confirmar os dados do agendamento. Posso confirmar esse agendamento?"),
            HumanMessage(content="sim"),
        ]
        response = AIMessage(content="Agendamento confirmado com sucesso para amanha as 11h.")

        self.assertTrue(should_retry_booking_tool_call(messages, response))
        self.assertTrue(should_block_unverified_booking_response(messages, response))

    def test_do_not_block_after_successful_booking_tool_result(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-1", "name": "agendar_horario", "args": {}}
                ],
            ),
            ToolMessage(
                content="Agendamento confirmado com sucesso no Google Calendar! ID do evento: evt-123.",
                tool_call_id="call-1",
                name="agendar_horario",
            ),
        ]
        response = AIMessage(content="Agendamento confirmado com sucesso. Seu horario esta reservado.")

        self.assertFalse(should_retry_booking_tool_call(messages, response))
        self.assertFalse(should_block_unverified_booking_response(messages, response))

    def test_do_not_trigger_guard_for_regular_operational_question(self):
        messages = [HumanMessage(content="quais horarios tem amanha?")]
        response = AIMessage(content="Tenho alguns horarios disponiveis na parte da tarde.")

        self.assertFalse(should_retry_booking_tool_call(messages, response))
        self.assertFalse(should_block_unverified_booking_response(messages, response))


if __name__ == "__main__":
    unittest.main()
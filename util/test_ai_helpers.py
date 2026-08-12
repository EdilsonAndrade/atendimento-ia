import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from util.ai_helpers import (
    build_booking_retry_context_block,
    should_block_unverified_availability_response,
    should_retry_availability_tool_call,
    should_block_unverified_booking_response,
    should_retry_booking_tool_call,
    user_is_asking_for_availability,
    user_selected_booking_slot,
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

    def test_retry_and_block_when_availability_is_claimed_without_consulting_calendar(self):
        messages = [HumanMessage(content="tem certeza que das 14 as 15 esta ocupado amanha?")]
        response = AIMessage(content="Sim, o horario das 14h as 15h esta ocupado.")

        self.assertTrue(should_retry_availability_tool_call(messages, response))
        self.assertTrue(should_block_unverified_availability_response(messages, response))

    def test_do_not_block_after_successful_availability_tool_result(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-2", "name": "consultar_agenda", "args": {}}
                ],
            ),
            ToolMessage(
                content="A agenda de amanha esta ocupada entre 14h e 15h.",
                tool_call_id="call-2",
                name="consultar_agenda",
            ),
        ]
        response = AIMessage(content="Sim, o horario das 14h as 15h esta ocupado.")

        self.assertFalse(should_retry_availability_tool_call(messages, response))
        self.assertFalse(should_block_unverified_availability_response(messages, response))

    def test_booking_retry_context_includes_selected_slot_and_last_availability_result(self):
        messages = [
            AIMessage(content="Qual horario seria melhor para voce? 10h, 14h ou 16h?"),
            HumanMessage(content="ok pode ser pras 10"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-3", "name": "consultar_agenda", "args": {}}
                ],
            ),
            ToolMessage(
                content="A agenda de amanha esta livre entre 10h e 11h.",
                tool_call_id="call-3",
                name="consultar_agenda",
            ),
        ]

        block = build_booking_retry_context_block(messages, {"nome": "Maria", "email": "maria@email.com"})

        self.assertIn("ok pode ser pras 10", block)
        self.assertIn("A agenda de amanha esta livre entre 10h e 11h.", block)
        self.assertIn("Maria", block)
        self.assertIn("maria@email.com", block)

    def test_slot_selection_is_booking_intent_not_availability(self):
        messages = [
            AIMessage(content="Qual horario seria melhor para voce? 10h, 14h ou 16h?"),
            HumanMessage(content="ok pode ser pras 10"),
        ]
        response = AIMessage(content="Perfeito, vou verificar o horario das 10h.")

        self.assertTrue(user_selected_booking_slot(messages))
        self.assertFalse(user_is_asking_for_availability(messages))
        self.assertTrue(should_retry_booking_tool_call(messages, response))
        self.assertFalse(should_retry_availability_tool_call(messages, response))
        self.assertFalse(should_block_unverified_availability_response(messages, response))

    def test_block_existing_appointment_claim_pulled_from_history(self):
        # Usuario pediu para agendar um slot (nao "pergunta de disponibilidade"),
        # mas a IA afirma um agendamento existente sem consultar o calendario neste turno.
        messages = [HumanMessage(content="poderia agendar pra amanha as 12 servico de consultoria?")]
        response = AIMessage(content=(
            "Infelizmente o horario das 12:00 esta ocupado. "
            "Voce ja tem um agendamento para as 14:00 nesse mesmo dia."
        ))

        self.assertTrue(should_retry_availability_tool_call(messages, response))
        self.assertTrue(should_block_unverified_availability_response(messages, response))

    def test_do_not_block_calendar_summary_after_google_style_tool_result(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-9", "name": "consultar_agenda", "args": {}}
                ],
            ),
            ToolMessage(
                content="Eventos encontrados na agenda:\n- ID: evt-1 | Titulo: Reuniao | Inicio: 2026-08-13T14:00:00-03:00 | Fim: 2026-08-13T15:00:00-03:00",
                tool_call_id="call-9",
                name="consultar_agenda",
            ),
        ]
        response = AIMessage(content="O horario das 14h esta ocupado, mas as 10h esta livre.")

        self.assertFalse(should_retry_availability_tool_call(messages, response))
        self.assertFalse(should_block_unverified_availability_response(messages, response))

    def test_block_when_availability_tool_returned_error(self):
        messages = [
            HumanMessage(content="tem horario amanha as 14?"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call-10", "name": "consultar_agenda", "args": {}}
                ],
            ),
            ToolMessage(
                content="Erro: O tenant nao possui um Google Calendar ID configurado.",
                tool_call_id="call-10",
                name="consultar_agenda",
            ),
        ]
        response = AIMessage(content="O horario das 14h esta livre.")

        self.assertTrue(should_block_unverified_availability_response(messages, response))


if __name__ == "__main__":
    unittest.main()
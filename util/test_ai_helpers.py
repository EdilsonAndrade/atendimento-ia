import unittest

from langchain_core.messages import AIMessage, HumanMessage

from util.ai_helpers import (
    build_customer_context_block,
    extract_customer_profile,
)


class CustomerProfileExtractionTest(unittest.TestCase):
    """Regressão do bug: 'Nome: Aline' vazando pro KNOWN CUSTOMER CONTEXT a partir
    da fala da propria assistente, quase confirmando um agendamento com dado errado."""

    def test_assistant_self_introduction_never_contaminates_customer_name(self):
        messages = [
            AIMessage(content="Ola! Meu nome é Aline, sua assistente virtual. Como posso ajudar?"),
            HumanMessage(content="quero agendar um horario"),
        ]

        profile = extract_customer_profile(messages)

        self.assertIsNone(profile["nome"])
        self.assertNotIn("Nome: Aline", build_customer_context_block(profile))

    def test_assistant_repeating_email_or_phone_never_contaminates_profile(self):
        messages = [
            AIMessage(content="Perfeito, vou usar o email suporte@aline-bot.com e o telefone 11000000000 aqui."),
            HumanMessage(content="ok, pode confirmar"),
        ]

        profile = extract_customer_profile(messages)

        self.assertIsNone(profile["email"])
        self.assertIsNone(profile["telefone"])

    def test_customer_message_is_still_captured_normally(self):
        messages = [
            AIMessage(content="Ola! Meu nome é Aline, sua assistente virtual."),
            HumanMessage(content="Meu nome é Joao, meu email é joao@teste.com, telefone 11999998888"),
        ]

        profile = extract_customer_profile(messages)

        self.assertEqual(profile["nome"], "Joao")
        self.assertEqual(profile["email"], "joao@teste.com")
        self.assertEqual(profile["telefone"], "11999998888")

        block = build_customer_context_block(profile)
        self.assertIn("Nome: Joao", block)
        self.assertNotIn("Aline", block)


if __name__ == "__main__":
    unittest.main()

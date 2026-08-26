import pytest

from modules.conversation_history.domain.conversation_message import ConversationMessage


def test_role_human_e_ai_sao_aceitos():
    ConversationMessage(
        tenant_id="acme", base_thread_id="acme:123", active_thread_id="acme:123#abc",
        role="human", content="oi",
    )
    ConversationMessage(
        tenant_id="acme", base_thread_id="acme:123", active_thread_id="acme:123#abc",
        role="ai", content="olá!",
    )


def test_role_invalido_levanta_value_error():
    with pytest.raises(ValueError):
        ConversationMessage(
            tenant_id="acme", base_thread_id="acme:123", active_thread_id="acme:123#abc",
            role="tool", content="qualquer coisa",
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

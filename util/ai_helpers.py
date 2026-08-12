from langchain.messages import AIMessage, ToolMessage


def sanitize_history_messages(messages: list) -> list:
    # 1. Mapeia todos os IDs de ToolMessages que realmente existem no histórico
    tool_msg_ids = {
        m.tool_call_id 
        for m in messages 
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None)
    }
    
    # 2. Mapeia todos os IDs de tool_calls que foram solicitados por AIMessages
    ai_tc_ids = {
        tc["id"]
        for m in messages
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        for tc in m.tool_calls
    }
    
    sanitized = []
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            # Filtra na AIMessage apenas os tool_calls que REALMENTE foram respondidos por uma ToolMessage no histórico
            valid_tcs = [tc for tc in m.tool_calls if tc.get("id") in tool_msg_ids]
            
            # Cria uma cópia da AIMessage apenas com os tool_calls respondidos
            m_copy = m.model_copy() if hasattr(m, "model_copy") else m
            m_copy.tool_calls = valid_tcs
            
            if hasattr(m_copy, "additional_kwargs") and "tool_calls" in m_copy.additional_kwargs:
                m_copy.additional_kwargs["tool_calls"] = [
                    tc for tc in m_copy.additional_kwargs["tool_calls"]
                    if tc.get("id") in {vtc["id"] for vtc in valid_tcs}
                ]
            sanitized.append(m_copy)
            
        elif isinstance(m, ToolMessage):
            # Só mantém a ToolMessage no histórico se a AIMessage 'pai' dela ainda existir no corte
            if getattr(m, "tool_call_id", None) in ai_tc_ids:
                sanitized.append(m)
        else:
            sanitized.append(m)
            
    return sanitized


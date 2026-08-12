import copy
from langchain_core.messages import AIMessage, ToolMessage


# ============================================================================
# ALGORITMO DEFINITIVO DE BLINDAGEM DE HISTÓRICO (STRICT SEQUENCE)
# ============================================================================
def sanitize_for_openai_strict_format(messages: list) -> list:
    """
    Garante a ordem estrita exigida pela API: 
    Toda AIMessage com tool_calls DEVE ser seguida imediatamente pelas suas ToolMessages.
    Qualquer interrupção (ex: usuário mandar mensagem no meio) ou ferramenta órfã é expurgada.
    Impede o envio de AIMessages vazias.
    """
    safe_messages = []
    i = 0
    
    while i < len(messages):
        m = messages[i]
        
        # 1. Se a IA chamou uma ferramenta...
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            j = i + 1
            tool_responses = []
            
            # 2. Olha para a frente: captura APENAS as ToolMessages que vieram coladas logo em seguida
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_responses.append(messages[j])
                j += 1
            
            # 3. Verifica quais tool_calls dessa mensagem realmente estão no bloco colado a ela
            found_ids = {tm.tool_call_id for tm in tool_responses}
            valid_tcs = [tc for tc in m.tool_calls if tc["id"] in found_ids]
            
            # 4. Reconstrói a mensagem da IA de forma segura
            if valid_tcs:
                m_copy = copy.deepcopy(m)
                m_copy.tool_calls = valid_tcs
                if hasattr(m_copy, "additional_kwargs") and "tool_calls" in m_copy.additional_kwargs:
                    m_copy.additional_kwargs["tool_calls"] = [
                        tc for tc in m_copy.additional_kwargs["tool_calls"]
                        if tc.get("id") in found_ids
                    ]
                safe_messages.append(m_copy)
                safe_messages.extend(tool_responses)
            else:
                # 5. Se as ferramentas foram cortadas, mantemos a mensagem APENAS se ela tiver texto.
                # Se for vazia, nós a destruímos completamente para evitar o Erro 400.
                if m.content:
                    m_copy = copy.deepcopy(m)
                    m_copy.tool_calls = []
                    if hasattr(m_copy, "additional_kwargs") and "tool_calls" in m_copy.additional_kwargs:
                        del m_copy.additional_kwargs["tool_calls"]
                    safe_messages.append(m_copy)
            
            i = j  # Avança o ponteiro pulando as ToolMessages que já inserimos
            
        elif isinstance(m, ToolMessage):
            # 6. Se acharmos uma ToolMessage solta (sem estar atrelada a uma AIMessage), ela é órfã. Destruir.
            i += 1
            
        elif isinstance(m, AIMessage) and not m.content and not getattr(m, "tool_calls", None):
            # 7. Se for uma AIMessage 100% vazia (sem texto e sem ferramentas), destruir.
            i += 1
            
        else:
            # 8. Mensagens normais (HumanMessage, SystemMessage ou AIMessage só com texto) passam livremente.
            safe_messages.append(m)
            i += 1
            
    return safe_messages
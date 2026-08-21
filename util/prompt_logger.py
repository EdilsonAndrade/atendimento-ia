# util/prompt_logger.py
"""
Log do prompt completo enviado ao LLM em cada nó do grafo.

Usa um marcador único (PROMPT_LOG_MARKER) para que seja possível filtrar
essas linhas no meio do volume geral de logs, ex:

    docker logs -f <container> | grep "LLM_PROMPT_TRACE"
"""
from langchain_core.messages import BaseMessage

PROMPT_LOG_MARKER = "###LLM_PROMPT_TRACE###"


def log_llm_prompt(node_name: str, tenant_id: str, prompt) -> None:
    """
    Imprime no stdout o prompt exato que será enviado ao LLM, delimitado por
    um marcador fixo (PROMPT_LOG_MARKER) para facilitar a busca no log.

    Aceita tanto uma string simples (ex: institutional_node) quanto uma lista
    de BaseMessage (ex: routing_agent, operational_node, chitchat_node).
    """
    print(f"\n{PROMPT_LOG_MARKER} INÍCIO node={node_name} tenant_id={tenant_id} {PROMPT_LOG_MARKER}")

    if isinstance(prompt, str):
        print(f"{PROMPT_LOG_MARKER} [SYSTEM/PROMPT STRING]\n{prompt}")
    elif isinstance(prompt, (list, tuple)):
        for i, msg in enumerate(prompt):
            if isinstance(msg, BaseMessage):
                tipo = msg.type
                conteudo = msg.content
            else:
                tipo = type(msg).__name__
                conteudo = msg
            print(f"{PROMPT_LOG_MARKER} [{i}] role={tipo} content={conteudo!r}")
    else:
        print(f"{PROMPT_LOG_MARKER} [PROMPT] {prompt!r}")

    print(f"{PROMPT_LOG_MARKER} FIM node={node_name} tenant_id={tenant_id} {PROMPT_LOG_MARKER}\n")

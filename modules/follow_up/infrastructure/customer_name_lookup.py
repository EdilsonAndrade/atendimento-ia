"""Busca best-effort do nome do cliente para exibição na fila de follow-up (EDI-65).

Fonte: `chat_thread_summaries.fatos_estruturados->>'nome'`, populado pela mesma
classificação de fechamento de sessão que já gera resumo/fatos (EDI-59/61) — nunca
inventado aqui. Chama o método público já existente do módulo legado `modules.ia`
(Política de Migração Legada: nunca acessa a tabela diretamente daqui).
"""
from modules.ia.thread_session import get_latest_session_summary


def get_customer_name(base_thread_id: str) -> str | None:
    summary = get_latest_session_summary(base_thread_id)
    if not summary:
        return None
    nome = (summary.get("fatos") or {}).get("nome")
    return nome if isinstance(nome, str) and nome.strip() else None

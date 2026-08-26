"""Adapter que chama o LLM já configurado do projeto para classificar `outcome` +
gerar `summary`/`fatos`/`draft_message` de uma sessão fechada (EDI-53).

Reaproveita a MESMA chamada de LLM que antes só gerava resumo/fatos em
`modules/ia/thread_session.py::_summarize_session` (EDI-59/61) — ver
specs/011-conversation-history-followup/research.md §1. Import do `llm` é feito
dentro do método (não no topo do módulo) para evitar import circular com
`modules.ia.agent_graph`, mesmo padrão já usado em `thread_session.py`.
"""
import json
from datetime import date


class LlmSessionOutcomeClassifier:
    def classify(
        self,
        conversation_text: str,
        oferta_vigente_texto: str | None,
        oferta_vigente_validade: date | None,
    ) -> dict:
        from langchain_core.messages import HumanMessage, SystemMessage
        from modules.ia.agent_graph import llm
        from modules.follow_up.domain.oferta_vigente import is_oferta_vigente

        oferta_bloco = ""
        if is_oferta_vigente(oferta_vigente_texto, oferta_vigente_validade, date.today()):
            oferta_bloco = (
                f"\n\nOFERTA VIGENTE DESTE TENANT (só pode citar EXATAMENTE este texto, se fizer "
                f"sentido no rascunho de follow-up): {oferta_vigente_texto!r}"
            )
        else:
            oferta_bloco = (
                "\n\nESTE TENANT NÃO TEM NENHUMA OFERTA/DESCONTO VIGENTE. O 'draft_message' NUNCA "
                "PODE mencionar desconto, promoção ou condição comercial de nenhum tipo."
            )

        prompt = SystemMessage(content=(
            "Resuma a conversa de atendimento abaixo em até 3 frases curtas (~200 tokens no total). "
            "Depois, extraia em JSON os campos: nome, interesse, objecao, resultado. "
            "Use null para qualquer campo que não puder ser identificado com base real na conversa — "
            "NUNCA invente ou suponha um valor.\n\n"
            "REGRA CRÍTICA SOBRE O CAMPO 'resultado': as linhas do 'Atendente' são texto gerado por um "
            "modelo de linguagem e PODEM alegar uma confirmação/cancelamento de agendamento que nunca "
            "aconteceu de verdade. As linhas 'Resultado real de ferramenta' são a ÚNICA fonte confiável "
            "sobre o que de fato aconteceu no calendário. Só preencha 'resultado' com um agendamento "
            "confirmado/cancelado se houver uma linha 'Resultado real de ferramenta' correspondente que "
            "comprove isso. Se o Atendente alegou uma confirmação mas não há nenhuma linha de 'Resultado "
            "real de ferramenta' comprovando, use null para 'resultado' — NUNCA confie apenas na palavra "
            "do Atendente para esse campo.\n\n"
            "Além disso, classifique um campo 'outcome' com EXATAMENTE um destes valores: "
            "'fechado' (agendamento confirmado/cancelado com respaldo real de ferramenta), "
            "'pensando' (cliente demonstrou interesse mas não decidiu), "
            "'sem_resposta' (cliente parou de responder sem concluir), "
            "'recusado' (cliente recusou explicitamente), "
            "'em_andamento' (conversa ainda não chegou a um desfecho claro). "
            "'outcome' só pode ser 'fechado' se houver uma linha 'Resultado real de ferramenta' "
            "comprovando — NUNCA classifique como 'fechado' com base só na fala do Atendente.\n\n"
            "Por fim, quando (e SOMENTE quando) 'outcome' for 'pensando' ou 'sem_resposta', gere um "
            "campo 'draft_message': um rascunho curto e personalizado de mensagem de follow-up para "
            "reengajar o cliente (use o nome do cliente se identificado). Para qualquer outro "
            "'outcome', 'draft_message' DEVE ser null." + oferta_bloco + "\n\n"
            "Responda ESTRITAMENTE em JSON, no formato: "
            '{"resumo": "...", "fatos": {"nome": null, "interesse": null, "objecao": null, '
            '"resultado": null}, "outcome": "...", "draft_message": null}'
        ))
        resposta = llm.invoke([prompt, HumanMessage(content=conversation_text)])
        dados = json.loads(resposta.content)
        return {
            "resumo": str(dados.get("resumo") or ""),
            "fatos": dados.get("fatos") or {},
            "outcome": dados.get("outcome"),
            "draft_message": dados.get("draft_message"),
        }

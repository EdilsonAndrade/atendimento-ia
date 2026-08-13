# ============================================================================
# LINHAS DE ALTERAÇÃO - IMPORTAÇÕES DE DATA E MENSAGENS
# ============================================================================
from datetime import datetime, timezone
import time
import unicodedata
from langchain.agents import AgentState
from langchain_core.messages import AIMessage, HumanMessage

# ============================================================================
# LINHAS DE ALTERAÇÃO - NÓS AUXILIARES E ROTEADOR DE HANDOVER
# ============================================================================
def remover_acentos(texto: str) -> str:
    """Remove acentos e converte para minúsculas (ex: 'alguém' vira 'alguem')."""
    if not texto:
        return ""
    texto_normalizado = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in texto_normalizado if not unicodedata.combining(c)]).lower().strip()
    
def node_iniciar_transbordo(state: AgentState):
    """
    NÓ 1: Chamado quando o usuário pede para falar com humano.
    Ativa a flag de pausa da IA e devolve a resposta informativa com contato do prompt.
    """
    
    print("\n🟢 [DEBUG NÓ] Executando node_iniciar_transbordo! Gravando is_human_active=True")
    
    # Texto informativo (Você pode buscar esses dados direto da config do tenant)
    mensagem_transbordo = (
        "Certo! Estou transferindo você para o nosso atendimento humano.\n\n"
        "Enquanto um atendente assume, a IA ficará pausada.\n"
        "Se quiser voltar a falar comigo a qualquer momento, digite **#VOLTAR**."
    )
    
    return {
        "is_human_active": True,
        "last_message_at": time.time(), # Usa timestamp em segundos (float)
        "messages": [AIMessage(content=mensagem_transbordo)]
    }


def node_humano_standby(state: AgentState):
    """
    NÓ 2: Chamado se o cliente mandar mensagem MENTRAS o humano estiver atendendo.
    A IA entra em silêncio (não chama LLM) e apenas atualiza o horário da mensagem.
    """
    return {
        "is_human_active": True,
        "last_message_at": time.time(),
        "messages": [AIMessage(content="[ATENDIMENTO_HUMANO_ATIVO]")]
    }

def node_reativar_ia(state: AgentState):
    """NÓ 3: Desativa o modo humano no banco de dados e avisa a reativação da IA."""
    return {
        "is_human_active": False,
        "messages": [AIMessage(content="Atendimento automatizado reativado! Como posso ajudar você agora?")]
    }


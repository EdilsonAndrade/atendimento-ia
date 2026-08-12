# app/api/v1/endpoints/chat.py
import logging
import asyncio
import os
from fastapi import APIRouter, Header, status, HTTPException
from langchain_core.messages import HumanMessage
from app.schemas.chat import MessageRequest, ChatResponse
from modules.ia.agent_graph import get_compiled_graph

logger = logging.getLogger(__name__)
router = APIRouter()

MESSAGE_PROCESSING_GAP_SECONDS = float(os.getenv("CHAT_MESSAGE_GAP_SECONDS", "5.0"))
_chat_locks: dict[str, asyncio.Lock] = {}
_chat_last_finished_at: dict[str, float] = {}


def _invoke_graph(graph_app, estado_inicial, configuracao_requisicao):
    if graph_app is None:
        raise ValueError("O grafo compilado não foi inicializado corretamente.")

    invoke_fn = getattr(graph_app, "invoke", None)
    if invoke_fn is None:
        raise ValueError("O grafo compilado não expõe o método invoke().")

    return invoke_fn(estado_inicial, configuracao_requisicao)


# Instanciamos o grafo compilado com o PostgresSaver UMA ÚNICA VEZ (Singleton)
# Isso mantém a conexão/checkpointer ativos para recuperar o histórico entre requisições
try:
    graph_app = get_compiled_graph()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar o grafo com PostgresSaver: {e}")
    graph_app = None

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK, summary="Interagir com o Agente de IA")
async def chat_interaction(request: MessageRequest, tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")):
    """
    Dispara um fluxo de conversa dentro do Grafo de Estados (LangGraph).
    O roteamento de intenção e a conexão com os arquivos vetoriais do cliente
    são estabelecidos dinamicamente a partir do ID do tenant, que pode vir
    por header (WhatsApp/integrações) ou pelo próprio corpo da requisição
    quando a origem é uma plataforma como o site.
    A memória é persistida no PostgreSQL por meio do PostgresSaver.
    """
    tenant_id = tenant_id or request.tenant_id

    if not tenant_id or not str(tenant_id).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="É obrigatório informar o tenant. Envie o cabeçalho X-Tenant-ID ou o campo tenant_id no corpo da requisição."
        )

    estado_inicial = {
        "messages": [HumanMessage(content=request.message)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }
    
    # Enviamos o tenant_id (para o RAG) e o thread_id (para o PostgresSaver)
    thread_id_sessao = request.thread_id or f"tenant_{tenant_id}_default"
    conversation_key = f"{tenant_id}:{thread_id_sessao}"
    conversation_lock = _chat_locks.setdefault(conversation_key, asyncio.Lock())
    
    configuracao_requisicao = {
        "configurable": {
            "tenant_id": tenant_id,
            "thread_id": thread_id_sessao
        }
    }
    
    try:
        # O lock é por conversa e não por tenant: clientes diferentes do mesmo tenant
        # podem processar mensagens em paralelo sem bloquear um ao outro.
        async with conversation_lock:
            now = asyncio.get_running_loop().time()
            last_finished_at = _chat_last_finished_at.get(conversation_key)
            if last_finished_at is not None:
                elapsed = now - last_finished_at
                remaining = MESSAGE_PROCESSING_GAP_SECONDS - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)

            # Puxamos o grafo compilado com o PostgresSaver.
            # O invoke é bloqueante (LLM + Postgres), então roda em uma thread separada
            # para não travar o event loop enquanto atende outras requisições.
            async with asyncio.timeout(40.0):
                result = await asyncio.to_thread(
                    _invoke_graph, graph_app, estado_inicial, configuracao_requisicao
                )

            resposta_final = result["messages"][-1].content
            _chat_last_finished_at[conversation_key] = asyncio.get_running_loop().time()

        return ChatResponse(
            tenant_id=tenant_id,
            status="success",
            response=resposta_final
        )
    except TimeoutError:
        logger.error(
            f"❌ [TIMEOUT] O processamento da mensagem estourou o tempo limite para a thread {request.thread_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="O serviço de atendimento demorou muito para responder. Por favor, tente novamente.",
        )
    except Exception as ex:
        # Log detalhado do erro no servidor para monitoramento interno
        logger.error(
            f"❌ [AGENT ERROR] Falha inesperada no processamento da thread {request.thread_id}: {str(ex)}",
            exc_info=True,
        )

        # Retorno amigável em JSON sem expor stack traces sensíveis de banco/código para o cliente
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro interno ao processar sua solicitação no Atendimento de IA. Nossa equipe já foi notificada.",
        )
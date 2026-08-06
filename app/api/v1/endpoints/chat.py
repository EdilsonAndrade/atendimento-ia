# app/api/v1/endpoints/chat.py
import logging
import asyncio
from fastapi import APIRouter, Depends, status, HTTPException
from langchain_core.messages import HumanMessage
from app.api.deps import get_tenant_id
from app.schemas.chat import MessageRequest, ChatResponse
from modules.ia.agent_graph import get_compiled_graph

logger = logging.getLogger(__name__)
router = APIRouter()

# Instanciamos o grafo compilado com o PostgresSaver UMA ÚNICA VEZ (Singleton)
# Isso mantém a conexão/checkpointer ativos para recuperar o histórico entre requisições
try:
    graph_app = get_compiled_graph()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar o grafo com PostgresSaver: {e}")
    graph_app = None

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK, summary="Interagir com o Agente de IA")
async def chat_interaction(request: MessageRequest, tenant_id: str = Depends(get_tenant_id)):
    """
    Dispara um fluxo de conversa dentro do Grafo de Estados (LangGraph).
    O roteamento de intenção e a conexão com os arquivos vetoriais do cliente
    são estabelecidos dinamicamente a partir do ID injetado pelo Header.
    A memória é persistida no PostgreSQL por meio do PostgresSaver.
    """
    estado_inicial = {
        "messages": [HumanMessage(content=request.message)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }
    
    # Enviamos o tenant_id (para o RAG) e o thread_id (para o PostgresSaver)
    thread_id_sessao = request.thread_id or f"tenant_{tenant_id}_default"
    
    configuracao_requisicao = {
        "configurable": {
            "tenant_id": tenant_id,
            "thread_id": thread_id_sessao
        }
    }
    
    try:
        # Puxamos o grafo compilado com o PostgresSaver
        # O LangGraph busca o histórico no Postgres automaticamente antes de rodar
        async with asyncio.timeout(40.0):
            result = await asyncio.to_thread(
            graph_app.invoke, 
            estado_inicial, 
            configuracao_requisicao
        )
        resposta_final = result["messages"][-1].content
        
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
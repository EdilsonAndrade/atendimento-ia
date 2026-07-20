# Endpoints de Mensageria (Nossos nós/grafo)
from fastapi import APIRouter, Depends, status
from langchain_core.messages import HumanMessage
from app.api.deps import get_tenant_id
from app.schemas.chat import MessageRequest, ChatResponse
from modules.ia.agent_graph import app as graph_app


router = APIRouter()

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK, summary="Interagir com o Agente de IA")
async def chat_interaction(request: MessageRequest, tenant_id: str = Depends(get_tenant_id)):
    """
    Dispara um fluxo de conversa dentro do Grafo de Estados (LangGraph).
    O roteamento de intenção e a conexão com os arquivos vetoriais do cliente
    são estabelecidos dinamicamente a partir do ID injetado pelo Header.
    """
    estado_inicial = {
        "messages": [HumanMessage(content=request.message)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }
    
    configuracao_requisicao = {
        "configurable": {
            "tenant_id": tenant_id
        }
    }
    
    result = graph_app.invoke(estado_inicial, configuracao_requisicao)
    resposta_final = result["messages"][-1].content
    
    return ChatResponse(
        tenant_id=tenant_id,
        status="success",
        response=resposta_final
    )
    
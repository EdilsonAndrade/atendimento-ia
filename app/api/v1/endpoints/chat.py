# app/api/v1/endpoints/chat.py
import asyncio
import logging
import os
import jwt
from fastapi import APIRouter, Request, status, HTTPException, Header, Depends
from langchain_core.messages import HumanMessage
from app.schemas.chat import MessageRequest, ChatResponse
from modules.ia.agent_graph import get_compiled_graph
from modules.ia.thread_session import resolve_active_thread_id
logger = logging.getLogger(__name__)
router = APIRouter()
from modules.token.token_verify import verificar_token
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from modules.tenant.tenant_service import TenantService
from app.core.limiter import limiter
SECRET_KEY = os.getenv("SECRET_KEY", "mudar_senha_123")
ALGORITHM = os.getenv("ALGORITHM", "HS256")


MESSAGE_PROCESSING_GAP_SECONDS = float(os.getenv("CHAT_MESSAGE_GAP_SECONDS", "5.0"))
_chat_locks: dict[str, asyncio.Lock] = {}
_chat_last_finished_at: dict[str, float] = {}





# Instanciamos o grafo compilado com o PostgresSaver UMA ÚNICA VEZ (Singleton)
# Isso mantém a conexão/checkpointer ativos para recuperar o histórico entre requisições
try:
    graph_app = get_compiled_graph()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar o grafo com PostgresSaver: {e}")
    graph_app = None
    

def _invoke_graph(graph_app, estado_inicial, configuracao_requisicao):
    if graph_app is None:
        raise ValueError("O grafo compilado não foi inicializado corretamente.")

    invoke_fn = getattr(graph_app, "invoke", None)
    if invoke_fn is None:
        raise ValueError("O grafo compilado não expõe o método invoke().")

    return invoke_fn(estado_inicial, configuracao_requisicao)

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK, summary="Interagir com o Agente de IA")
@limiter.limit("10/minute")
async def chat_interaction(
    request: Request,
    payload: MessageRequest,
    tenant_id: str = Depends(verificar_token),
):
    """
    Dispara um fluxo de conversa dentro do Grafo de Estados (LangGraph).
    O roteamento de intenção e a conexão com os arquivos vetoriais do cliente
    são estabelecidos dinamicamente a partir do ID do tenant, que pode vir
    por header (WhatsApp/integrações) ou pelo próprio corpo da requisição
    quando a origem é uma plataforma como o site.
    A memória é persistida no PostgreSQL por meio do PostgresSaver.
    """
    tenant_id = tenant_id or payload.tenant_id

    if not tenant_id or not str(tenant_id).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="É obrigatório informar o tenant. Envie o cabeçalho X-Tenant-ID ou o campo tenant_id no corpo da requisição."
        )

    estado_inicial = {
        "messages": [HumanMessage(content=payload.message)],
        "current_date": "",
        "selected_slot": "",
        "alternatives_suggested": []
    }
    
    # Enviamos o tenant_id (para o RAG) e o thread_id (para o PostgresSaver)
    # CRÍTICO: o PostgresSaver do LangGraph indexa o checkpoint SOMENTE pelo thread_id.
    # Se dois tenants (ou dois visitantes sem thread_id próprio) usarem o mesmo valor,
    # eles passam a compartilhar o MESMO histórico de mensagens persistido, misturando
    # datas e agendamentos de conversas antigas/de outros clientes na conversa atual.
    # Por isso o thread_id enviado ao grafo é SEMPRE prefixado com o tenant_id.
    thread_id_sessao = payload.thread_id or "default_session"
    thread_id_base = f"{tenant_id}:{thread_id_sessao}"
    # O thread_id do widget fica salvo no localStorage do cliente e pode ser reaproveitado
    # por dias/semanas. Resolvemos aqui, no backend, se essa conversa esta "parada" ha muito
    # tempo (CHAT_SESSION_IDLE_MINUTES) e, se sim, geramos uma nova sessao automaticamente -
    # sem depender do front avisar o cliente pra abrir uma conversa nova.
    thread_id_grafo = resolve_active_thread_id(thread_id_base)
    conversation_key = thread_id_grafo
    conversation_lock = _chat_locks.setdefault(conversation_key, asyncio.Lock())
    
    configuracao_requisicao = {
        "configurable": {
            "tenant_id": tenant_id,
            "thread_id": thread_id_grafo,
            "base_thread_id": thread_id_base
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
            f"❌ [TIMEOUT] O processamento da mensagem estourou o tempo limite para a thread {payload.thread_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="O serviço de atendimento demorou muito para responder. Por favor, tente novamente.",
        )
    except Exception as ex:
        # Log detalhado do erro no servidor para monitoramento interno
        logger.error(
            f"❌ [AGENT ERROR] Falha inesperada no processamento da thread {payload.thread_id}: {str(ex)}",
            exc_info=True,
        )

        # Retorno amigável em JSON sem expor stack traces sensíveis de banco/código para o cliente
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro interno ao processar sua solicitação no Atendimento de IA. Nossa equipe já foi notificada.",
        )

   
        
@router.get("/chat/init")
@limiter.limit("5/minute")
def inicializar_widget(request: Request, tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")):
    """
    O frontend chama esta rota passando o tenant_id aberto na URL UMA ÚNICA VEZ.
    O backend devolve um token assinado e temporário.
    """
    tenant_service = TenantService()
    if not tenant_id or not str(tenant_id).strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado."
        )
    
    tenant_config = tenant_service.get_tenant_by_id(tenant_id)
        
    origin = request.headers.get("origin", "") or request.headers.get("referer", "") or ""
    
    netloc_bruto = urlparse(origin).netloc.lower()
    domain_origen = netloc_bruto.split(":")[0] if netloc_bruto else ""
    
    if not tenant_config:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado."
        )
        
    authorized_domains = [d.lower() for d in tenant_config.get("allowed_domains", [])]
    if not tenant_config or domain_origen not in authorized_domains:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado."
        )
    
    # Define que o token vai expirar em exatos 30 minutos a partir de agora
    tempo_expiracao = datetime.now(timezone.utc) + timedelta(minutes=30)
    
    
    # O "payload" é o pacote de dados que vai viajar dentro do token escondido
    payload = {
        "tenant_id": tenant_id, # Guarda de qual empresa é este chat
        "exp": tempo_expiracao  # Regra obrigatória do JWT para data de vencimento
    }
    
    # Gera o token em formato de texto gigante e criptografado
    token_assinado = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # Devolve para o frontend salvar na memória (ex: sessionStorage)
    return {
        "access_token": token_assinado,
        "token_type": "bearer"
    }
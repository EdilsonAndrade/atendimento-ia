from langchain_core.messages import HumanMessage
import psycopg
import asyncio
import logging
import os
import httpx
from infrastructure.connection import DB_URI, get_db_connection
from modules.ia.agent_graph import get_compiled_graph
from dotenv import load_dotenv
load_dotenv()  # Carrega variáveis de ambiente do arquivo .env
logger = logging.getLogger("whatsapp_webhook")

MESSAGE_PROCESSING_GAP_SECONDS = float(os.getenv("WHATSAPP_MESSAGE_GAP_SECONDS", "1.0"))
_conversation_locks: dict[str, asyncio.Lock] = {}
_conversation_last_finished_at: dict[str, float] = {}

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evolution-api:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "SuaChaveGlobalSuperSegura123")

headers_global = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json"
}

try:
    graph_app = get_compiled_graph()
except Exception as e:
    print(f"⚠️ Alerta: Erro ao inicializar o grafo com PostgresSaver: {e}")
    graph_app = None


def _invoke_graph(estado_inicial, configuracao_requisicao):
    if graph_app is None:
        raise ValueError("O grafo compilado não foi inicializado corretamente.")

    invoke_fn = getattr(graph_app, "invoke", None)
    if invoke_fn is None:
        raise ValueError("O grafo compilado não expõe o método invoke().")

    return invoke_fn(estado_inicial, configuracao_requisicao)


def _get_conversation_key(tenant_id: str, sender_phone: str, instance_name: str) -> str:
    return f"{tenant_id}:{sender_phone or instance_name}"


def _get_conversation_lock(conversation_key: str) -> asyncio.Lock:
    lock = _conversation_locks.get(conversation_key)
    if lock is None:
        lock = asyncio.Lock()
        _conversation_locks[conversation_key] = lock
    return lock


async def manter_digitando_continuo(instance_name: str, sender_phone: str, stop_event: asyncio.Event):
    """
    Envia o evento de 'composing' a cada 3.0 segundos até que a flag stop_event seja ativada.
    """
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{instance_name}"
    
    # COMENTÁRIO DUMMY: Remove o sufixo '@s.whatsapp.net' se houver, pois a Evolution API 
    # exige apenas os dígitos numéricos no campo 'number'.
    numero_limpo = sender_phone.split("@")[0].strip() if sender_phone else ""
    
    payload = {
        "number": numero_limpo,
        "presence": "composing",
        "delay": 3500
    }
    
    # COMENTÁRIO: Aumenta o timeout do HTTP Client para 3.5s e ignora oscilações na resposta do digitando
    async with httpx.AsyncClient(timeout=60.0) as client:
        while not stop_event.is_set():
            try:
                await client.post(url, json=payload, headers=headers_global)
            except Exception:
                # Silencia erros de conectividade no status 'digitando' para não poluir o console
                pass
            
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
async def buscar_instancia_por_nome(instance_name: str) -> dict | None:
    """
    Busca o tenant_id e dados da instância com base no instance_name recebido do Webhook.
    """
    query = """
        SELECT tenant_id, instance_name, phone_number 
        FROM whatsapp_instances
        WHERE instance_name = %s AND active = True
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (instance_name,))
            result = cur.fetchone() # COMENTÁRIO: fetchone traz a linha única diretamente
            
            if not result:
                return None
            
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, result))


        
async def salvar_instancia_banco(tenant_id: str, instance_name: str) -> dict:
    """
    Insere ou atualiza o registro da instância vinculando-a ao tenant no banco.
    """
    query = """
        INSERT INTO whatsapp_instances (tenant_id, instance_name)
        VALUES (%s, %s)
        ON CONFLICT (instance_name) 
        DO UPDATE SET tenant_id = EXCLUDED.tenant_id, updated_at = CURRENT_TIMESTAMP
        RETURNING id, tenant_id, instance_name
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (tenant_id, instance_name))
            result = cur.fetchone()
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, result))
    

            
    
# COMENTÁRIO: Lógica de execução do Agente IA em Background
async def processar_mensagem_e_responder(
    tenant_id: str,
    sender_phone: str,
    user_message: str,
    instance_name: str
):
    """
    Executa o pipeline do LangGraph e cancela a animação de digitando imediatamente após a resposta.
    """
    conversation_key = _get_conversation_key(tenant_id, sender_phone, instance_name)
    conversation_lock = _get_conversation_lock(conversation_key)
    resposta_final = ""

    async with conversation_lock:
        now = asyncio.get_running_loop().time()
        last_finished_at = _conversation_last_finished_at.get(conversation_key)
        if last_finished_at is not None:
            elapsed = now - last_finished_at
            remaining = MESSAGE_PROCESSING_GAP_SECONDS - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

        stop_typing_event = asyncio.Event()

        # Inicia o loop do digitando em background
        typing_task = asyncio.create_task(
            manter_digitando_continuo(instance_name, sender_phone, stop_typing_event)
        )

        try:
            logger.info(f"[WhatsApp] Processando mensagem do tenant {tenant_id} para {sender_phone}")
            
            estado_inicial = {
                "messages": [HumanMessage(content=user_message)]
            }

            thread_id_sessao = sender_phone or f"tenant_{tenant_id}_default"

            configuracao_requisicao = {
                "configurable": {
                    "tenant_id": tenant_id,
                    "thread_id": thread_id_sessao
                }
            }

            # COMENTÁRIO 1: Aumentado timeout para 60s para dar tempo da LLM + DB sem dar timeout
            async with asyncio.timeout(60.0):
                result = await asyncio.to_thread(
                    _invoke_graph, estado_inicial, configuracao_requisicao
                )

            # Se o Grafo executou com sucesso, extrai o texto da resposta
            if result and "messages" in result and result["messages"]:
                resposta_final = result["messages"][-1].content

        except Exception as ex:
            logger.error(f"[WhatsApp-WebHook] Erro no grafo do tenant {tenant_id} para {sender_phone}: {str(ex)}")
            # COMENTÁRIO 2: Define a mensagem de erro APENAS se o Grafo não tiver retornado nada antes
            if not resposta_final:
                resposta_final = "Desculpe, tive um problema ao processar sua solicitação. Pode tentar novamente em instantes?"

        finally:
            # COMENTÁRIO 3: Cancela a task do digitando IMEDIATAMENTE sem esperar o loop HTTP terminar
            stop_typing_event.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        # COMENTÁRIO 4: Dispara uma ÚNICA mensagem para o WhatsApp enquanto a conversa ainda está travada.
        if resposta_final:
            endpoint_send = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"
            numero_limpo = sender_phone.split("@")[0].strip() if sender_phone else ""
            payload_envio = {
                "number": numero_limpo,
                "text": resposta_final
            }

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(endpoint_send, json=payload_envio, headers=headers_global)
                    if response.status_code in [200, 201]:
                        logger.info(f"[WhatsApp] Resposta enviada com sucesso para {sender_phone}")
                    else:
                        logger.error(f"[WhatsApp Error] Falha Evolution API ({response.status_code}): {response.text}")
            except Exception as err_send:
                logger.error(f"[WhatsApp Error] Falha ao enviar resposta para o WhatsApp: {str(err_send)}")

        _conversation_last_finished_at[conversation_key] = asyncio.get_running_loop().time()
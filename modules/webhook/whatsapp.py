from wsgiref import headers

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


async def manter_digitando_continuo(instance_name: str, sender_phone: str, stop_event: asyncio.Event):
    """
    Envia o evento de 'composing' a cada 2.5 segundos até que a flag stop_event seja ativada.
    """
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{instance_name}"
    payload = {
        "number": sender_phone,
        "presence": "composing",
        "delay": 500
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        while not stop_event.is_set():
            try:
                await client.post(url, json=payload, headers=headers_global)
            except Exception as e:
                logger.warning(f"[WhatsApp Warning] Erro no loop de digitando: {str(e)}")
            
            # COMENTÁRIO: Aguarda 2.5 segundos antes de renovar a presença (ou encerra se stop_event for True)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2.5)
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
        INSERT INTO whatsapp_instances (tenant_id, instance_name, status)
        VALUES ($1, $2, 'connecting')
        ON CONFLICT (instance_name) 
        DO UPDATE SET tenant_id = EXCLUDED.tenant_id, updated_at = CURRENT_TIMESTAMP
        RETURNING id, tenant_id, instance_name, status;
    """
    async with get_db_connection() as conn:
        result = await conn.fetchrow(query, tenant_id, instance_name)
        return dict(result)
    

            
    
# COMENTÁRIO: Lógica de execução do Agente IA em Background
async def processar_mensagem_e_responder(
    tenant_id: str,
    sender_phone: str,
    user_message: str,
    instance_name: str
):
    """
    Executa o pipeline do LangGraph mantendo o status 'digitando...' continuamente visível no WhatsApp.
    """
    # COMENTÁRIO 1: Evento de controle para sinalizar a parada do 'digitando...'
    stop_typing_event = asyncio.Event()
    
    # COMENTÁRIO 2: Inicia o loop de animação contínua como uma task paralela em background
    typing_task = asyncio.create_task(
        manter_digitando_continuo(instance_name, sender_phone, stop_typing_event)
    )

    try:
        logger.info(f"[WhatsApp] Processando mensagem do tenant {tenant_id} para {sender_phone}")
        
        estado_inicial = {
            "messages": [HumanMessage(content=user_message)],
            "current_date": "",
            "selected_slot": "",
            "alternatives_suggested": []
        }
        
        thread_id_sessao = sender_phone or f"tenant_{tenant_id}_default"
        
        configuracao_requisicao = {
            "configurable": {
                "tenant_id": tenant_id,
                "thread_id": thread_id_sessao
            }
        }
        
        resposta_final = ""
        try:
            # COMENTÁRIO 3: Enquanto o LangGraph processa (carrega embeddings, faz RAG e chama a LLM)...
            async with asyncio.timeout(40.0):
                result = await asyncio.to_thread(
                    graph_app.invoke, 
                    estado_inicial, 
                    configuracao_requisicao
                )
            resposta_final = result["messages"][-1].content
            
        except Exception as ex:
            logger.error(f"[WhatsApp-WebHook] Erro no grafo do tenant {tenant_id} para {sender_phone}: {str(ex)}")
            resposta_final = "Desculpe, tive um problema ao processar sua solicitação. Pode tentar novamente em instantes?"

        # COMENTÁRIO 4: Envio da resposta de texto para o cliente
        endpoint_send = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"
        payload_envio = {
            "number": sender_phone,
            "text": resposta_final
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(endpoint_send, json=payload_envio, headers=headers_global)
            if response.status_code in [200, 201]:
                logger.info(f"[WhatsApp] Resposta enviada com sucesso para {sender_phone}")
            else:
                logger.error(f"[WhatsApp Error] Falha ao enviar para Evolution API ({response.status_code}): {response.text}")

    except Exception as e:
        logger.error(f"[WhatsApp Error] Falha geral no processamento para {sender_phone}: {str(e)}")

    finally:
        # COMENTÁRIO 5: Garante SEMPRE o encerramento do loop de digitando no final do processo
        stop_typing_event.set()
        await typing_task
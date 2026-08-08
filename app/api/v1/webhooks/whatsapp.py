# ONDE ALTERAR: No arquivo app/api/v1/webhooks/whatsapp.py

from fastapi import APIRouter, BackgroundTasks, Request
import logging
import time
from modules.webhook.whatsapp import processar_mensagem_e_responder, buscar_instancia_por_nome

# COMENTÁRIO: Logger do módulo de Webhook
logger = logging.getLogger("whatsapp_webhook")

router = APIRouter(tags=["Webhooks WhatsApp"])

PROCESSED_MESSAGE_IDS = {}

def limpar_ids_antigos():
    """Remove IDs com mais de 60 segundos da memória para evitar vazamento de memória."""
    agora = time.time()
    ids_para_remover = [msg_id for msg_id, timestamp in PROCESSED_MESSAGE_IDS.items() if agora - timestamp > 60]
    for msg_id in ids_para_remover:
        del PROCESSED_MESSAGE_IDS[msg_id]

# COMENTÁRIO: Rota única e oficial do Webhook para a Evolution API
@router.post("/webhook/whatsapp/evolution", summary="Recebe notificações de mensagens do WhatsApp via Evolution API")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint principal de recepção de eventos da Evolution API v2.
    Processa mensagens de texto e delega a resposta para o LangGraph via Background Tasks.
    """
    payload = await request.json()
    
    # COMENTÁRIO 1: Suporta tanto caixa alta quanto caixa baixa no evento da Evolution v2
    event_type = payload.get("event")
    if event_type not in ["messages.upsert", "MESSAGES_UPSERT"]:
        return {"status": "ignored_event"}

    data = payload.get("data", {})
    key = data.get("key", {})
    
    # COMENTÁRIO 2: Trava de segurança para ignorar mensagens enviadas pela própria instância
    if key.get("fromMe", False):
        return {"status": "ignored_from_me"}

    # COMENTÁRIO 3: Ignora mensagens enviadas em Grupos de WhatsApp
    sender_jid = key.get("remoteJid", "")
    if sender_jid.endswith("@g.us"):
        return {"status": "ignored_group"}

    # COMENTÁRIO 4: Extrai e limpa o número do remetente
    sender_phone = sender_jid.split("@")[0] if sender_jid else ""
    
    # COMENTÁRIO 5: Extrai o texto da mensagem (suporta conversa simples e texto estendido)
    message_content = data.get("message", {})
    user_message = (
        message_content.get("conversation") or
        message_content.get("extendedTextMessage", {}).get("text") or
        ""
    )

    if not user_message:
        return {"status": "no_text_content"}

    # COMENTÁRIO 6: DEDUPLICAÇÃO DE MENSAGENS (Executa apenas se houver mensagem de texto válida)
    message_id = key.get("id")
    limpar_ids_antigos()
    
    if message_id:
        if message_id in PROCESSED_MESSAGE_IDS:
            logger.info(f"[WhatsApp Webhook] Mensagem duplicada ignorada (ID: {message_id})")
            return {"status": "duplicate_message_ignored"}
        
        # Registra o ID da mensagem para travar requisições paralelas idênticas
        PROCESSED_MESSAGE_IDS[message_id] = time.time()

    # COMENTÁRIO 7: Pega o nome da instância que recebeu a mensagem na Evolution API
    instance_name = payload.get("instance")
    
    # COMENTÁRIO 8: Busca as configurações do tenant no banco de dados usando o nome da instância
    instance_info = await buscar_instancia_por_nome(instance_name)
    
    if not instance_info:
        logger.warning(f"[WhatsApp - API] Instância não cadastrada no banco: {instance_name}")
        return {"status": "instance_not_found"}

    # COMENTÁRIO 9: Envia o processamento e resposta do LangGraph para a fila em background do FastAPI
    background_tasks.add_task(
        processar_mensagem_e_responder,
        tenant_id=instance_info["tenant_id"],
        sender_phone=sender_phone,
        user_message=user_message,
        instance_name=instance_name
    )

    return {"status": "queued"}
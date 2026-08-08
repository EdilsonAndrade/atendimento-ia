# ONDE ALTERAR: Substitua todo o conteúdo do seu arquivo app/api/v1/webhooks/whatsapp.py por este

from fastapi import APIRouter, BackgroundTasks, Request
import logging
from modules.webhook.whatsapp import processar_mensagem_e_responder, buscar_instancia_por_nome

# COMENTÁRIO: Logger do módulo de Webhook
logger = logging.getLogger("whatsapp_webhook")

router = APIRouter(tags=["Webhooks WhatsApp"])

# COMENTÁRIO: Rota única e oficial do Webhook para a Evolution API
@router.post("/webhook/whatsapp/evolution", summary="Recebe notificações de mensagens do WhatsApp via Evolution API")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint principal de recepção de eventos da Evolution API v2.
    Processa mensagens de texto e delega a resposta para o LangGraph via Background Tasks.
    """
    payload = await request.json()
    logger.info(f"[WhatsApp - API] Payload recebido: {payload}")
    # COMENTÁRIO: Filtra apenas eventos de envio/recebimento de mensagens (messages.upsert)
    event_type = payload.get("event")
    if event_type != "messages.upsert":
        return {"status": "ignored_event"}

    data = payload.get("data", {})
    key = data.get("key", {})
    
    # COMENTÁRIO: Trava de segurança para ignorar mensagens enviadas pela própria instância
    if key.get("fromMe", False):
        return {"status": "ignored_from_me"}

    # COMENTÁRIO: Extrai e limpa o número do remetente
    sender_jid = key.get("remoteJid", "")
    sender_phone = sender_jid.split("@")[0] if sender_jid else ""
    
    # COMENTÁRIO: Extrai o texto da mensagem (suporta conversa simples e texto estendido)
    message_content = data.get("message", {})
    user_message = (
        message_content.get("conversation") or
        message_content.get("extendedTextMessage", {}).get("text") or
        ""
    )

    if not user_message:
        return {"status": "no_text_content"}

    # COMENTÁRIO: Pega o nome da instância que recebeu a mensagem na Evolution API (Ex: 'barbearia_v4')
    instance_name = payload.get("instance")
    
    # COMENTÁRIO: Busca as configurações do tenant no banco de dados usando o nome da instância
    instance_info = await buscar_instancia_por_nome(instance_name)
    
    if not instance_info:
        logger.warning(f"[WhatsApp - API] Instância não cadastrada no banco: {instance_name}")
        return {"status": "instance_not_found"}

    # COMENTÁRIO: Envia o processamento e resposta do LangGraph para a fila em background do FastAPI
    background_tasks.add_task(
        processar_mensagem_e_responder,
        tenant_id=instance_info["tenant_id"],
        sender_phone=sender_phone,
        user_message=user_message,
        instance_name=instance_name
    )

    return {"status": "queued"}
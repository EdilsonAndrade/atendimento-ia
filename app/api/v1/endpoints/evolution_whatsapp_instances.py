# ONDE ALTERAR: Criar ou ajustar o arquivo de endpoints de instâncias (ex: app/api/v1/endpoints/instances.py)

import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import httpx
import logging

from modules.webhook.whatsapp import salvar_instancia_banco

logger = logging.getLogger("whatsapp_instances")

router = APIRouter(tags=["Instâncias WhatsApp"])

# COMENTÁRIO: Schema de entrada da requisição de cadastro
class CreateInstanceRequest(BaseModel):
    tenant_id: str
    instance_name: str  # Ex: 'barbearia_v4' ou 'cliente_tenant_123'

# COMENTÁRIO: Configurações de ambiente da Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evolution-api:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "SuaChaveGlobalSuperSegura123")
EVOLUTION_WEBHOOK_URL = os.getenv("EVOLUTION_WEBHOOK_URL", "http://chatatendimento-api:8000/api/v1/webhook/whatsapp/evolution").rstrip('/')


@router.post(
    "/whatsapp/instances",
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma nova instância de WhatsApp e gera o QR Code"
)
async def criar_instancia_whatsapp(payload: CreateInstanceRequest):
    """
    1. Salva a instância no banco de dados vinculada ao tenant_id.
    2. Cria a instância na Evolution API.
    3. Retorna o QR Code em Base64 para exibição no frontend.
    """
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

    # =========================================================================
    # PASSO 1: CRIAR A INSTÂNCIA NA EVOLUTION API
    # =========================================================================
    create_body = {
        "instanceName": payload.instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
        # COMENTÁRIO 3: Garante o vínculo do webhook global para enviar mensagens à sua API Python
        "webhook": {
            "url": EVOLUTION_WEBHOOK_URL,
            "byEvents": False,
            "base64": False,
            "events": ["MESSAGES_UPSERT"]
        }
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # COMENTÁRIO: Requisição para criar a instância
            response_create = await client.post(
                f"{EVOLUTION_API_URL}/instance/create",
                json=create_body,
                headers=headers
            )
            
            if response_create.status_code not in [200, 201]:
                logger.error(f"[Evolution API] Erro ao criar instância: {response_create.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Falha ao criar instância na Evolution API"
                )

            # =========================================================================
            # PASSO 3: BUSCAR O QR CODE EM BASE64
            # =========================================================================
            dados_criacao = response_create.json()

            # =========================================================================
            # PASSO 2: SALVAR NO SEU BANCO POSTGRESQL
            # =========================================================================
            await salvar_instancia_banco(
                tenant_id=payload.tenant_id, 
                instance_name=payload.instance_name
            )

            # =========================================================================
            # PASSO 3: EXTRAIR E RETORNAR O QR CODE EM BASE64
            # =========================================================================
            # A Evolution retorna no formato: dados_criacao["qrcode"]["base64"]
            qrcode_base64 = (
                dados_criacao.get("qrcode", {}).get("base64") or 
                dados_criacao.get("base64")
            )

            return {
                "message": "Instância cadastrada e gerada com sucesso!",
                "tenant_id": payload.tenant_id,
                "instance_name": payload.instance_name,
                "qrcode_base64": qrcode_base64
            }

        except httpx.RequestError as exc:
            logger.error(f"Erro de conexão com Evolution API: {str(exc)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Serviço da Evolution API indisponível no momento"
            )
        except Exception as ex:
            logger.error(f"Erro interno ao processar criação de instância: {str(ex)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro interno no servidor: {str(ex)}"
            )

@router.get("/whatsapp/instances/{instance_name}/qrcode")
async def buscar_qrcode_instancia(instance_name: str):
    headers = {"apikey": EVOLUTION_API_KEY}
    url = f"{EVOLUTION_API_URL}/instance/connect/{instance_name}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            raise HTTPException(status_code=400, detail="Instância já conectada ou não encontrada.")
        data = res.json()
        
        # Pega a string base64 retornado da Evolution
        qr_base64 = data.get("base64") or data.get("code")
        return {"instance_name": instance_name, "qrcode_base64": qr_base64}
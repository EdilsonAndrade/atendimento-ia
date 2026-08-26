# Security: Usado para acionar o esquema de segurança na rota.
import os
import jwt
from dotenv import load_dotenv
from fastapi import  HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from modules.observability.interface.logger_factory import get_logger

security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "mudar_senha_123")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# ==============================================================================
# FUNÇÃO DE VALIDAÇÃO DO TOKEN (RODA ANTES DO CHAT)
# ==============================================================================
def verificar_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Função que pega o token enviado pelo frontend, descriptografa e vê se é válido.
    Se for falso, alterado ou vencido, ele derruba a requisição na hora.
    """
    token = credentials.credentials
    try:
        # Tenta abrir o token usando a sua senha secreta
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Se deu certo, extrai o tenant_id de dentro do token e devolve para a rota
        return payload.get("tenant_id")
        
    except jwt.ExpiredSignatureError:
        # Cai aqui se o token passou do tempo de validade (ex: 30 minutos)
        get_logger(tenant_id="unknown", tenant_name="unknown", agent="token_verify").warn(
            message="JWT expired",
            method="modules.token.token_verify.verificar_token",
            line=28,
            thread_id="system",
            extra={"error": "TOKEN_EXPIRED"},
        )
        raise HTTPException(status_code=401, detail="Sessão expirada. Recarregue o site.")
    except jwt.InvalidTokenError:
        # Cai aqui se um hacker tentar enviar um token inventado
        get_logger(tenant_id="unknown", tenant_name="unknown", agent="token_verify").warn(
            message="Invalid JWT rejected",
            method="modules.token.token_verify.verificar_token",
            line=31,
            thread_id="system",
            extra={"error": "TOKEN_INVALID"},
        )
        raise HTTPException(status_code=401, detail="Token de segurança inválido.")
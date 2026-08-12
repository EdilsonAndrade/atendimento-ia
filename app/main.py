# Ponto de Entrada que inicializa a aplicação FastAPI e registra os endpoints da versão 1 (v1) da API.
# main.py
import uvicorn
import os
from fastapi import Depends, FastAPI
from app.api.v1.webhooks import whatsapp
from app.core.config import settings
from app.api.v1.router import api_router
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.core.security import get_swagger_credentials
from app.api.v1.webhooks.whatsapp import router as whatsapp_router
from app.api.v1.endpoints.evolution_whatsapp_instances import router as evolution_instances_router
from app.api.v1.endpoints.tenant import router as tenant_router
from app.api.v1.endpoints.prompt_manager import router as prompt_manager_router

from fastapi import FastAPI, Depends, HTTPException, Request, Security

# HTTPBearer e HTTPAuthorizationCredentials: Fazem o FastAPI entender e exigir 
# o envio de um token no formato "Bearer <token>" no header de Autorização.
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Limiter: A classe principal que controla quantas requisições podem ser feitas.
# _rate_limit_exceeded_handler: A função que devolve a mensagem de erro bonita quando o limite estoura.
from slowapi import Limiter, _rate_limit_exceeded_handler

# get_remote_address: Função que pega o IP real do usuário (ignorando proxies se configurado certo).
from slowapi.util import get_remote_address

# RateLimitExceeded: O erro disparado quando o usuário passa do limite.
from slowapi.errors import RateLimitExceeded

# jwt: A biblioteca PyJWT que vai criar (encode) e ler (decode) os nossos tokens criptografados.
import jwt


from datetime import datetime, timedelta, timezone
# COMENTÁRIO: Carrega as variáveis declaradas no arquivo .env
load_dotenv()

limiter = Limiter(key_func=get_remote_address)
security = HTTPBearer()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json"  # COMENTÁRIO: O esquema do OpenAPI continua em /openapi.json
)

# ==============================================================================
# CONFIGURANDO O APP PARA USAR O LIMITADOR
# ==============================================================================
# Avisa o FastAPI que o limitador existe e que deve usar a mensagem padrão de erro
app.state.limiter = limiter

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
        raise HTTPException(status_code=401, detail="Sessão expirada. Recarregue o site.")
    except jwt.InvalidTokenError:
        # Cai aqui se um hacker tentar enviar um token inventado
        raise HTTPException(status_code=401, detail="Token de segurança inválido.")
    
# COMENTÁRIO: Rota protegida do Swagger UI
@app.get("/docs", include_in_schema=False)
async def get_swagger_documentation(username: str = Depends(get_swagger_credentials)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " - Swagger UI"
    )

# COMENTÁRIO: Rota protegida do Redoc
@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(username: str = Depends(get_swagger_credentials)):
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=app.title + " - ReDoc"
    )
# COMENTÁRIO: Lista de origens permitidas pelo CORS contendo portas locais de desenvolvimento e subdomínios de produção
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://localhost:8001",  # Adicionado para suportar testes locais em porta alternativa
    "http://127.0.0.1:8001",  # Adicionado para evitar bloqueio ao chamar via IP local em testes
    "https://interasisai.com.br",
    "https://www.interasisai.com.br",
    "http://interasisai.com.br",
    "https://api.interasisai.com.br",  # Adicionado subdomínio da API em produção
    "http://api.interasisai.com.br"
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos (GET, POST, OPTIONS, DELETE, etc.)
    allow_headers=["*"],  # Permite todos os headers (incluindo X-Tenant-ID, Content-Type, etc.)
    
)
app.include_router(
    whatsapp_router,
    prefix="/api/v1",
    tags=["Webhooks WhatsApp"]
)
app.include_router(
    evolution_instances_router,
    prefix="/api/v1",
    tags=["Evolution WhatsApp Instances"]
)
app.include_router(
    tenant_router,
    prefix="/api/v1",
    tags=["Tenants"]
)
app.include_router(
    prompt_manager_router,
    prefix="/api/v1"
)


# Acopla todas as rotas centralizadas do roteador v1
app.include_router(api_router, prefix=settings.API_V1_STR)


# COMENTÁRIO: Lê as variáveis de ambiente com fallback para padrões seguros
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
if __name__ == "__main__":
    # Roda o servidor localmente na porta 8000 de forma otimizada
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True, app_dir=".")
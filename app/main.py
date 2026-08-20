# Ponto de Entrada que inicializa a aplicação FastAPI e registra os endpoints da versão 1 (v1) da API.
# main.py
import uvicorn
import os
# jwt: A biblioteca PyJWT que vai criar (encode) e ler (decode) os nossos tokens criptografados.
import jwt
from fastapi import Depends, FastAPI
from app.core.config import settings
from app.api.v1.router import api_router
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
from app.core.widget_cors import WidgetCORSMiddleware
from dotenv import load_dotenv
from app.core.security import get_swagger_credentials
from app.api.v1.webhooks.whatsapp import router as whatsapp_router
from app.api.v1.endpoints.evolution_whatsapp_instances import router as evolution_instances_router
from app.api.v1.endpoints.tenant import router as tenant_router
from app.api.v1.endpoints.prompt_manager import router as prompt_manager_router
from app.api.v1.endpoints.knowledge_base import router as knowledge_base_router
from fastapi import FastAPI, Depends
from slowapi import _rate_limit_exceeded_handler
# get_remote_address: Função que pega o IP real do usuário (ignorando proxies se configurado certo).
from slowapi.util import get_remote_address
# RateLimitExceeded: O erro disparado quando o usuário passa do limite.
from slowapi.errors import RateLimitExceeded
from modules.token.token_verify import verificar_token
from app.core.limiter import limiter
# COMENTÁRIO: Carrega as variáveis declaradas no arquivo .env
load_dotenv()


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
app.add_middleware(WidgetCORSMiddleware)
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
app.include_router(
    knowledge_base_router,
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
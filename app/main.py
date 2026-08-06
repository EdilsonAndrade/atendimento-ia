# Ponto de Entrada que inicializa a aplicação FastAPI e registra os endpoints da versão 1 (v1) da API.
# main.py
import uvicorn
import os
from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
# COMENTÁRIO: Carrega as variáveis declaradas no arquivo .env
load_dotenv()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
    docs_url="/docs",       # Rota explícita do Swagger
    redoc_url="/redoc"      # Rota alternativa corporativa
)

origins =  [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://interasisai.com.br",
    "https://www.interasisai.com.br",
    "http://interasisai.com.br",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos (GET, POST, OPTIONS, DELETE, etc.)
    allow_headers=["*"],  # Permite todos os headers (incluindo X-Tenant-ID, Content-Type, etc.)
    
)
# Acopla todas as rotas centralizadas do roteador v1
app.include_router(api_router, prefix=settings.API_V1_STR)


# COMENTÁRIO: Lê as variáveis de ambiente com fallback para padrões seguros
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
if __name__ == "__main__":
    # Roda o servidor localmente na porta 8000 de forma otimizada
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True, app_dir=".")
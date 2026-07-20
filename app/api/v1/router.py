# Concentrador das Rotas da versão 1
# app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1.endpoints import chat, ingest

api_router = APIRouter()

# Acoplamento de rotas com tags limpas para organizar o Swagger visualmente
api_router.include_router(chat.router, tags=["Mensageria & Conversação"])
api_router.include_router(ingest.router, tags=["Ingestão de Dados (RAG)"])
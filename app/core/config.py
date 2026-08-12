# Configurações globais e Pydantic Settings

from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "SincroAgente API"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    PROJECT_DESCRIPTION: str=(
        "## Motor de Agentes Inteligentes Multi-Tenant (SaaS)\n\n"
        "Esta API orquestra Grafos de Estados com LangGraph e indexações "
        "vetoriais isoladas por cliente (Tenant ID).\n"
        "**Regra Operacional:** o header `X-Tenant-ID` é obrigatório para integrações e WhatsApp; "
        "o chat web pode complementar com `tenant_id` no body quando necessário."
    )
    
    class Config:
        case_sensitive = True
    
settings = Settings()
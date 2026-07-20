# Contratos de Dados de Ingestão de Conhecimento (RAG)
from pydantic import BaseModel, Field

class TextIngestionRequest(BaseModel):
    text_content: str = Field(...,examples=["Regra: o barbeiro Lucas atende apenas de terça a sábado, das 09h às 18h."], description="Texto livre contendo regras ou informações institucionais para alimentar a base vetorial.")
    
class IngestionResponse(BaseModel):
    tenant_id: str = Field(..., description="O ID do cliente que solicitou a indexação.")
    status: str = Field(..., description="Status do agendamento da tarefa assincrona")
    message: str = Field(..., description="Resposta limpa gerada pelo Grafo de Estados")
    

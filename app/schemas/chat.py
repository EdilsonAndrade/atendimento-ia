# Contratos de dados de entrada/saida do chat
from pydantic import BaseModel, Field

class MessageRequest(BaseModel):
    message: str = Field(...,examples=["Qual o horário disponíve para corte hoje?"], description="Mensagem ou pergunta textual enviada pelo usuário final.")


class ChatResponse(BaseModel):
    tenant_id: str = Field(..., description="O ID do cliente que processou a requisição.")
    status: str = Field(..., description="Status da execução do motor")
    response: str = Field(...,description="Resposta limpa gerada pelo Grafo de Estados")


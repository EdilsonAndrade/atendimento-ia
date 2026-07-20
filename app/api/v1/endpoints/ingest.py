# Endpoints de Ingestão de conhecimento (RAG)
import os
from fastapi import APIRouter, Depends, BackgroundTasks, status
from app.schemas.ingest import TextIngestionRequest, IngestionResponse
from app.api.deps import get_tenant_id
from modules.vetorizacao.setup_databases import initialize_tenant_data

router = APIRouter()

@router.post("/ingest/text", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED, summary="Vetorizar Regras por Texto Corrido")
async def ingest_text_rules(request: TextIngestionRequest, background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id)):
    """
    Adiciona regras de negócio em formato de texto para a base operacional do cliente.
    O processamento do embedding e salvamento no ChromaDB roda de forma assíncrona
    para evitar travamento no servidor.
    """
    temp_dir = f"data/temp/{tenant_id}"
    os.makedirs(temp_dir, exist_ok=True)
    txt_file_path = f"{temp_dir}/regras_api.txt"

    with open(txt_file_path, "w", encoding="utf-8") as f:
        f.write(request.text_content)

    # Dispara tarefa em background de acordo com as melhores práticas de Engenharia de Dados
    background_tasks.add_task(
        initialize_tenant_data,
        tenant_id=tenant_id,
        txt_path=txt_file_path
    )

    return IngestionResponse(
        tenant_id=tenant_id,
        status="processing",
        message="A tarefa de vetorização foi agendada e está sendo processada em segundo plano."
    )
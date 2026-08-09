from langchain_core.tools import tool
from pydantic import BaseModel, Field

class DeleteAppointmentInput(BaseModel):
    event_id: str = Field(description="O ID do evento no Google Calendar (obtido previamente via consultar_agenda)")

def build_delete_tool(tenant_id: str, tenant_service, calendar_service):
    """
    Fábrica da Tool para Deletar/Cancelar agendamentos.
    """
    @tool("cancelar_agendamento", args_schema=DeleteAppointmentInput)
    def cancelar_agendamento(event_id: str) -> str:
        """Utilize para cancelar um agendamento existente no Google Calendar usando o ID do evento."""
        
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        if not tenant or not tenant.google_calendar_id:
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        result = calendar_service.delete_event(
            calendar_id=tenant.google_calendar_id,
            event_id=event_id
        )

        if result.get("status") == "deleted":
            return f"Agendamento (ID: {event_id}) foi cancelado com sucesso."
        else:
            return f"Erro ao tentar cancelar o agendamento: {result.get('message')}"

    return cancelar_agendamento
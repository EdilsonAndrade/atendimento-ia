#Consulta a agenda do Google Calendar para verificar se há conflitos de horário antes de agendar um novo compromisso.
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class SearchAppointmentInput(BaseModel):
    start_time: str = Field(description="Data/hora inicial para busca no formato ISO (ex: 2026-08-10T00:00:00-03:00)")
    end_time: str = Field(description="Data/hora final para busca no formato ISO (ex: 2026-08-10T23:59:59-03:00)")
    query: str = Field(default="", description="Nome ou telefone do cliente para filtrar os eventos (opcional)")

def build_consulta_tool(tenant_id: str, tenant_service, calendar_service):
    """
    Fábrica da Tool de Consulta para verificar disponibilidade ou localizar agendamento existente.
    """
    @tool("consultar_agenda", args_schema=SearchAppointmentInput)
    def consultar_agenda(start_time: str, end_time: str, query: str = "") -> str:
        """Utilize para verificar horários ocupados/livres ou para localizar o event_id de um agendamento existente."""
        
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        if not tenant or not tenant.google_calendar_id:
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        events = calendar_service.list_events(
            calendar_id=tenant.google_calendar_id,
            start_time=start_time,
            end_time=end_time,
            query=query if query else None
        )

        if not events:
            return "Nenhum agendamento ou compromisso encontrado para esse período/filtro."

        # Formata a resposta de maneira legível para a IA interpretar
        linhas = []
        for ev in events:
            linhas.append(f"- ID: {ev['event_id']} | Título: {ev['summary']} | Início: {ev['start']} | Fim: {ev['end']}")

        return "Eventos encontrados na agenda:\n" + "\n".join(linhas)

    return consultar_agenda
#Consulta a agenda do Google Calendar para verificar se há conflitos de horário antes de agendar um novo compromisso.
from typing import Callable

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from util.tool_error_handling import safe_tool_result

class SearchAppointmentInput(BaseModel):
    # CRITICO: NAO usar data de exemplo aqui. Um literal fixo nesta descricao e enviado
    # ao LLM em toda chamada e pode ser copiado como se fosse a data real (bug ja visto
    # em producao). A data DEVE vir sempre da tabela CALENDAR REFERENCE do system prompt.
    start_time: str = Field(description="Data/hora inicial para busca no formato ISO (YYYY-MM-DDTHH:MM:SS-03:00). SEMPRE calcule a partir da tabela CALENDAR REFERENCE do prompt, nunca invente ou reutilize uma data de exemplo.")
    end_time: str = Field(description="Data/hora final para busca no formato ISO (YYYY-MM-DDTHH:MM:SS-03:00). SEMPRE calcule a partir da tabela CALENDAR REFERENCE do prompt, nunca invente ou reutilize uma data de exemplo.")
    query: str = Field(default="", description="Nome ou telefone do cliente para filtrar os eventos (opcional)")

def build_consulta_tool(tenant_id: str, tenant_service, calendar_service) -> Callable:
    """
    Fábrica da Tool de Consulta para verificar disponibilidade ou localizar agendamento existente.
    """
    @tool("consultar_agenda", args_schema=SearchAppointmentInput)
    @safe_tool_result(
        fallback="Não foi possível consultar a agenda no Google Calendar agora. Por favor, tente novamente em instantes.",
        tenant_id=tenant_id,
    )
    def consultar_agenda(start_time: str, end_time: str, query: str = "") -> str:
        """Utilize para verificar horários ocupados/livres ou para localizar o event_id de um agendamento existente."""

        print(
            f" -> [TOOL: consultar_agenda] tenant_id={tenant_id} "
            f"periodo={start_time} até {end_time}"
        )
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        google_calendar_id = tenant.get("google_calendar_id") if tenant else None
        print(
            f" -> [TOOL: consultar_agenda] tenant_encontrado={tenant is not None} "
            f"google_calendar_id={google_calendar_id!r}"
        )
        if not google_calendar_id:
            print(" -> [TOOL: consultar_agenda] Google Calendar não configurado; fallback permitido.")
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        events = calendar_service.list_events(
            calendar_id=google_calendar_id,
            start_time=start_time,
            end_time=end_time,
            query=query if query else None
        )

        print(f" -> [TOOL: consultar_agenda] consulta concluída; eventos_encontrados={len(events)}")

        if not events:
            return "Nenhum agendamento ou compromisso encontrado para esse período/filtro."

        # Formata a resposta de maneira legível para a IA interpretar
        linhas = []
        for ev in events:
            linhas.append(f"- ID: {ev['event_id']} | Título: {ev['summary']} | Início: {ev['start']} | Fim: {ev['end']}")

        return "Eventos encontrados na agenda:\n" + "\n".join(linhas)

    return consultar_agenda
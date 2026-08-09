# Agendamento de compromissos no Google Calendar
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class CreateAppointmentInput(BaseModel):
    summary: str = Field(description="Nome do cliente e/ou tipo de atendimento")
    start_time: str = Field(description="Data e hora de início no formato ISO 8601 (ex: 2026-08-10T14:00:00-03:00)")
    end_time: str = Field(description="Data e hora de término no formato ISO 8601 (ex: 2026-08-10T15:00:00-03:00)")
    description: str = Field(default="", description="Telefone do cliente, e-mail ou observações sobre o atendimento")

def build_agendar_tool(tenant_id: str, tenant_service, calendar_service) ->str:
    """
    Fábrica que injeta os serviços e o tenant_id ativo na Tool de Agendamento.
    """
    @tool("agendar_horario", args_schema=CreateAppointmentInput)
    def agendar_horario(summary: str, start_time: str, end_time: str, description: str = "") -> str:
        """Utilize para criar um agendamento no Google Calendar após o cliente confirmar data e horário."""

        print(
            f" -> [TOOL: agendar_horario] tenant_id={tenant_id} "
            f"periodo={start_time} até {end_time}"
        )
        # 1. Busca os dados do Tenant no repositório
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        google_calendar_id = tenant.get("google_calendar_id") if tenant else None
        print(
            f" -> [TOOL: agendar_horario] tenant_encontrado={tenant is not None} "
            f"google_calendar_id={google_calendar_id!r}"
        )
        if not google_calendar_id:
            print(" -> [TOOL: agendar_horario] Google Calendar não configurado; fallback permitido.")
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        # 2. Checa disponibilidade na agenda antes de criar
        try:
            is_free = calendar_service.check_availability(
                calendar_id=google_calendar_id,
                start_time=start_time,
                end_time=end_time
            )
        except Exception as ex:
            print(f" -> [TOOL: agendar_horario] ERRO ao consultar disponibilidade: {type(ex).__name__}: {ex}")
            raise

        print(f" -> [TOOL: agendar_horario] horario_disponivel={is_free}")

        if not is_free:
            return "O horário solicitado já está ocupado na agenda. Peça para o cliente escolher outro horário."

        # 3. Cria o evento na agenda do cliente
        try:
            result = calendar_service.create_event(
                calendar_id=google_calendar_id,
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                description=description
            )
        except Exception as ex:
            print(f" -> [TOOL: agendar_horario] ERRO ao criar evento: {type(ex).__name__}: {ex}")
            raise

        print(f" -> [TOOL: agendar_horario] evento_criado event_id={result.get('event_id')!r}")

        return f"Agendamento confirmado com sucesso! ID do evento: {result['event_id']}"

    return agendar_horario
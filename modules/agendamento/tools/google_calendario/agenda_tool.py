# Agendamento de compromissos no Google Calendar
from typing import Callable

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from util.tool_error_handling import safe_tool_result
from modules.observability.interface.logger_factory import get_logger

class CreateAppointmentInput(BaseModel):
    summary: str = Field(description="Nome do cliente e/ou tipo de atendimento")
    # CRITICO: NAO usar data de exemplo aqui. Um literal fixo nesta descricao e enviado
    # ao LLM em toda chamada e pode ser copiado como se fosse a data real (bug ja visto
    # em producao). A data DEVE vir sempre da tabela CALENDAR REFERENCE do system prompt.
    start_time: str = Field(description="Data e hora de início no formato ISO 8601 (YYYY-MM-DDTHH:MM:SS-03:00). SEMPRE calcule a partir da tabela CALENDAR REFERENCE do prompt, nunca invente ou reutilize uma data de exemplo.")
    end_time: str = Field(description="Data e hora de término no formato ISO 8601 (YYYY-MM-DDTHH:MM:SS-03:00). SEMPRE calcule a partir da tabela CALENDAR REFERENCE do prompt, nunca invente ou reutilize uma data de exemplo.")
    description: str = Field(default="", description="Telefone do cliente, e-mail ou observações sobre o atendimento")

def build_agendar_tool(tenant_id: str, tenant_service, calendar_service, thread_id: str = "unknown") -> Callable:
    """
    Fábrica que injeta os serviços e o tenant_id ativo na Tool de Agendamento.
    """
    @tool("agendar_horario", args_schema=CreateAppointmentInput)
    @safe_tool_result(
        fallback="Não foi possível concluir o agendamento no Google Calendar agora. Por favor, tente novamente em instantes.",
        tenant_id=tenant_id,
    )
    def agendar_horario(summary: str, start_time: str, end_time: str, description: str = "") -> str:
        """Utilize para criar um agendamento no Google Calendar após o cliente confirmar data e horário."""

        logger = get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="agendamento_google_calendar")

        print(
            f" -> [TOOL: agendar_horario] tenant_id={tenant_id} "
            f"periodo={start_time} até {end_time}"
        )
        logger.info(
            message="Booking started",
            method="modules.agendamento.tools.google_calendario.agenda_tool.agendar_horario",
            line=27,
            thread_id=thread_id,
            extra={"start_time": start_time, "end_time": end_time},
        )
        # 1. Busca os dados do Tenant no repositório
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        google_calendar_id = tenant.get("google_calendar_id") if tenant else None
        print(
            f" -> [TOOL: agendar_horario] tenant_encontrado={tenant is not None} "
            f"google_calendar_id={google_calendar_id!r}"
        )
        if not google_calendar_id:
            print(
                f" -> [CALENDAR_CREATE_FAIL] tenant_id={tenant_id} google_calendar_id=None "
                f"periodo={start_time} até {end_time} motivo=tenant_sem_google_calendar_id"
            )
            logger.error(
                message="Booking failed: tenant sem google_calendar_id",
                method="modules.agendamento.tools.google_calendario.agenda_tool.agendar_horario",
                line=46,
                thread_id=thread_id,
                extra={"error": "TENANT_SEM_GOOGLE_CALENDAR_ID"},
            )
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        # 2. Checa disponibilidade na agenda antes de criar
        is_free = calendar_service.check_availability(
            calendar_id=google_calendar_id,
            start_time=start_time,
            end_time=end_time,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )

        print(f" -> [TOOL: agendar_horario] horario_disponivel={is_free}")

        if not is_free:
            print(
                f" -> [CALENDAR_CREATE_FAIL] tenant_id={tenant_id} google_calendar_id={google_calendar_id!r} "
                f"periodo={start_time} até {end_time} motivo=horario_ocupado"
            )
            logger.warn(
                message="Booking slot unavailable",
                method="modules.agendamento.tools.google_calendario.agenda_tool.agendar_horario",
                line=62,
                thread_id=thread_id,
                extra={"error": "SLOT_UNAVAILABLE", "start_time": start_time, "end_time": end_time},
            )
            return "O horário solicitado já está ocupado na agenda. Peça para o cliente escolher outro horário."

        # 3. Cria o evento na agenda do cliente
        result = calendar_service.create_event(
            calendar_id=google_calendar_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )

        print(
            f" -> [CALENDAR_CREATE_OK] tenant_id={tenant_id} google_calendar_id={google_calendar_id!r} "
            f"periodo={start_time} até {end_time} event_id={result.get('event_id')!r} link={result.get('link')!r}"
        )
        logger.info(
            message=f"Booking confirmed: {result.get('event_id')}",
            method="modules.agendamento.tools.google_calendario.agenda_tool.agendar_horario",
            line=76,
            thread_id=thread_id,
            extra={"event_id": result.get("event_id"), "link": result.get("link")},
        )

        return (
            f"Agendamento confirmado com sucesso no Google Calendar! "
            f"ID do evento: {result['event_id']}. Link: {result.get('link')}"
        )

    return agendar_horario
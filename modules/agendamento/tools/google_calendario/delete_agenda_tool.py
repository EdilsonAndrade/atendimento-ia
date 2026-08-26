from typing import Callable

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from util.tool_error_handling import safe_tool_result
from modules.observability.interface.logger_factory import get_logger

class DeleteAppointmentInput(BaseModel):
    event_id: str = Field(description="O ID do evento no Google Calendar (obtido previamente via consultar_agenda)")

def build_delete_tool(tenant_id: str, tenant_service, calendar_service, thread_id: str = "unknown") -> Callable:
    """
    Fábrica da Tool para Deletar/Cancelar agendamentos.
    """
    @tool("cancelar_evento_google", args_schema=DeleteAppointmentInput)
    @safe_tool_result(
        fallback="Não foi possível cancelar o agendamento no Google Calendar agora. Por favor, tente novamente em instantes.",
        tenant_id=tenant_id,
    )
    def cancelar_evento_google(event_id: str) -> str:
        """Utilize para cancelar um agendamento existente no Google Calendar usando o ID do evento."""

        logger = get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="agendamento_google_calendar")
        logger.info(
            message=f"Cancel booking started: {event_id}",
            method="modules.agendamento.tools.google_calendario.delete_agenda_tool.cancelar_evento_google",
            line=20,
            thread_id=thread_id,
            extra={"event_id": event_id},
        )

        print(f" -> [TOOL: cancelar_evento_google] tenant_id={tenant_id} event_id={event_id}")
        tenant = tenant_service.get_tenant_by_id(tenant_id)
        google_calendar_id = tenant.get("google_calendar_id") if tenant else None
        print(
            f" -> [TOOL: cancelar_evento_google] tenant_encontrado={tenant is not None} "
            f"google_calendar_id={google_calendar_id!r}"
        )
        if not google_calendar_id:
            print(
                f" -> [CALENDAR_CANCEL_FAIL] tenant_id={tenant_id} google_calendar_id=None "
                f"event_id={event_id} motivo=tenant_sem_google_calendar_id"
            )
            return "Erro: O tenant não possui um Google Calendar ID configurado."

        result = calendar_service.delete_event(
            calendar_id=google_calendar_id,
            event_id=event_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )

        print(f" -> [TOOL: cancelar_evento_google] resultado={result}")

        if result.get("status") == "deleted":
            print(
                f" -> [CALENDAR_CANCEL_OK] tenant_id={tenant_id} google_calendar_id={google_calendar_id!r} "
                f"event_id={event_id}"
            )
            logger.info(
                message=f"Booking cancelled: {event_id}",
                method="modules.agendamento.tools.google_calendario.delete_agenda_tool.cancelar_evento_google",
                line=49,
                thread_id=thread_id,
                extra={"event_id": event_id},
            )
            return f"Agendamento (ID: {event_id}) foi cancelado com sucesso."
        else:
            print(
                f" -> [CALENDAR_CANCEL_FAIL] tenant_id={tenant_id} google_calendar_id={google_calendar_id!r} "
                f"event_id={event_id} motivo={result.get('message')!r}"
            )
            logger.error(
                message=f"Cancel booking failed: {result.get('message')}",
                method="modules.agendamento.tools.google_calendario.delete_agenda_tool.cancelar_evento_google",
                line=55,
                thread_id=thread_id,
                extra={"event_id": event_id, "error": result.get("message")},
            )
            return f"Erro ao tentar cancelar o agendamento: {result.get('message')}"

    return cancelar_evento_google
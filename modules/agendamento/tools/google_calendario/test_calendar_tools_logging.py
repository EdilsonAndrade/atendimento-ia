"""EDI-61: garante que toda chamada real às tools de calendário (criar, consultar,
cancelar) fica localizável em produção via uma tag fixa e grep-ável, cobrindo tanto o
caminho de sucesso quanto os de falha esperada (sem exceção — falha de negócio)."""
import contextlib
import io
import unittest
from unittest.mock import MagicMock

from modules.agendamento.tools.google_calendario.agenda_tool import build_agendar_tool
from modules.agendamento.tools.google_calendario.consulta_agenda_tool import build_consulta_tool
from modules.agendamento.tools.google_calendario.delete_agenda_tool import build_delete_tool


def _capture_stdout():
    return contextlib.redirect_stdout(io.StringIO())


class AgendarHorarioLoggingTest(unittest.TestCase):
    def test_success_emits_calendar_create_ok_tag(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal@x.com"}
        calendar_service = MagicMock()
        calendar_service.check_availability.return_value = True
        calendar_service.create_event.return_value = {"event_id": "evt1", "link": "http://x/evt1"}

        tool = build_agendar_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({
                "summary": "Chain Marcos",
                "start_time": "2026-08-24T09:00:00-03:00",
                "end_time": "2026-08-24T09:30:00-03:00",
                "description": "",
            })

        saida = out.getvalue()
        self.assertIn("[CALENDAR_CREATE_OK]", saida)
        self.assertIn("tenant_id=1234", saida)
        self.assertIn("evt1", saida)

    def test_slot_busy_emits_calendar_create_fail_tag(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal@x.com"}
        calendar_service = MagicMock()
        calendar_service.check_availability.return_value = False

        tool = build_agendar_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({
                "summary": "Chain Marcos",
                "start_time": "2026-08-24T09:00:00-03:00",
                "end_time": "2026-08-24T09:30:00-03:00",
                "description": "",
            })

        saida = out.getvalue()
        self.assertIn("[CALENDAR_CREATE_FAIL]", saida)
        self.assertIn("motivo=horario_ocupado", saida)

    def test_missing_google_calendar_id_emits_calendar_create_fail_tag(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": None}
        calendar_service = MagicMock()

        tool = build_agendar_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({
                "summary": "Chain Marcos",
                "start_time": "2026-08-24T09:00:00-03:00",
                "end_time": "2026-08-24T09:30:00-03:00",
                "description": "",
            })

        saida = out.getvalue()
        self.assertIn("[CALENDAR_CREATE_FAIL]", saida)
        self.assertIn("motivo=tenant_sem_google_calendar_id", saida)


class ConsultarAgendaLoggingTest(unittest.TestCase):
    def test_query_emits_calendar_query_tag_with_event_count(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal@x.com"}
        calendar_service = MagicMock()
        calendar_service.list_events.return_value = []

        tool = build_consulta_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({
                "start_time": "2026-08-24T00:00:00-03:00",
                "end_time": "2026-08-24T23:59:59-03:00",
                "query": "Chain Marcos",
            })

        saida = out.getvalue()
        self.assertIn("[CALENDAR_QUERY]", saida)
        self.assertIn("eventos_encontrados=0", saida)


class CancelarEventoGoogleLoggingTest(unittest.TestCase):
    def test_success_emits_calendar_cancel_ok_tag(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal@x.com"}
        calendar_service = MagicMock()
        calendar_service.delete_event.return_value = {"status": "deleted"}

        tool = build_delete_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({"event_id": "evt1"})

        saida = out.getvalue()
        self.assertIn("[CALENDAR_CANCEL_OK]", saida)
        self.assertIn("event_id=evt1", saida)

    def test_failure_emits_calendar_cancel_fail_tag(self):
        tenant_service = MagicMock()
        tenant_service.get_tenant_by_id.return_value = {"google_calendar_id": "cal@x.com"}
        calendar_service = MagicMock()
        calendar_service.delete_event.return_value = {"status": "error", "message": "not found"}

        tool = build_delete_tool("1234", tenant_service, calendar_service)

        with _capture_stdout() as out:
            tool.invoke({"event_id": "evt1"})

        saida = out.getvalue()
        self.assertIn("[CALENDAR_CANCEL_FAIL]", saida)
        self.assertIn("not found", saida)


if __name__ == "__main__":
    unittest.main()

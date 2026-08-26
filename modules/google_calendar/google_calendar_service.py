import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from util.time_helpers import ensure_business_timezone
from modules.observability.interface.logger_factory import get_logger

class GoogleCalendarService:
    def __init__(self, service_account_path: str = "credentials.json"):
        # Escopo necessário para ler e escrever na agenda do Google
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        
        # Carrega a chave da Service Account
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(f"Arquivo de credenciais não encontrado em: {service_account_path}")
            
        self.credentials = Credentials.from_service_account_file(
            service_account_path, 
            scopes=self.scopes
        )
        print(
            " -> [GOOGLE CALENDAR] "
            f"service_account={self.credentials.service_account_email!r} "
            f"credentials_file={os.path.abspath(service_account_path)!r}"
        )
        # Cria a conexão com a API v3 do Google Calendar
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def check_availability(
        self,
        calendar_id: str,
        start_time: datetime,
        end_time: datetime,
        tenant_id: str = "unknown",
        thread_id: str = "unknown",
    ) -> bool:
        """
        Verifica se há conflitos de horários na agenda do tenant.
        """
        start_iso = ensure_business_timezone(start_time)
        end_iso = ensure_business_timezone(end_time)

        try:
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start_iso,
                timeMax=end_iso,
                singleEvents=True
            ).execute()
        except Exception as e:
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="google_calendar_api").error(
                message=f"Google Calendar API error on events.list: {e}",
                method="modules.google_calendar.google_calendar_service.check_availability",
                line=36,
                thread_id=thread_id,
                extra={"calendar_id": calendar_id, "error": str(e)},
            )
            raise

        events = events_result.get('items', [])
        # Retorna True se a agenda estiver livre no horário
        return len(events) == 0

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        tenant_id: str = "unknown",
        thread_id: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Insere o agendamento no Google Calendar do cliente/tenant.
        """
        start_iso = ensure_business_timezone(start_time)
        end_iso = ensure_business_timezone(end_time)

        event_body = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_iso,
                'timeZone': 'America/Sao_Paulo',
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': 'America/Sao_Paulo',
            },
        }

        try:
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
        except Exception as e:
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="google_calendar_api").error(
                message=f"Google Calendar API error on events.insert: {e}",
                method="modules.google_calendar.google_calendar_service.create_event",
                line=74,
                thread_id=thread_id,
                extra={"calendar_id": calendar_id, "error": str(e)},
            )
            raise

        return {
            "status": "created",
            "event_id": event.get("id"),
            "link": event.get("htmlLink")
        }

    def list_events(
        self,
        calendar_id: str,
        start_time: datetime,
        end_time: datetime,
        query: Optional[str] = None,
        tenant_id: str = "unknown",
        thread_id: str = "unknown",
    ) -> List[Dict[str, Any]]:
        """
        Lista/busca eventos em um intervalo de tempo para consultar ou localizar o event_id.
        Permite filtrar pelo nome do cliente usando o parâmetro `query` (q).
        """
        start_iso = ensure_business_timezone(start_time)
        end_iso = ensure_business_timezone(end_time)

        params = {
            "calendarId": calendar_id,
            "timeMin": start_iso,
            "timeMax": end_iso,
            "singleEvents": True,
            "orderBy": "startTime"
        }

        # Filtra por texto se passado (ex: nome do cliente)
        if query:
            params["q"] = query

        try:
            events_result = self.service.events().list(**params).execute()
        except Exception as e:
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="google_calendar_api").error(
                message=f"Google Calendar API error on events.list: {e}",
                method="modules.google_calendar.google_calendar_service.list_events",
                line=111,
                thread_id=thread_id,
                extra={"calendar_id": calendar_id, "has_query_filter": bool(query), "error": str(e)},
            )
            raise

        items = events_result.get('items', [])

        result = []
        for item in items:
            result.append({
                "event_id": item.get("id"),
                "summary": item.get("summary", ""),
                "description": item.get("description", ""),
                "start": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date"),
                "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            })

        return result

    def delete_event(
        self,
        calendar_id: str,
        event_id: str,
        tenant_id: str = "unknown",
        thread_id: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Deleta um evento específico do Google Calendar do cliente/tenant.
        """
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            return {"status": "deleted", "event_id": event_id}
        except Exception as e:
            get_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="google_calendar_api").error(
                message=f"Google Calendar API error on events.delete: {e}",
                method="modules.google_calendar.google_calendar_service.delete_event",
                line=131,
                thread_id=thread_id,
                extra={"calendar_id": calendar_id, "event_id": event_id, "error": str(e)},
            )
            return {"status": "error", "message": str(e)}
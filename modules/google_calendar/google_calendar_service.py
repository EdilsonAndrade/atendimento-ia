import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

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

    def check_availability(self, calendar_id: str, start_time: datetime, end_time: datetime) -> bool:
        """
        Verifica se há conflitos de horários na agenda do tenant.
        """
        start_iso = start_time.isoformat() if isinstance(start_time, datetime) else start_time
        end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True
        ).execute()

        events = events_result.get('items', [])
        # Retorna True se a agenda estiver livre no horário
        return len(events) == 0

    def create_event(
        self, 
        calendar_id: str, 
        summary: str, 
        start_time: datetime, 
        end_time: datetime, 
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Insere o agendamento no Google Calendar do cliente/tenant.
        """
        start_iso = start_time.isoformat() if isinstance(start_time, datetime) else start_time
        end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

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

        event = self.service.events().insert(
            calendarId=calendar_id, 
            body=event_body
        ).execute()

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
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista/busca eventos em um intervalo de tempo para consultar ou localizar o event_id.
        Permite filtrar pelo nome do cliente usando o parâmetro `query` (q).
        """
        start_iso = start_time.isoformat() if isinstance(start_time, datetime) else start_time
        end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

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

        events_result = self.service.events().list(**params).execute()
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

    def delete_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
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
            return {"status": "error", "message": str(e)}
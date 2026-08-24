from infrastructure.connection import DB_URI
from pydantic import BaseModel, Field, ConfigDict
from langchain.tools import tool
import psycopg
from util.tool_error_handling import safe_tool_result
class DeleteAgendaInput(BaseModel):
    model_config = ConfigDict(validate_by_name=True)
    
    tenant_id: str = Field(..., description="ID do tenant do cliente (ex: '987654')")
    cliente_email: str = Field(..., description="E-mail from client", alias="email")
    data_agendamento: str = Field(..., description="Booking date (YYYY-MM-DD). Always compute from the CALENDAR REFERENCE table in the system prompt, never invent or reuse an example date.", alias="data")
    horario_agendamento: str = Field(..., description="Booking time, example (HH:MM) 07:25 or 17:25")
    
    


@tool("cancelar_agendamento", args_schema=DeleteAgendaInput)
@safe_tool_result(fallback="Não foi possível processar o cancelamento devido a um erro técnico. Por favor, tente novamente mais tarde.")
def cancelar_agendamento(
    tenant_id: str,
    cliente_email: str,
    data_agendamento: str,
    horario_agendamento: str
) -> str:
    """
    Cancela agendamento previamente feito.

    Args:
        tenant_id (str): O ID da empresa / tenant.
        cliente_email (str): Email do cliente que está agendado
        data_agendamento (str): Data do agendamento (YYYY-MM-DD).
        horario_agendamento: (str): Horario do agendamento (HH:MM)

    Returns:
        str: Texto detalhado com o cancelamento ou com informativa de que não há agendamento para data e horário para este cliente
    """

    delete_query_ = """
        UPDATE agendamentos
        SET deleted_at = NOW(), status = 'CANCELADO'
        WHERE tenant_id = %s
          AND LOWER(cliente_email) = LOWER(%s)
          AND data_agendamento = %s
          AND horario = %s
          AND deleted_at IS NULL
        """

    with psycopg.connect(conninfo=DB_URI, autocommit=True, prepare_threshold=0) as conn:
        with conn.cursor() as cur:
            cur.execute(query=delete_query_, params=(
                tenant_id,
                cliente_email,
                data_agendamento,
                horario_agendamento,
            ))

            # Valida se o UPDATE realmente encontrou e alterou o agendamento no banco
            if cur.rowcount == 0:
                return f"Não foi encontrado nenhum agendamento ativo para o e-mail '{cliente_email}' na data {data_agendamento} às {horario_agendamento}."

    return f"Seu agendamento do dia {data_agendamento} às {horario_agendamento} foi cancelado com sucesso!"

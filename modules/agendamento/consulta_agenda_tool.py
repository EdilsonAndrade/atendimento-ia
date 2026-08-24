import psycopg
from langchain.tools import tool
from pydantic import BaseModel, Field, ConfigDict
from infrastructure.connection import DB_URI
from util.tool_error_handling import safe_tool_result

class ConsultaAgendaInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    tenant_id: str = Field(...,description="Tenant id do cliente")
    cliente_email: str = Field(...,description="Email do cliente", alias="email")
    
    
@tool("consulta_agendamento", args_schema=ConsultaAgendaInput)
@safe_tool_result(fallback="Não foi possível consultar seus agendamentos agora. Por favor, tente novamente em instantes.")
def consulta_agendamento(
    tenant_id: str,
    cliente_email: str
) -> str:
    """
    Consulta a base pelo email do cliente e tenant_id para encontrar o agendamento mais próximo
    
    Args:
        tenant_id (str): O ID da empresa / tenant.
        cliente_email (str): Email do cliente que está agendado
        
    Returns:
        str: Texto detalhado contendo a data do proximo agendamento do cliente 
    """
    
   
        
    consulta_sql = """
        SELECT 
            cliente_nome, 
            servico, 
            profissional, 
            data_agendamento, 
            horario, 
            status
        FROM agendamentos
        where tenant_id = %s
        AND LOWER(cliente_email) = LOWER(%s)
        AND deleted_at IS NULL AND status != 'CANCELADO'
        AND data_agendamento >= CURRENT_DATE
        ORDER BY data_agendamento ASC, horario ASC;
    """
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    with psycopg.connect(DB_URI, **connection_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(consulta_sql,
            (
                tenant_id,
                cliente_email
            ))

            result = cur.fetchall()

            if not result:
               return f"Nenhum agendamento ativo foi encontrado no sistema para o e-mail '{cliente_email}'."

            lista_agendamentos = []
            for row in result:
                nome_cliente = row[0]
                servico = row[1]
                profissional = row[2]

                data_str = row[3].strftime("%d/%m/%Y") if hasattr(row[3], 'strftime') else str(row[3])
                horario_str = row[4].strftime("%H:%M") if hasattr(row[4], 'strftime') else str(row[4])[:5]

                lista_agendamentos.append(
                    f"• Data: {data_str} às {horario_str} | Serviço: {servico} | Profissional: {profissional}"
                )

            resumo_texto = "\n".join(lista_agendamentos)
            return f"Agendamento(s) encontrado(s) para '{cliente_email}':\n{resumo_texto}"
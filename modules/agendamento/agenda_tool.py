import os
import psycopg
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from langchain.tools import tool

# Importa a função de inicialização do seu arquivo de booking
from modules.agendamento.booking_tools import init_booking_table

load_dotenv()

DB_URI = os.getenv("POSTGRES_DATABASE_URI", "postgresql://postgres:2765581@localhost:5432/simplificando")


class DisponibilidadeInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    tenant_id: str = Field(..., description="ID do tenant do cliente (ex: '987654')")
    profissional: str = Field(..., description="Nome do profissional/barbeiro (ex: 'Daniel')")
    data_agendamento: str = Field(..., alias="data", description="Data do agendamento no formato YYYY-MM-DD (ex: '2026-07-22')")


@tool("consultar_horarios_disponiveis", args_schema=DisponibilidadeInput)
def consultar_horarios_disponiveis(
    tenant_id: str,
    profissional: str,
    data_agendamento: str,
) -> str:
    """
    Consulta os horários que JÁ ESTÃO OCUPADOS/AGENDADOS para um profissional em uma data específica.
    
    Args:
        tenant_id (str): O ID da empresa / tenant.
        profissional (str): Nome do profissional para verificar disponibilidade.
        data_agendamento (str): Data do agendamento (YYYY-MM-DD).

    Returns:
        str: Texto detalhando quais horários estão ocupados naquele dia ou se a agenda está totalmente livre.
    """
    if not tenant_id or not profissional or not data_agendamento:
        return "Erro: Parâmetros tenant_id, profissional e data_agendamento são obrigatórios."

    try:
        print(f" -> [TOOL: consultar_horarios_disponiveis] Verificando agenda no Postgres para '{profissional}' em {data_agendamento}...")
        init_booking_table()
        
        # Query com LOWER/ILIKE para evitar divergência de maiúsculas/minúsculas
        search_query = """
            SELECT horario, servico, cliente_nome
            FROM agendamentos 
            WHERE 
                tenant_id = %s 
                AND LOWER(profissional) = LOWER(%s)
                AND data_agendamento = %s 
            ORDER BY horario ASC;
        """
        
        connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
        with psycopg.connect(DB_URI, **connection_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(search_query, (tenant_id, profissional, data_agendamento))
                agendamentos_existentes = cur.fetchall()
                
                if not agendamentos_existentes:
                    return f"A agenda do profissional '{profissional}' no dia {data_agendamento} está totalmente LIVRE (nenhum horário agendado ainda)."
                
                # Formata os horários ocupados em texto claro para a IA raciocinar
                horarios_ocupados = []
                for row in agendamentos_existentes:
                    val_horario = row[0]
                    if hasattr(val_horario, 'strftime'):
                        horarios_ocupados.append(val_horario.strftime("%H:%M"))
                    else:
                        horarios_ocupados.append(str(val_horario)[:5])  # Pega "HH:MM" se já for string

                lista_horarios_str = ", ".join(horarios_ocupados)
                
                return (
                    f"Para o profissional '{profissional}' no dia {data_agendamento}, "
                    f"os seguintes horários JÁ ESTÃO OCUPADOS: [{lista_horarios_str}]. "
                    f"Todos os outros horários de funcionamento do estabelecimento estão disponíveis."
                )

    except Exception as ex:
        print(f"❌ Erro ao consultar banco de dados: {ex}")
        return f"Erro ao consultar disponibilidade no banco de dados: {str(ex)}"
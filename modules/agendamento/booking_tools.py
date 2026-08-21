from datetime import datetime
from langchain.tools import tool
from pydantic import Field, BaseModel, ConfigDict
import psycopg
from infrastructure.connection import DB_URI


class BookingInput(BaseModel):
    # Permite aceitar tanto o nome do campo ('data_agendamento') quanto o alias ('data')
    model_config = ConfigDict(populate_by_name=True)
    
    tenant_id: str = Field(..., description="ID do tenant do cliente (ex: 'interasis_barber')")
    cliente_nome: str = Field(..., description="Nome do cliente que está realizando a reserva")
    cliente_email: str = Field(..., description="E-mail do cliente para envio do convite e confirmação")
    servico: str = Field(..., description="Nome do serviço desejado (ex: 'Corte Degradê', 'Barba Terapia')")
    profissional: str = Field(..., description="Nome do barbeiro/profissional escolhido")
    email_profissional: str = Field(..., description="E-mail do profissional para vincular à agenda do Google Calendar")
    # CRITICO: NAO usar data de exemplo aqui; um literal fixo na descricao e enviado ao
    # LLM em toda chamada e pode ser copiado como se fosse a data real.
    data_agendamento: str = Field(..., alias="data", description="Data do agendamento no formato YYYY-MM-DD. SEMPRE calcule a partir da tabela CALENDAR REFERENCE do prompt, nunca invente ou reutilize uma data de exemplo.")
    horario: str = Field(..., alias="hora", description="Horário do agendamento no formato HH:MM (ex: '14:30')")

def real_time_available(
    tenant_id: str,
    profissional: str,
    data_agendamento: str,
    horario: str,
) -> str:
    # A tabela `agendamentos` é criada pelas migrations em `migrations/` (EDI-37).
    check_query = """
        SELECT id FROM agendamentos 
        WHERE tenant_id = %s 
        AND LOWER(profissional) = LOWER(%s) 
        AND data_agendamento = %s 
        AND horario = %s
    """
    
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    with psycopg.connect(DB_URI, **connection_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(check_query, (tenant_id, profissional, data_agendamento, horario))
            if cur.fetchone():
                return f"Erro: O horário {horario} com o profissional {profissional} em {data_agendamento} já foi preenchido por outro cliente. Por favor, escolha outro horário."
    return ""
          
def save_local_booking(
    tenant_id: str,
    cliente_nome: str,
    cliente_email: str,
    servico: str,
    profissional: str,
    email_profissional: str,
    data_agendamento: str,
    horario: str,
    google_event_id: str = None
) -> int:
    """
    Insere o registro do agendamento no banco PostgreSQL.
    """
    
    insert_query = """
    INSERT INTO agendamentos (
        tenant_id, cliente_nome, cliente_email, servico, 
        profissional, email_profissional, data_agendamento, horario, google_event_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id;
    """
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    with psycopg.connect(DB_URI, **connection_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(
                
                insert_query,
                (
                    tenant_id, cliente_nome, cliente_email, servico,
                    profissional, email_profissional, data_agendamento, horario, google_event_id
                )
            )
            agendamento_id = cur.fetchone()[0]
            return agendamento_id
    
# ============================================================================
# INTEGRADOR DO GOOGLE CALENDAR (Placeholder para 1.3)
# ============================================================================
def create_google_calendar_event(
    email_profissional: str,
    cliente_email: str,
    servico: str,
    cliente_nome: str,
    data_agendamento: str,
    horario: str
) -> str:
    """
    Simula / Executa a criação do evento na API do Google Calendar.
    Retorna o ID do evento criado no Google.
    """
    # Se houver integração oficial via Google API Credentials no ambiente:
    # Aqui entrará a chamada oficial `service.events().insert(...)`
    # Por enquanto, geramos o identificador único simulando o retorno da API do Google.
    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
    google_event_id = f"gcal_evt_{timestamp_str}_{email_profissional.split('@')[0]}"
    
    print(f"\n Google Calendar API (1.3): Evento agendado na agenda de [{email_profissional}]")
    print(f"    - Convite enviado para o cliente: [{cliente_email}]")
    print(f"    - Detalhes: {servico} para {cliente_nome} às {horario} em {data_agendamento}")
    
    return google_event_id


# ============================================================================
# TOOL OFICIAL DO LANGCHAIN / LANGGRAPH
# ============================================================================
@tool("confirmar_agendamento", args_schema=BookingInput)
def confirmar_agendamento(
    tenant_id: str,
    cliente_nome: str,
    cliente_email: str,
    servico: str,
    profissional: str,
    email_profissional: str,
    data_agendamento: str,
    horario: str
) -> str:
    """
    Executa a confirmação final do agendamento.
    Salva a reserva na base local do tenant (Fallback 1.6) e cria o evento
    no Google Calendar do profissional e do cliente (Google Calendar 1.3).
    Use esta ferramenta apenas quando tiver todos os dados confirmados pelo cliente.
    """
    print(f"\n --- [TOOL EXECUTADA: confirmar_agendamento] Processando reserva para {cliente_nome}... ---")
    
    try:
        is_available = real_time_available(tenant_id, profissional, data_agendamento,horario)
        
        if is_available:
            return is_available
        
        # 1. Dispara integração com o Google Calendar (1.3)
        google_evt_id = create_google_calendar_event(
            email_profissional=email_profissional,
            cliente_email=cliente_email,
            servico=servico,
            cliente_nome=cliente_nome,
            data_agendamento=data_agendamento,
            horario=horario
        )
        
        # 2. Salva no banco de dados do Tenant no PostgreSQL (1.6)
        agendamento_id = save_local_booking(
            tenant_id=tenant_id,
            cliente_nome=cliente_nome,
            cliente_email=cliente_email,
            servico=servico,
            profissional=profissional,
            email_profissional=email_profissional,
            data_agendamento=data_agendamento,
            horario=horario,
            google_event_id=google_evt_id
        )
        
        return (
            f"Agendamento confirmado com sucesso! ID da reserva: #{agendamento_id}. "
            f"O serviço '{servico}' com {profissional} ficou marcado para {data_agendamento} às {horario}. "
            f"Um convite foi enviado para o e-mail {cliente_email}."
        )
        
    except Exception as e:
        print(f"❌ Erro na execução da Tool de agendamento: {e}")
        return f"Falha ao realizar o agendamento no sistema: {str(e)}"
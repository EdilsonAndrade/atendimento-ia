from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def ensure_business_timezone(value, timezone_name: str = "America/Sao_Paulo"):
    """Normaliza datas ISO/naive para o fuso de negócio, garantindo offset explícito.

    Sem isso, o Google Calendar trata strings sem offset como UTC na consulta e como
    horário local na criação, deslocando o agendamento em algumas horas.
    """
    if value is None:
        return value

    try:
        business_tz = ZoneInfo(timezone_name)
    except Exception:
        business_tz = None

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
    elif isinstance(value, datetime):
        parsed = value
    else:
        return value

    if parsed.tzinfo is None and business_tz is not None:
        parsed = parsed.replace(tzinfo=business_tz)

    return parsed.isoformat()


def get_tabela_dias(quantidade_dias: int, timezone_name: str = "America/Sao_Paulo", reference_now: datetime | None = None):
    try:
        business_tz = ZoneInfo(timezone_name)
    except Exception:
        business_tz = None

    if reference_now is not None:
        if reference_now.tzinfo is None:
            now = reference_now.replace(tzinfo=business_tz)
        elif business_tz is not None:
            now = reference_now.astimezone(business_tz)
        else:
            now = reference_now
    else:
        if business_tz is not None:
            now = datetime.now(business_tz)
        else:
            now = datetime.now()

    data_hoje_iso = now.strftime("%Y-%m-%d")
    hora_atual_str = now.strftime("%H:%M")

    dias_semana_pt = {
        0: "segunda-feira",
        1: "terça-feira",
        2: "quarta-feira",
        3: "quinta-feira",
        4: "sexta-feira",
        5: "sábado",
        6: "domingo",
    }

    tabela_dias = []
    for i in range(quantidade_dias):
        dia_calc = now + timedelta(days=i)
        nome_dia = "hoje" if i == 0 else ("amanhã" if i == 1 else dias_semana_pt[dia_calc.weekday()])
        data_iso = dia_calc.strftime("%Y-%m-%d")
        data_br = dia_calc.strftime("%d/%m/%Y")
        tabela_dias.append(f"• {nome_dia.capitalize()} ({dias_semana_pt[dia_calc.weekday()]}): {data_br} (ISO: '{data_iso}')")

    return tabela_dias, hora_atual_str, data_hoje_iso
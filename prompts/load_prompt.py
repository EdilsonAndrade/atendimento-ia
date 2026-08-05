from pathlib import Path

# Caminho para o arquivo markdown de prompt
PROMPTS_DIR = Path(__file__).resolve().parent
# Define o caminho do arquivo .md dentro da pasta prompts
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"

def carregar_operacional_prompt(tenant_id, tabela_calendario_str, hora_atual_str, data_hoje_iso, contexto_formatado):
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    
    # Preenche os placeholders do arquivo .md com as variáveis calculadas do Python
    return template.format(
        tenant_id=tenant_id,
        tabela_calendario_str=tabela_calendario_str,
        hora_atual_str=hora_atual_str,
        data_hoje_iso=data_hoje_iso,
        contexto_formatado=contexto_formatado
    )
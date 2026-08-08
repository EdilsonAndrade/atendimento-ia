# ONDE ALTERAR: No seu arquivo onde está a função carregar_operacional_prompt

from pathlib import Path

# Caminho para o arquivo markdown de prompt
PROMPTS_DIR = Path(__file__).resolve().parent
# Define o caminho dos arquivos .md dentro da pasta prompts
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"
GUARDRAIL_PATH = PROMPTS_DIR / "guardrails.md"

# COMENTÁRIO 1: Lê o texto do guardrail (lido uma vez no carregamento do módulo)
guardrails_text = GUARDRAIL_PATH.read_text(encoding="utf-8")

def carregar_operacional_prompt(tenant_id, tabela_calendario_str, hora_atual_str, data_hoje_iso, contexto_formatado):
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    
    # COMENTÁRIO 2: Inclui a variável guardrails_text no preenchimento dos placeholders
    return template.format(
        guardrails=guardrails_text,
        tenant_id=tenant_id,
        tabela_calendario_str=tabela_calendario_str,
        hora_atual_str=hora_atual_str,
        data_hoje_iso=data_hoje_iso,
        contexto_formatado=contexto_formatado
    )
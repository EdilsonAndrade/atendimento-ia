from pathlib import Path
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import PromptManagerService

# Caminhos locais para os arquivos Markdown (Plano de Contingência / Fallback)
PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"
GUARDRAIL_PATH = PROMPTS_DIR / "guardrails.md"


def _carregar_fallback_local(tenant_id, tabela_calendario_str, hora_atual_str, data_hoje_iso, contexto_formatado):
    """
    Função auxiliar interna para carregar os arquivos .md locais
    caso o tenant não possua configuração no banco de dados.
    """
    guardrails_text_local = GUARDRAIL_PATH.read_text(encoding="utf-8")
    
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        template_local = f.read()

    return template_local.format(
        guardrails=guardrails_text_local,
        tenant_id=tenant_id,
        tabela_calendario_str=tabela_calendario_str,
        hora_atual_str=hora_atual_str,
        data_hoje_iso=data_hoje_iso,
        contexto_formatado=contexto_formatado
    )


def carregar_operacional_prompt(tenant_id, tabela_calendario_str, hora_atual_str, data_hoje_iso, contexto_formatado):
    """
    Função principal chamada pelo agente.
    Tenta carregar do PostgreSQL. Se não houver vínculo para o tenant, usa o fallback local.
    """
    try:
        service = PromptManagerService(get_db_connection)
        
        # 1. Tenta buscar o prompt ativo vinculado ao tenant no banco
        active_prompt = service.repository.get_active_prompt_by_tenant(tenant_id)

        # 2. Se NÃO encontrou registro no banco para esse tenant, vai para o fallback local
        if not active_prompt:
            return _carregar_fallback_local(
                tenant_id=tenant_id,
                tabela_calendario_str=tabela_calendario_str,
                hora_atual_str=hora_atual_str,
                data_hoje_iso=data_hoje_iso,
                contexto_formatado=contexto_formatado
            )

        # 3. Se encontrou no banco, carrega os guardrails da tabela N:N (prompt_guardrails)
        prompt_template = active_prompt["conteudo"]
        prompt_id = active_prompt["id"]

        guardrails_db_list = service.repository.get_guardrails_by_prompt(prompt_id)
        
        # Concatena o texto de todos os guardrails vinculados a esse prompt
        guardrails_str = "\n\n".join([g["conteudo"] for g in guardrails_db_list])

        # 4. Formata o template dinâmico retornado do banco
        return prompt_template.format(
            guardrails=guardrails_str,
            tenant_id=tenant_id,
            tabela_calendario_str=tabela_calendario_str,
            hora_atual_str=hora_atual_str,
            data_hoje_iso=data_hoje_iso,
            contexto_formatado=contexto_formatado
        )

    except Exception as e:
        # Em caso de qualquer falha de conexão com o banco, garante que a aplicação não cai
        # e utiliza o arquivo local
        print(f"[WARN] Falha ao carregar prompt do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        return _carregar_fallback_local(
            tenant_id=tenant_id,
            tabela_calendario_str=tabela_calendario_str,
            hora_atual_str=hora_atual_str,
            data_hoje_iso=data_hoje_iso,
            contexto_formatado=contexto_formatado
        )
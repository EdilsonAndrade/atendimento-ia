from pathlib import Path
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import PromptManagerService

# Caminhos locais para os arquivos Markdown (Plano de Contingência / Fallback)
PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"
GUARDRAIL_PATH = PROMPTS_DIR / "guardrails.md"
INSTITUTIONAL_PROMPT_PATH = PROMPTS_DIR / "institutional_prompt.md"
CHITCHAT_PROMPT_PATH = PROMPTS_DIR / "chitchat_prompt.md"


def carregar_guardrails(tenant_id):
    """
    Resolve o texto de guardrails para o tenant: se houver prompt vinculado no
    banco, usa os guardrails dessa tabela N:N + os is_global=TRUE. Caso
    contrário (sem vínculo ou erro de conexão), usa o arquivo local guardrails.md.
    Reaproveitada tanto pelo fluxo operacional quanto pelo institucional.
    """
    try:
        service = PromptManagerService(get_db_connection)
        active_prompt = service.repository.get_active_prompt_by_tenant(tenant_id)

        if not active_prompt:
            return GUARDRAIL_PATH.read_text(encoding="utf-8")

        guardrails_db_list = service.repository.get_guardrails_by_prompt(active_prompt["id"])
        return "\n\n".join([g["conteudo"] for g in guardrails_db_list])

    except Exception as e:
        print(f"[WARN] Falha ao carregar guardrails do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        return GUARDRAIL_PATH.read_text(encoding="utf-8")


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


def carregar_institutional_prompt(tenant_id, contexto_formatado, historico_texto, pergunta_usuario):
    """
    Nível 1: vínculo institutional próprio do tenant no banco — usa o conteúdo e os
    guardrails vinculados especificamente a esse prompt (+ globais).
    Nível 2 (FR-004): sem vínculo institutional próprio, usa o template local
    institutional_prompt.md com os guardrails resolvidos pela mesma cadeia do
    operational_node do tenant (carregar_guardrails) — comportamento idêntico ao
    que existia antes desta feature, quando institutional sempre reaproveitava os
    guardrails do operational.
    """
    try:
        service = PromptManagerService(get_db_connection)
        institutional_prompt = service.repository.get_active_prompt_by_tenant(tenant_id, node_type="institutional")

        if institutional_prompt:
            guardrails_db_list = service.repository.get_guardrails_by_prompt(institutional_prompt["id"])
            guardrails_str = "\n\n".join([g["conteudo"] for g in guardrails_db_list])
            template = institutional_prompt["conteudo"]
        else:
            guardrails_str = carregar_guardrails(tenant_id)
            template = INSTITUTIONAL_PROMPT_PATH.read_text(encoding="utf-8")

        return template.format(
            guardrails=guardrails_str,
            tenant_id=tenant_id,
            contexto_formatado=contexto_formatado,
            historico_texto=historico_texto,
            pergunta_usuario=pergunta_usuario,
        )

    except Exception as e:
        print(f"[WARN] Falha ao carregar prompt institutional do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        template = INSTITUTIONAL_PROMPT_PATH.read_text(encoding="utf-8")
        return template.format(
            guardrails=GUARDRAIL_PATH.read_text(encoding="utf-8"),
            tenant_id=tenant_id,
            contexto_formatado=contexto_formatado,
            historico_texto=historico_texto,
            pergunta_usuario=pergunta_usuario,
        )


def carregar_chitchat_prompt(tenant_id):
    """
    Nível 1: vínculo chitchat próprio do tenant no banco.
    Nível 2 (FR-005): sem vínculo próprio, usa o prompt padrão único
    (is_default=TRUE, node_type='chitchat'), se existir.
    Nível 3: sem vínculo nem padrão configurado, usa o texto fixo local
    (chitchat_prompt.md + guardrails.md) — comportamento idêntico ao que existia
    antes desta feature, quando chitchat era 100% hardcoded.
    """
    try:
        service = PromptManagerService(get_db_connection)
        chitchat_prompt = service.repository.get_active_prompt_by_tenant(tenant_id, node_type="chitchat")

        if not chitchat_prompt:
            chitchat_prompt = service.repository.get_default_prompt(node_type="chitchat")

        if chitchat_prompt:
            guardrails_db_list = service.repository.get_guardrails_by_prompt(chitchat_prompt["id"])
            guardrails_str = "\n\n".join([g["conteudo"] for g in guardrails_db_list])
            template = chitchat_prompt["conteudo"]
        else:
            guardrails_str = GUARDRAIL_PATH.read_text(encoding="utf-8")
            template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")

        return template.format(guardrails=guardrails_str, tenant_id=tenant_id)

    except Exception as e:
        print(f"[WARN] Falha ao carregar prompt de chitchat do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")
        return template.format(
            guardrails=GUARDRAIL_PATH.read_text(encoding="utf-8"),
            tenant_id=tenant_id,
        )
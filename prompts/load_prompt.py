import re
from pathlib import Path
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import PromptManagerService

# Caminhos locais para os arquivos Markdown (Plano de Contingência / Fallback)
PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"
GUARDRAIL_PATH = PROMPTS_DIR / "guardrails.md"
INSTITUTIONAL_PROMPT_PATH = PROMPTS_DIR / "institutional_prompt.md"
CHITCHAT_PROMPT_PATH = PROMPTS_DIR / "chitchat_prompt.md"

GUARDRAILS_PLACEHOLDER = "{guardrails}"

# Casa apenas placeholders simples do tipo {nome_da_chave}. Chaves com qualquer
# outro caractere (ex: o {"nome": "x"} de um exemplo JSON dentro do prompt) não
# casam e ficam intactas no texto.
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _render_prompt(template: str, **valores) -> str:
    """
    Substitui os placeholders do template em UMA ÚNICA passada, em vez de usar
    str.format(). Dois motivos, ambos vindos de bugs reais em produção:

    1. str.format() levanta KeyError/IndexError para qualquer chave solta no
       texto (um exemplo JSON, uma chave de template que o admin escreveu à mão).
       Como o carregamento é envolvido em try/except, o prompt do tenant vinha do
       banco e era descartado silenciosamente, caindo no fallback local sem aviso.
       Aqui, placeholder desconhecido é preservado como texto, não quebra nada.

    2. Passada única: o conteúdo injetado (guardrails, contexto RAG, histórico)
       NÃO é reprocessado. Assim um guardrail cujo texto contenha "{guardrails}"
       não dispara substituição em cascata.
    """
    def _substituir(match):
        chave = match.group(1)
        if chave in valores:
            return str(valores[chave])
        return match.group(0)  # placeholder desconhecido permanece literal

    return _PLACEHOLDER_RE.sub(_substituir, template)


def _montar_guardrails_str(guardrails_list) -> str:
    """
    Concatena o conteúdo dos guardrails vindos do banco aplicando duas limpezas:

    - Remove o token "{guardrails}" de dentro do conteúdo. Guardrail é CONTEÚDO,
      nunca template; quando o admin cola um prompt inteiro (incluindo a linha do
      placeholder) dentro de um guardrail, esse token vazava literal para o prompt
      final enviado ao LLM.
    - Descarta guardrails com conteúdo repetido (comparando texto normalizado),
      evitando que o mesmo bloco de regras apareça duas vezes quando um guardrail
      global e um vinculado ao prompt carregam o mesmo texto.
    """
    vistos = set()
    partes = []

    for guardrail in guardrails_list:
        conteudo = (guardrail.get("conteudo") or "").replace(GUARDRAILS_PLACEHOLDER, "").strip()
        if not conteudo:
            continue

        chave_dedupe = " ".join(conteudo.split())
        if chave_dedupe in vistos:
            print(f"[WARN] Guardrail duplicado ignorado: {guardrail.get('titulo')!r}")
            continue

        vistos.add(chave_dedupe)
        partes.append(conteudo)

    return "\n\n".join(partes)


def _aplicar_guardrails(template: str, guardrails_str: str, **valores) -> str:
    """
    Renderiza o template e garante que os guardrails sempre cheguem ao prompt final.

    Se o template não tiver o placeholder {guardrails} (caso dos prompts gravados
    no banco antes desta correção, que já vieram com os guardrails "assados" no
    texto), os guardrails resolvidos são anexados ao final em vez de sumirem sem
    aviso — que era o comportamento anterior do str.format().
    """
    tem_placeholder = GUARDRAILS_PLACEHOLDER in template
    renderizado = _render_prompt(template, guardrails=guardrails_str, **valores)

    if guardrails_str and not tem_placeholder:
        print("[WARN] Prompt sem o placeholder {guardrails}; anexando os guardrails ao final.")
        renderizado = f"{renderizado}\n\n{guardrails_str}"

    return renderizado


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
        return _montar_guardrails_str(guardrails_db_list)

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

    return _aplicar_guardrails(
        template_local,
        guardrails_text_local,
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
        guardrails_str = _montar_guardrails_str(guardrails_db_list)

        # 4. Formata o template dinâmico retornado do banco
        return _aplicar_guardrails(
            prompt_template,
            guardrails_str,
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
            guardrails_str = _montar_guardrails_str(guardrails_db_list)
            template = institutional_prompt["conteudo"]
        else:
            guardrails_str = carregar_guardrails(tenant_id)
            template = INSTITUTIONAL_PROMPT_PATH.read_text(encoding="utf-8")

        return _aplicar_guardrails(
            template,
            guardrails_str,
            tenant_id=tenant_id,
            contexto_formatado=contexto_formatado,
            historico_texto=historico_texto,
            pergunta_usuario=pergunta_usuario,
        )

    except Exception as e:
        print(f"[WARN] Falha ao carregar prompt institutional do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        template = INSTITUTIONAL_PROMPT_PATH.read_text(encoding="utf-8")
        return _aplicar_guardrails(
            template,
            GUARDRAIL_PATH.read_text(encoding="utf-8"),
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
            guardrails_str = _montar_guardrails_str(guardrails_db_list)
            template = chitchat_prompt["conteudo"]
        else:
            guardrails_str = GUARDRAIL_PATH.read_text(encoding="utf-8")
            template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")

        return _aplicar_guardrails(template, guardrails_str, tenant_id=tenant_id)

    except Exception as e:
        print(f"[WARN] Falha ao carregar prompt de chitchat do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")
        return _aplicar_guardrails(
            template,
            GUARDRAIL_PATH.read_text(encoding="utf-8"),
            tenant_id=tenant_id,
        )
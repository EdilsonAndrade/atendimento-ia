import re
from pathlib import Path
from infrastructure.connection import get_db_connection
from modules.prompt_manager.prompt_manager_service import PromptManagerService
from prompts.prompt_resolver import (
    PromptConfigurationError,
    resolver_guardrails_list,
    resolver_prompt_e_guardrails,
)
from modules.observability.interface.logger_factory import get_logger as get_obs_logger

# Caminhos locais para os arquivos Markdown (Plano de Contingência / Fallback)
PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PROMPTS_DIR / "operactional_prompt.md"
GUARDRAIL_PATH = PROMPTS_DIR / "guardrails.md"
INSTITUTIONAL_PROMPT_PATH = PROMPTS_DIR / "institutional_prompt.md"
CHITCHAT_PROMPT_PATH = PROMPTS_DIR / "chitchat_prompt.md"

GUARDRAILS_PLACEHOLDER = "{guardrails}"
CONTEXTO_PLACEHOLDER = "{contexto_formatado}"

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
    Renderiza o template e garante que os guardrails e o contexto do RAG sempre
    cheguem ao prompt final.

    Se o template não tiver o placeholder {guardrails} (caso dos prompts gravados
    no banco antes desta correção, que já vieram com os guardrails "assados" no
    texto), os guardrails resolvidos são anexados ao final em vez de sumirem sem
    aviso — que era o comportamento anterior do str.format().

    Mesma rede de segurança para {contexto_formatado}: um prompt de tenant escrito
    à mão no banco pode omitir esse placeholder (aconteceu em produção — o tenant
    tinha uma seção "Contexto da Conversa" só com {historico_texto}, sem o bloco de
    conhecimento). Sem isso, o RAG inteiro é descartado em silêncio pelo
    _render_prompt e o modelo responde só com o que está escrito no prompt (ex.:
    repetindo os serviços do few-shot example), nunca com a base de conhecimento.
    """
    tem_guardrails_placeholder = GUARDRAILS_PLACEHOLDER in template
    tem_contexto_placeholder = CONTEXTO_PLACEHOLDER in template
    renderizado = _render_prompt(template, guardrails=guardrails_str, **valores)

    if guardrails_str and not tem_guardrails_placeholder:
        print("[WARN] Prompt sem o placeholder {guardrails}; anexando os guardrails ao final.")
        renderizado = f"{renderizado}\n\n{guardrails_str}"

    contexto_formatado = valores.get("contexto_formatado")
    if contexto_formatado and not tem_contexto_placeholder:
        print("[WARN] Prompt sem o placeholder {contexto_formatado}; anexando o contexto da base de conhecimento ao final.")
        renderizado = f"{renderizado}\n\n--- CONTEXT FROM KNOWLEDGE BASE ---\n{contexto_formatado}"

    return renderizado


def carregar_guardrails(tenant_id):
    """
    Resolve o texto de guardrails para o tenant, SEMPRE a partir do banco.

    Com prompt vinculado: guardrails da tabela N:N + os is_global=TRUE.
    Sem prompt vinculado: os is_global=TRUE, que antes desta correção nunca eram
    consultados neste caminho — o early-return devolvia o guardrails.md e fazia
    "guardrail global" significar, na prática, "global só para quem já tem prompt
    vinculado". Justamente o tenant novo, que mais precisa da rede de proteção
    padrão, ficava sem.

    O arquivo local só é lido quando o banco está indisponível, para não derrubar
    o atendimento.
    """
    try:
        service = PromptManagerService(get_db_connection)
        active_prompt = service.repository.get_active_prompt_by_tenant(tenant_id)
        prompt_id = active_prompt["id"] if active_prompt else None

        return _montar_guardrails_str(resolver_guardrails_list(service, tenant_id, prompt_id))

    except Exception as e:
        print(f"[WARN] Falha ao carregar guardrails do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        get_obs_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_loader").error(
            message=f"Failed to load guardrails from DB, using local fallback: {e}",
            method="prompts.load_prompt.carregar_guardrails",
            line=136,
            thread_id="unknown",
            extra={"error": str(e)},
        )
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
    Função principal chamada pelo agente. Carrega EXCLUSIVAMENTE do banco.

    Tenant sem prompt operacional vinculado não cai mais no arquivo local: isso é
    erro de configuração, não estado normal de operação, e absorvê-lo em silêncio
    fazia um cliente receber o texto genérico do projeto como se fosse o dele. O
    erro sobe como PromptConfigurationError, com alerta identificando o tenant.

    ATENÇÃO À ORDEM DOS `except` ABAIXO. `PromptConfigurationError` precisa vir
    antes de `Exception`; se as duas trocarem de lugar, o erro de configuração
    volta a ser engolido pelo fallback local e o defeito que este ticket corrige
    reaparece sem fazer barulho nenhum. Há teste dedicado a essa ordem.
    """
    try:
        service = PromptManagerService(get_db_connection)

        prompt_template, guardrails_str = resolver_prompt_e_guardrails(
            service, tenant_id, "operational", _montar_guardrails_str
        )

        return _aplicar_guardrails(
            prompt_template,
            guardrails_str,
            tenant_id=tenant_id,
            tabela_calendario_str=tabela_calendario_str,
            hora_atual_str=hora_atual_str,
            data_hoje_iso=data_hoje_iso,
            contexto_formatado=contexto_formatado
        )

    except PromptConfigurationError as e:
        # Erro de CONFIGURAÇÃO: falha e alerta. Os guardrails globais já foram
        # resolvidos e viajam na exceção — segurança não falha junto com o prompt.
        print(
            f"[ALERTA] Configuração ausente: tenant {tenant_id!r} não tem prompt "
            f"'operational' vinculado. O atendimento NÃO será respondido até que um "
            f"prompt seja vinculado no Painel Administrador. Detalhe: {e}"
        )
        get_obs_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_loader").error(
            message=f"Tenant has no operational prompt configured — service is DOWN for this tenant: {e}",
            method="prompts.load_prompt.carregar_operacional_prompt",
            line=193,
            thread_id="unknown",
            extra={"error": "PROMPT_CONFIGURATION_MISSING"},
        )
        raise

    except Exception as e:
        # Falha de INFRAESTRUTURA (banco indisponível): mantém o atendimento em pé
        # com o conteúdo local. É o único caminho que ainda lê os arquivos .md.
        print(f"[WARN] Falha ao carregar prompt do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        get_obs_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_loader").error(
            message=f"Failed to load operational prompt from DB, using local fallback: {e}",
            method="prompts.load_prompt.carregar_operacional_prompt",
            line=203,
            thread_id="unknown",
            extra={"error": str(e)},
        )
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

        # Este nó NÃO exige vínculo (FR-008), então o resolver devolve template=None
        # em vez de levantar erro quando não há vínculo institucional próprio.
        template, guardrails_str = resolver_prompt_e_guardrails(
            service, tenant_id, "institutional", _montar_guardrails_str
        )

        if template is None:
            # Nível 2: sem vínculo próprio, usa o template local E herda os
            # guardrails resolvidos pela cadeia do operational_node do tenant —
            # comportamento preservado do FR-004 da feature anterior.
            #
            # A herança precisa ser explícita aqui: resolver pelo node_type
            # 'institutional' devolveria apenas os globais, perdendo os guardrails
            # próprios do prompt operacional do tenant.
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
        get_obs_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_loader").error(
            message=f"Failed to load institutional prompt from DB, using local fallback: {e}",
            method="prompts.load_prompt.carregar_institutional_prompt",
            line=255,
            thread_id="unknown",
            extra={"error": str(e)},
        )
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

        # Nível 1: vínculo próprio. Este nó NÃO exige vínculo (FR-008), então o
        # resolver devolve template=None em vez de levantar erro.
        template, guardrails_str = resolver_prompt_e_guardrails(
            service, tenant_id, "chitchat", _montar_guardrails_str
        )

        if template is None:
            # Nível 2: prompt padrão do banco, garantido pelo seed. Os guardrails
            # desse prompt substituem os globais já resolvidos, porque agora há um
            # prompt concreto ao qual eles podem estar vinculados.
            default_prompt = service.repository.get_default_prompt(node_type="chitchat")
            if default_prompt:
                template = default_prompt["conteudo"]
                guardrails_str = _montar_guardrails_str(
                    service.repository.get_guardrails_by_prompt(default_prompt["id"])
                )
            else:
                # Nível 3: sem vínculo e sem padrão. Com o seed em vigor isto não
                # deveria ocorrer; mantido para não quebrar bancos ainda não semeados.
                template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")

        return _aplicar_guardrails(template, guardrails_str, tenant_id=tenant_id)

    except Exception as e:
        print(f"[WARN] Falha ao carregar prompt de chitchat do banco para tenant {tenant_id}: {e}. Usando fallback local.")
        get_obs_logger(tenant_id=tenant_id, tenant_name=tenant_id, agent="prompt_loader").error(
            message=f"Failed to load chitchat prompt from DB, using local fallback: {e}",
            method="prompts.load_prompt.carregar_chitchat_prompt",
            line=303,
            thread_id="unknown",
            extra={"error": str(e)},
        )
        template = CHITCHAT_PROMPT_PATH.read_text(encoding="utf-8")
        return _aplicar_guardrails(
            template,
            GUARDRAIL_PATH.read_text(encoding="utf-8"),
            tenant_id=tenant_id,
        )
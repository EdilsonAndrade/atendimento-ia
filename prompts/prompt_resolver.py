"""Resolução de prompt e guardrails para o runtime do agente (EDI-43).

Este módulo concentra a POLÍTICA de resolução: o que buscar no banco, quando um
estado é erro de configuração e quando é indisponibilidade. A RENDERIZAÇÃO
(substituição de placeholders, dedupe, anexação de guardrails) continua em
`prompts/load_prompt.py`, que também mantém as funções públicas chamadas pelos
nós do agente.

Por que a separação: `load_prompt.py` já carrega três helpers que resolvem bugs
reais de produção (substituição em passada única, dedupe por texto normalizado,
anexação quando o template não tem o placeholder). Misturar a política nova
dentro deles tornaria ilegível justamente o ponto mais sensível do sistema.

O defeito que este módulo corrige: antes, "tenant sem prompt vinculado" e "banco
fora do ar" caíam no MESMO `except Exception`, que devolvia o conteúdo dos
arquivos .md do projeto. Os dois casos exigem comportamentos opostos — o
primeiro precisa falhar e alertar, o segundo precisa continuar atendendo — então
precisam ser tipos distintos. Daí `PromptConfigurationError`.
"""

from typing import Any, Dict, List, Optional

# Nós que exigem vínculo explícito de prompt com o tenant. Decisão do EDI-43:
# apenas o operational. O institutional herda a resolução do operational e o
# chitchat usa o prompt is_default semeado — as duas cadeias permanecem como
# estavam, para limitar o risco de regressão.
NODES_QUE_EXIGEM_VINCULO = frozenset({"operational"})


class PromptConfigurationError(Exception):
    """Erro de CONFIGURAÇÃO: o tenant não tem prompt vinculado para um nó que exige.

    Distinto de uma falha de infraestrutura. Uma falha de banco deve cair no
    fallback local e manter o atendimento em pé; esta aqui deve falhar e alertar,
    porque significa que alguém esqueceu de vincular um prompt ao cliente.

    Carrega `guardrails_str` porque guardrail é política de segurança da
    plataforma e não pode falhar junto com o prompt: mesmo neste caminho de erro,
    quem tratar a exceção ainda tem os guardrails globais resolvidos em mãos.
    """

    def __init__(self, tenant_id: str, node_type: str, guardrails_str: str = ""):
        self.tenant_id = tenant_id
        self.node_type = node_type
        self.guardrails_str = guardrails_str
        super().__init__(
            f"Tenant {tenant_id!r} não possui prompt ativo vinculado para o nó "
            f"{node_type!r}. Vincule um prompt a este tenant no Painel Administrador."
        )


def resolver_guardrails_list(service, tenant_id: str, prompt_id: Optional[str]) -> List[Dict[str, Any]]:
    """Devolve os guardrails aplicáveis, SEMPRE a partir do banco.

    Com prompt vinculado: `get_guardrails_by_prompt` já cobre "vinculados ao
    prompt + todos os is_global" numa query só (`WHERE g.is_global = TRUE OR
    pg.prompt_id = %s`), então não há motivo para unir listas em Python — isso
    só criaria uma segunda implementação da mesma regra, com risco de divergir.

    Sem prompt vinculado: os globais continuam valendo. Este é o caminho que
    antes devolvia o arquivo guardrails.md e nunca consultava o banco, fazendo
    com que "guardrail global" significasse na prática "global para quem já tem
    prompt vinculado".
    """
    if prompt_id:
        return service.repository.get_guardrails_by_prompt(prompt_id)
    return service.repository.get_global_guardrails()


def resolver_prompt_e_guardrails(service, tenant_id: str, node_type: str, montar_guardrails):
    """Resolve (template, guardrails_str) para um tenant e um nó, lendo só do banco.

    Devolve `(None, guardrails_str)` quando não há prompt vinculado e o nó NÃO
    exige vínculo — o chamador decide o que usar como template (o .md local, no
    caso do institutional, ou o prompt is_default, no caso do chitchat).

    Levanta `PromptConfigurationError` quando não há prompt vinculado e o nó
    exige — com os guardrails já resolvidos anexados à exceção.

    Não captura exceções de banco: elas devem subir para o chamador, que as trata
    como indisponibilidade e cai no fallback local. Capturar aqui reintroduziria
    a confusão entre os dois casos que este módulo existe para separar.
    """
    active_prompt = service.repository.get_active_prompt_by_tenant(tenant_id, node_type=node_type)
    prompt_id = active_prompt["id"] if active_prompt else None

    # Os guardrails são resolvidos ANTES de qualquer decisão sobre o prompt.
    # Ordem deliberada: garante que eles existam mesmo no caminho de erro abaixo.
    guardrails_str = montar_guardrails(resolver_guardrails_list(service, tenant_id, prompt_id))

    if not active_prompt:
        if node_type in NODES_QUE_EXIGEM_VINCULO:
            raise PromptConfigurationError(tenant_id, node_type, guardrails_str)
        return None, guardrails_str

    return active_prompt["conteudo"], guardrails_str

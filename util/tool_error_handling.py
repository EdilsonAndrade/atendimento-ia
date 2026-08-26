import functools
import logging

from modules.observability.interface.logger_factory import get_logger as get_obs_logger

logger = logging.getLogger(__name__)


def safe_tool_result(fallback: str, tenant_id: str = None):
    """
    Decorator para funções de tool do agente (aplicado ANTES de `@tool`, ou seja,
    mais próximo da função original — `@tool` deve ficar por cima).

    Captura qualquer exceção técnica lançada pela tool (erro de banco, erro de API
    externa, etc.), loga a exceção completa (com tenant_id/thread_id quando presentes)
    e devolve `fallback` no lugar de propagar a exceção ou de devolver o texto cru de
    `str(e)` como resultado da tool — esse texto cru ficava salvo no histórico da
    conversa e era reenviado ao LLM em todo turno seguinte, contaminando o contexto
    (EDI-59). Isso também evita que o `ToolNode` do LangGraph (`handle_tool_errors=True`)
    capture a exceção propagada e gere seu próprio `ToolMessage` de erro genérico
    contendo o `repr()` cru da exceção.

    `tenant_id`, quando a tool é construída por uma factory que já tem o tenant_id
    disponível por closure (ex.: `build_agendar_tool`), pode ser passado diretamente
    aqui. Quando a tool recebe `tenant_id` como argumento de chamada (ex.: as tools
    de `modules/agendamento/*.py`), ele é extraído automaticamente dos kwargs.

    Não se aplica a mensagens de negócio devolvidas intencionalmente pela tool
    (ex.: "horário já ocupado") — essas continuam sendo retornadas normalmente,
    pois nunca chegam a lançar uma exceção.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                resolved_tenant_id = tenant_id or kwargs.get("tenant_id")
                thread_id = kwargs.get("thread_id") or kwargs.get("base_thread_id")
                logger.error(
                    "Falha ao executar tool '%s' (tenant_id=%s, thread_id=%s): %s: %s",
                    func.__name__,
                    resolved_tenant_id,
                    thread_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                safe_tenant_id = resolved_tenant_id or "unknown"
                get_obs_logger(tenant_id=safe_tenant_id, tenant_name=safe_tenant_id, agent="tool_executor").error(
                    message=f"Tool '{func.__name__}' failed: {type(exc).__name__}: {exc}",
                    method="util.tool_error_handling.safe_tool_result",
                    line=35,
                    thread_id=thread_id or "unknown",
                    extra={"tool_name": func.__name__, "error": str(exc), "error_type": type(exc).__name__},
                )
                return fallback
        return wrapper
    return decorator

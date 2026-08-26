"""Main observability wiring and initialization."""

import asyncio
import logging
from modules.observability.application.log_service import LogService
from modules.observability.infrastructure.log_sender_factory import get_log_sender
from modules.observability.interface.logger_factory import set_log_service
from app.core.observability_config import get_observability_config

logger = logging.getLogger(__name__)

_log_service: LogService | None = None


def init_observability() -> None:
    """Constrói o LogService e o registra globalmente (chamado no import do
    módulo, antes do uvicorn ter um event loop rodando).

    NÃO inicia a task de flush aqui: `asyncio.get_event_loop()` chamado fora de
    uma coroutine/callback cria (ou pega) um loop que o uvicorn nunca executa —
    a task de `_flush_loop()` fica presa a esse loop órfão e nunca roda de
    verdade. `get_logger()` continua funcionando (só enfileira, não precisa de
    loop), mas o flush para o Loki nunca dispara. Ver `start_observability_flush()`.
    """
    global _log_service

    try:
        config = get_observability_config()

        if not config.is_enabled():
            logger.info("Observability disabled (GRAFANA_LOKI_* env vars not configured)")
            set_log_service(None)
            return

        sender = get_log_sender(config)
        _log_service = LogService(sender)
        set_log_service(_log_service)
        logger.info("Observability configured: waiting for app startup to begin streaming to Grafana Loki")

    except Exception as e:
        logger.error(f"Failed to initialize observability: {e}", exc_info=True)


def start_observability_flush() -> None:
    """Inicia a task de flush do LogService. DEVE ser chamado de dentro de um
    handler `async def` do FastAPI (`@app.on_event("startup")`), nunca de um
    handler síncrono nem do import do módulo — só um handler async roda direto
    no event loop real do uvicorn (handlers sync rodam em threadpool, sem
    acesso a esse loop); é o único ponto em que `LogService.start()` consegue
    criar a task no loop que efetivamente vai executá-la.
    """
    if _log_service:
        _log_service.start()
        logger.info("Observability flush task started: logs streaming to Grafana Loki")


async def shutdown_observability() -> None:
    """Shutdown observability module on application shutdown."""
    global _log_service

    if _log_service:
        try:
            await _log_service.stop()
            logger.info("Observability shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down observability: {e}", exc_info=True)


def get_log_service() -> LogService | None:
    """Get the global LogService instance (None if disabled)."""
    return _log_service

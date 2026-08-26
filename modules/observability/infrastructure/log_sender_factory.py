"""Factory for creating LogSender instances based on configuration."""

from modules.observability.domain.ports.log_sender import LogSender
from modules.observability.infrastructure.loki_client import LokiLogSender, NoOpLogSender
from app.core.observability_config import ObservabilitySettings


def get_log_sender(config: ObservabilitySettings) -> LogSender:
    """Factory: return real or no-op sender based on environment configuration.

    Args:
        config: ObservabilitySettings with Loki URL and API token

    Returns:
        LokiLogSender if configured, NoOpLogSender otherwise (safe default)
    """
    if not config.is_enabled():
        return NoOpLogSender()

    return LokiLogSender(
        url=config.grafana_loki_url,
        api_token=config.grafana_loki_api_token,
        user_id=config.grafana_loki_user_id,
    )

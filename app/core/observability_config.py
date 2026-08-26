"""Observability configuration using Pydantic Settings."""

import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class ObservabilitySettings(BaseSettings):
    """Configuration for Grafana Loki observability."""

    grafana_loki_url: str | None = None
    """Loki push API endpoint (e.g., https://org.grafana.net/loki/api/v1/push)"""

    grafana_loki_api_token: str | None = None
    """Grafana Cloud API token for authentication"""

    grafana_loki_user_id: str | None = None
    """Grafana Cloud Loki Instance/User ID (numeric). O push API do Loki hospedado
    no Grafana Cloud exige HTTP Basic Auth (user_id:api_token) — só o Bearer token
    sozinho retorna 401. Encontrar em: Grafana Cloud Portal > sua stack > Loki >
    Details (campo "User" na seção de configuração de envio de dados)."""

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields from .env (other app settings)
    )

    def is_enabled(self) -> bool:
        """Check if observability is configured."""
        return bool(self.grafana_loki_url and self.grafana_loki_api_token and self.grafana_loki_user_id)


def get_observability_config() -> ObservabilitySettings:
    """Load observability configuration from environment."""
    return ObservabilitySettings()

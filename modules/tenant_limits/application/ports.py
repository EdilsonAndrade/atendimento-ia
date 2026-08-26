"""Portas (interfaces) da Application layer — Princípio III da constituição.

A Application depende só destas abstrações para tudo que é externo (leitura de
config do tenant, contagem de uso, claim de notificação, e-mail). As implementações
concretas vivem na Infrastructure layer e são injetadas de fora.
"""
from typing import Protocol


class TenantLimitConfigPort(Protocol):
    def get_limit_and_emails(self, tenant_id: str) -> tuple[int | None, list[str]]:
        """Devolve (`monthly_message_limit`, `notification_emails`) do tenant.
        Tenant inexistente devolve (`None`, `[]`) — mesmo efeito de "sem limite"."""
        ...


class UsageCounterPort(Protocol):
    def count_current_month(self, tenant_id: str) -> int:
        """Quantidade de chamadas de LLM (linhas em `chat_token_usage`) do tenant
        no mês corrente."""
        ...


class NotificationClaimPort(Protocol):
    def try_claim(self, tenant_id: str, year_month: str, milestone: int) -> bool:
        """Tenta reservar o direito de enviar o alerta deste marco neste mês para
        este tenant. Devolve True só na primeira vez (claim atômico) — chamadas
        seguintes no mesmo mês/marco devolvem False."""
        ...


class GlobalRecipientsPort(Protocol):
    def list_active_emails(self) -> list[str]:
        """E-mails internos da InterasisAI ativos; fallback para
        `contato@interasisai.com.br` quando a lista está vazia (aplicado aqui, não
        persistido como linha especial)."""
        ...


class EmailSenderPort(Protocol):
    def send(self, to: list[str], subject: str, body: str) -> None:
        """Nunca deve lançar exceção que interrompa o chamador — falha de envio é
        responsabilidade da implementação registrar e engolir."""
        ...

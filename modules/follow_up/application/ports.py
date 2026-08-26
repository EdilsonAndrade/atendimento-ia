"""Ports (Protocols) do módulo follow_up — Application layer."""
from typing import Protocol

from modules.follow_up.domain.follow_up_entry import FollowUpEntry


class FollowUpQueueRepository(Protocol):
    def save(self, entry: FollowUpEntry) -> bool:
        """Grava a entrada. Retorna False quando active_thread_id já existe (claim
        idempotente via ON CONFLICT DO NOTHING) — reprocessar a mesma sessão expirada
        nunca duplica (FR-004)."""
        ...

    def list_by_tenant(
        self, tenant_id: str, status: str | None = None, outcome: str | None = None
    ) -> list[FollowUpEntry]:
        ...

    def list_all(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
    ) -> list[FollowUpEntry]:
        """Lista entre tenants (painel admin, EDI-65). `tenant_id` opcional filtra;
        omitido, devolve de todos os tenants."""
        ...

    def update(
        self,
        tenant_id: str,
        entry_id: int,
        status: str | None = None,
        draft_message: str | None = None,
        approved_by: str | None = None,
    ) -> FollowUpEntry | None:
        """Atualiza status e/ou draft_message de um registro do próprio tenant.
        Devolve None quando `entry_id` não existe (ou não pertence a `tenant_id` —
        isolamento multi-tenant, nunca vaza/edita registro de outro tenant)."""
        ...


class SessionOutcomeClassifierPort(Protocol):
    def classify(
        self,
        conversation_text: str,
        oferta_vigente_texto: str | None,
        oferta_vigente_validade,
    ) -> dict:
        """Devolve {"outcome": str, "summary": str, "draft_message": str | None}."""
        ...

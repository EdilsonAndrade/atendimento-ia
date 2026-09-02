from typing import Optional

from modules.vetorizacao.gerenciador_vetores import GerenciadorVetores


class PgVectorKnowledgeBaseAdapter:
    """Implementa VectorStorePort sobre o GerenciadorVetores (pgvector) já existente.

    reindex() sempre remove os vetores antigos do tenant antes de inserir os novos —
    substitui, não acumula (ver research.md #3).
    """

    def __init__(self, gerenciador: Optional[GerenciadorVetores] = None):
        self._gerenciador = gerenciador

    @property
    def gerenciador(self) -> GerenciadorVetores:
        # Instanciação preguiçosa: GerenciadorVetores() conecta ao Postgres/pgvector no
        # construtor, então só deve acontecer quando o adapter é de fato usado.
        if self._gerenciador is None:
            self._gerenciador = GerenciadorVetores()
        return self._gerenciador

    def reindex(self, tenant_id: str, content: str) -> None:
        self.gerenciador.deletar_por_tenant(tenant_id)
        self.gerenciador.criar_banco_com_textos([content], tenant_id)

    def delete(self, tenant_id: str) -> None:
        self.gerenciador.deletar_por_tenant(tenant_id)

    def reindex_item(self, tenant_id: str, item_id: str, content: str) -> None:
        """Substitui só os vetores daquele item (EDI-39) — não afeta os demais itens do tenant."""
        self.gerenciador.deletar_por_item(tenant_id, item_id)
        self.gerenciador.criar_banco_com_textos([content], tenant_id, item_id=item_id)

    def delete_item(self, tenant_id: str, item_id: str) -> None:
        self.gerenciador.deletar_por_item(tenant_id, item_id)

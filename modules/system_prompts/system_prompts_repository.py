from typing import Any, Dict, List, Optional
from psycopg.rows import dict_row


class SystemPromptsRepository:
    """Acesso à tabela `system_prompts` (EDI-71).

    Diferente de `modules/prompt_manager` (prompts POR TENANT, com N:N de
    guardrails), aqui o conjunto de linhas é fixo — os 4 `prompt_key`s
    semeados pela migration `0010_system_prompts` — e o versionamento é
    apenas de 2 níveis (`current_version`/`last_version`), sem histórico
    além disso. Não há endpoint de criação/exclusão de linha.
    """

    def __init__(self, get_connection_func):
        self.get_connection = get_connection_func

    def get_all(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, prompt_key, titulo, current_version, last_version, created_at, updated_at
                    FROM system_prompts
                    ORDER BY prompt_key
                """)
                return cur.fetchall()

    def get_by_key(self, prompt_key: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, prompt_key, titulo, current_version, last_version, created_at, updated_at
                    FROM system_prompts
                    WHERE prompt_key = %s
                """, (prompt_key,))
                return cur.fetchone()

    def update_current_version(self, prompt_key: str, conteudo: str) -> Optional[Dict[str, Any]]:
        """Grava `conteudo` como nova `current_version`, deslocando a versão
        vigente para `last_version` — nunca perde o conteúdo anterior."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    UPDATE system_prompts
                    SET last_version = current_version,
                        current_version = %s,
                        updated_at = NOW()
                    WHERE prompt_key = %s
                    RETURNING id, prompt_key, titulo, current_version, last_version, created_at, updated_at
                """, (conteudo, prompt_key))
                return cur.fetchone()

    def rollback(self, prompt_key: str) -> Optional[Dict[str, Any]]:
        """Troca `current_version` <-> `last_version`. Reversível: aplicar
        duas vezes seguidas volta ao estado original."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    UPDATE system_prompts
                    SET current_version = last_version,
                        last_version = current_version,
                        updated_at = NOW()
                    WHERE prompt_key = %s
                    RETURNING id, prompt_key, titulo, current_version, last_version, created_at, updated_at
                """, (prompt_key,))
                return cur.fetchone()

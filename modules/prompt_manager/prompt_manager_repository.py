from typing import List, Optional, Dict, Any
from psycopg.rows import dict_row


class PromptManagerRepository:
    def __init__(self, get_connection_func):
        self.get_connection = get_connection_func

    # --- GUARDRAILS ---
    def get_all_guardrails(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, titulo, conteudo, is_global, created_at, updated_at 
                    FROM guardrails 
                    ORDER BY created_at DESC
                """)
                return cur.fetchall()

    def create_guardrail(self, titulo: str, conteudo: str, is_global: bool) -> Dict[str, Any]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    INSERT INTO guardrails (titulo, conteudo, is_global)
                    VALUES (%s, %s, %s)
                    RETURNING id, titulo, conteudo, is_global, created_at, updated_at
                """, (titulo, conteudo, is_global))
                return cur.fetchone()

    # --- PROMPTS ---
    def get_all_prompts(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT 
                        p.id, 
                        p.titulo, 
                        p.conteudo, 
                        p.is_default, 
                        p.created_at, 
                        p.updated_at,
                        COALESCE(
                            ARRAY_AGG(pg.guardrail_id) FILTER (WHERE pg.guardrail_id IS NOT NULL), 
                            '{}'
                        ) AS guardrail_ids
                    FROM prompts p
                    LEFT JOIN prompt_guardrails pg ON p.id = pg.prompt_id
                    GROUP BY p.id
                    ORDER BY p.created_at DESC
                """)
                return cur.fetchall()

    def create_prompt(self, titulo: str, conteudo: str, is_default: bool) -> Dict[str, Any]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    INSERT INTO prompts (titulo, conteudo, is_default)
                    VALUES (%s, %s, %s)
                    RETURNING id, titulo, conteudo, is_default, created_at, updated_at
                """, (titulo, conteudo, is_default))
                return cur.fetchone()

    # --- ASSOCIAÇÕES (N:N) ---
    def sync_prompt_guardrails(self, prompt_id: str, guardrail_ids: List[str]):
        """Remove associações antigas e insere as novas para o prompt."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM prompt_guardrails WHERE prompt_id = %s", (prompt_id,))
                
                if guardrail_ids:
                    records = [(prompt_id, g_id) for g_id in guardrail_ids]
                    cur.executemany("""
                        INSERT INTO prompt_guardrails (prompt_id, guardrail_id)
                        VALUES (%s, %s)
                    """, records)

    def sync_tenant_prompt(self, tenant_id: str, prompt_id: str, custom_override: Optional[str] = None):
        """Associa um tenant a um prompt na tabela tenant_prompts."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active, custom_content_override)
                    VALUES (%s, %s, TRUE, %s)
                    ON CONFLICT (tenant_id, prompt_id) 
                    DO UPDATE SET is_active = TRUE, custom_content_override = EXCLUDED.custom_content_override, updated_at = NOW()
                """, (tenant_id, prompt_id, custom_override))

    # --- RESOLUÇÃO DO PROMPT (RUNTIME DO AGENTE) ---
    def get_active_prompt_by_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Busca o prompt associado e ativo para o tenant específico."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT p.id, p.titulo, COALESCE(tp.custom_content_override, p.conteudo) AS conteudo
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE
                    LIMIT 1
                """, (tenant_id,))
                return cur.fetchone()

    def get_guardrails_by_prompt(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Busca todos os guardrails vinculados ao prompt via N:N."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT g.id, g.titulo, g.conteudo
                    FROM guardrails g
                    JOIN prompt_guardrails pg ON g.id = pg.guardrail_id
                    WHERE pg.prompt_id = %s
                """, (prompt_id,))
                return cur.fetchall()
    
    def update_prompt(self, prompt_id: str, titulo: str, conteudo: str, is_default: bool) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    UPDATE prompts 
                    SET titulo = %s, conteudo = %s, is_default = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, titulo, conteudo, is_default, created_at, updated_at
                """, (titulo, conteudo, is_default, prompt_id))
                return cur.fetchone()
            
    def update_guardrail(self, guardrail_id: str, titulo: str, conteudo: str, is_global: bool) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    UPDATE guardrails 
                    SET titulo = %s, conteudo = %s, is_global = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, titulo, conteudo, is_global, created_at, updated_at
                """, (titulo, conteudo, is_global, guardrail_id))
                return cur.fetchone()
            
    def get_tenant_prompt_details(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Busca o prompt associado ao tenant e a lista de guardrails vinculados a esse prompt."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # 1. Pega os dados do vínculo do tenant com o prompt
                cur.execute("""
                    SELECT 
                        tp.tenant_id,
                        tp.prompt_id,
                        tp.is_active,
                        tp.custom_content_override,
                        p.titulo AS prompt_titulo,
                        p.conteudo AS prompt_conteudo_base,
                        p.is_default AS prompt_is_default
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE
                    LIMIT 1
                """, (tenant_id,))
                
                tenant_data = cur.fetchone()
                if not tenant_data:
                    return None

                # 2. Pega os guardrails vinculados a este prompt na tabela N:N
                cur.execute("""
                    SELECT g.id, g.titulo, g.conteudo, g.is_global
                    FROM guardrails g
                    JOIN prompt_guardrails pg ON g.id = pg.guardrail_id
                    WHERE pg.prompt_id = %s
                """, (tenant_data["prompt_id"],))
                
                guardrails = cur.fetchall()

                # Retorna os dados agrupados
                return {
                    **tenant_data,
                    "guardrails_associados": guardrails
                }
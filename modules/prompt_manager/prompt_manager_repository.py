from typing import List, Optional, Dict, Any
from psycopg.rows import dict_row

NODE_TYPES = ("operational", "institutional", "chitchat")


class PromptManagerRepository:
    def __init__(self, get_connection_func):
        self.get_connection = get_connection_func

    def ensure_node_type_schema(self):
        """Adiciona a coluna node_type (e suas constraints) de forma idempotente.

        Mesmo padrão de DDL idempotente já usado em init_thread_sessions_table()
        (modules/ia/thread_session.py): este repositório não usa framework de
        migração, então o schema é garantido no início de cada método que
        depende de node_type, em vez do __init__ — construir o repositório não
        deve, por si só, exigir uma conexão real de banco (ver testes unitários
        que trocam .repository por um fake logo após instanciar o service).
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE prompts ADD COLUMN IF NOT EXISTS node_type TEXT NOT NULL DEFAULT 'operational'"
                )
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'prompts_node_type_check'
                        ) THEN
                            ALTER TABLE prompts ADD CONSTRAINT prompts_node_type_check
                                CHECK (node_type IN ('operational', 'institutional', 'chitchat'));
                        END IF;
                    END $$;
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS prompts_one_default_per_node
                    ON prompts (node_type) WHERE is_default = TRUE
                    """
                )

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
    def get_all_prompts(self, node_type: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        p.id,
                        p.titulo,
                        p.conteudo,
                        p.is_default,
                        p.node_type,
                        p.created_at,
                        p.updated_at,
                        COALESCE(
                            ARRAY_AGG(pg.guardrail_id) FILTER (WHERE pg.guardrail_id IS NOT NULL),
                            '{}'
                        ) AS guardrail_ids
                    FROM prompts p
                    LEFT JOIN prompt_guardrails pg ON p.id = pg.prompt_id
                    WHERE %(node_type)s::text IS NULL OR p.node_type = %(node_type)s::text
                    GROUP BY p.id
                    ORDER BY p.created_at DESC
                """, {"node_type": node_type})
                return cur.fetchall()

    def create_prompt(self, titulo: str, conteudo: str, is_default: bool, node_type: str = "operational") -> Dict[str, Any]:
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    INSERT INTO prompts (titulo, conteudo, is_default, node_type)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, titulo, conteudo, is_default, node_type, created_at, updated_at
                """, (titulo, conteudo, is_default, node_type))
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
        """Associa um tenant a um prompt na tabela tenant_prompts.

        Garante que apenas um vínculo fica ativo por tenant **por node_type**.
        Desativa automaticamente vínculos antigos do MESMO node_type quando um
        novo é ativado — vínculos ativos de outros node_type (ex.: chitchat)
        não são afetados ao vincular um novo prompt operational (FR-009).
        """
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Desativa vínculos antigos do tenant do MESMO node_type do prompt novo (exceto o novo)
                cur.execute("""
                    UPDATE tenant_prompts tp
                    SET is_active = FALSE, updated_at = NOW()
                    FROM prompts p
                    WHERE tp.prompt_id = p.id
                      AND tp.tenant_id = %(tenant_id)s
                      AND tp.prompt_id != %(prompt_id)s
                      AND p.node_type = (SELECT node_type FROM prompts WHERE id = %(prompt_id)s)
                """, {"tenant_id": tenant_id, "prompt_id": prompt_id})

                # 2. Ativa o novo vínculo (ou reativa se já foi vinculado antes)
                cur.execute("""
                    INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active, custom_content_override)
                    VALUES (%s, %s, TRUE, %s)
                    ON CONFLICT (tenant_id, prompt_id)
                    DO UPDATE SET is_active = TRUE, custom_content_override = EXCLUDED.custom_content_override, updated_at = NOW()
                """, (tenant_id, prompt_id, custom_override))

    # --- RESOLUÇÃO DO PROMPT (RUNTIME DO AGENTE) ---
    def get_active_prompt_by_tenant(self, tenant_id: str, node_type: str = "operational") -> Optional[Dict[str, Any]]:
        """Busca o prompt associado e ativo para o tenant específico, no node_type pedido."""
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT p.id, p.titulo, COALESCE(tp.custom_content_override, p.conteudo) AS conteudo
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE AND p.node_type = %s
                    LIMIT 1
                """, (tenant_id, node_type))
                return cur.fetchone()

    def get_guardrails_by_prompt(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Busca os guardrails vinculados ao prompt via N:N, MAIS todos os guardrails
        marcados como is_global=TRUE (aplicados a todo tenant automaticamente, sem
        precisar de associação manual em prompt_guardrails)."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT DISTINCT g.id, g.titulo, g.conteudo
                    FROM guardrails g
                    LEFT JOIN prompt_guardrails pg ON g.id = pg.guardrail_id AND pg.prompt_id = %s
                    WHERE g.is_global = TRUE OR pg.prompt_id = %s
                """, (prompt_id, prompt_id))
                return cur.fetchall()
    
    def update_prompt(self, prompt_id: str, titulo: str, conteudo: str, is_default: bool, node_type: str = "operational") -> Optional[Dict[str, Any]]:
        """Atualiza um prompt. PUT substitui o estado completo do recurso — assim como
        titulo/conteudo/is_default, node_type também é sempre o valor enviado pelo
        chamador (mesma convenção já usada pelos demais campos deste endpoint)."""
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    UPDATE prompts
                    SET titulo = %s, conteudo = %s, is_default = %s, node_type = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, titulo, conteudo, is_default, node_type, created_at, updated_at
                """, (titulo, conteudo, is_default, node_type, prompt_id))
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
            
    def get_default_prompt(self, node_type: str = "operational") -> Optional[Dict[str, Any]]:
        """Busca o prompt marcado como padrão (is_default=TRUE) do node_type pedido,
        usado como fallback para tenants sem vínculo ativo nesse node_type."""
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, titulo, conteudo
                    FROM prompts
                    WHERE is_default = TRUE AND node_type = %s
                    LIMIT 1
                """, (node_type,))
                return cur.fetchone()

    def get_global_guardrails(self) -> List[Dict[str, Any]]:
        """Busca todos os guardrails marcados como is_global=TRUE, aplicados
        automaticamente a qualquer tenant, independente de vínculo de prompt."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT id, titulo, conteudo, is_global
                    FROM guardrails
                    WHERE is_global = TRUE
                """)
                return cur.fetchall()

    def delete_prompt(self, prompt_id: str) -> bool:
        """Remove um prompt e seus vínculos (prompt_guardrails, tenant_prompts)."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM prompt_guardrails WHERE prompt_id = %s", (prompt_id,))
                cur.execute("DELETE FROM tenant_prompts WHERE prompt_id = %s", (prompt_id,))
                cur.execute("DELETE FROM prompts WHERE id = %s", (prompt_id,))
                return cur.rowcount > 0

    def seed_missing_node_prompts(self, chitchat_default_titulo: str, chitchat_default_conteudo: str) -> None:
        """Seed idempotente (User Story 3 / research.md R5), roda com segurança em toda inicialização:

        1. Garante 1 prompt is_default=TRUE, node_type='chitchat' (cria apenas se nenhum existir ainda),
           usando o texto hoje fixo no código como conteúdo inicial.
        2. Para cada tenant com vínculo operational ativo e SEM vínculo institutional ativo, copia o
           prompt operational ativo (conteúdo + prompt_guardrails) para um novo prompt
           node_type='institutional' e cria o vínculo institutional correspondente.

        Não duplica nada ao rodar novamente: tenants que já têm vínculo institutional (seedado antes ou
        configurado manualmente pelo admin) são ignorados; o prompt padrão de chitchat só é criado uma vez.
        """
        self.ensure_node_type_schema()

        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id FROM prompts WHERE is_default = TRUE AND node_type = 'chitchat' LIMIT 1"
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO prompts (titulo, conteudo, is_default, node_type)
                        VALUES (%s, %s, TRUE, 'chitchat')
                        """,
                        (chitchat_default_titulo, chitchat_default_conteudo),
                    )

        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT tp.tenant_id, tp.prompt_id, p.titulo, p.conteudo
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.is_active = TRUE AND p.node_type = 'operational'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM tenant_prompts tp2
                          JOIN prompts p2 ON tp2.prompt_id = p2.id
                          WHERE tp2.tenant_id = tp.tenant_id
                            AND tp2.is_active = TRUE
                            AND p2.node_type = 'institutional'
                      )
                    """
                )
                tenants_sem_institutional = cur.fetchall()

                for row in tenants_sem_institutional:
                    cur.execute(
                        """
                        INSERT INTO prompts (titulo, conteudo, is_default, node_type)
                        VALUES (%s, %s, FALSE, 'institutional')
                        RETURNING id
                        """,
                        (row["titulo"], row["conteudo"]),
                    )
                    new_prompt_id = cur.fetchone()["id"]

                    cur.execute(
                        """
                        INSERT INTO prompt_guardrails (prompt_id, guardrail_id)
                        SELECT %s, guardrail_id FROM prompt_guardrails WHERE prompt_id = %s
                        """,
                        (new_prompt_id, row["prompt_id"]),
                    )

                    cur.execute(
                        """
                        INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active)
                        VALUES (%s, %s, TRUE)
                        ON CONFLICT (tenant_id, prompt_id)
                        DO UPDATE SET is_active = TRUE, updated_at = NOW()
                        """,
                        (row["tenant_id"], new_prompt_id),
                    )

    def get_tenant_prompt_details(self, tenant_id: str, node_type: str = "operational") -> Optional[Dict[str, Any]]:
        """Busca o prompt associado ao tenant (no node_type pedido) e a lista de
        guardrails vinculados a esse prompt."""
        self.ensure_node_type_schema()
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # 1. Pega os dados do vínculo do tenant com o prompt, para o node_type pedido
                cur.execute("""
                    SELECT
                        tp.tenant_id,
                        tp.prompt_id,
                        tp.is_active,
                        tp.custom_content_override,
                        p.titulo AS prompt_titulo,
                        p.conteudo AS prompt_conteudo_base,
                        p.is_default AS prompt_is_default,
                        p.node_type AS prompt_node_type
                    FROM tenant_prompts tp
                    JOIN prompts p ON tp.prompt_id = p.id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE AND p.node_type = %s
                    LIMIT 1
                """, (tenant_id, node_type))
                
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
from typing import List, Optional, Dict, Any
from psycopg.rows import dict_row

NODE_TYPES = ("operational", "institutional", "chitchat")


class PromptManagerRepository:
    """Acesso às tabelas de prompts, guardrails e seus vínculos por tenant.

    O schema (incluindo a coluna `node_type`, sua constraint de valores válidos e o
    índice único parcial de prompt padrão por node_type) é garantido pelas migrations
    em `migrations/` — ver EDI-37. Até então este repositório executava DDL idempotente
    no início de cada método, ou seja, uma alteração de estrutura por requisição atendida.
    """

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
    def get_all_prompts(self, node_type: Optional[str] = None) -> List[Dict[str, Any]]:
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

    def get_prompt_by_id(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Busca um prompt pelo id. Usado na validação do cadastro de tenant, que
        precisa saber se o prompt existe E qual o seu node_type."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, titulo, conteudo, is_default, node_type FROM prompts WHERE id = %s",
                    (prompt_id,),
                )
                return cur.fetchone()

    def link_tenants_bulk(
        self, prompt_id: str, tenant_ids: List[str], custom_override: Optional[str] = None
    ) -> None:
        """Vincula UM prompt a N tenants numa única transação (FR-019/FR-020).

        Mesma semântica do sync_tenant_prompt singular, aplicada em lote: desativa
        os vínculos ativos do MESMO node_type de cada tenant e ativa o novo, sem
        tocar em vínculos de outros node_type (FR-021).

        Uma única conexão para toda a operação: se qualquer tenant falhar, nenhum
        vínculo é aplicado.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tenant_prompts tp
                    SET is_active = FALSE, updated_at = NOW()
                    FROM prompts p
                    WHERE tp.prompt_id = p.id
                      AND tp.tenant_id = ANY(%(tenant_ids)s)
                      AND tp.prompt_id != %(prompt_id)s
                      AND p.node_type = (SELECT node_type FROM prompts WHERE id = %(prompt_id)s)
                """, {"tenant_ids": list(tenant_ids), "prompt_id": prompt_id})

                cur.executemany("""
                    INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active, custom_content_override)
                    VALUES (%s, %s, TRUE, %s)
                    ON CONFLICT (tenant_id, prompt_id)
                    DO UPDATE SET is_active = TRUE,
                                  custom_content_override = EXCLUDED.custom_content_override,
                                  updated_at = NOW()
                """, [(tenant_id, prompt_id, custom_override) for tenant_id in tenant_ids])

    def get_existing_tenant_ids(self, tenant_ids: List[str]) -> List[str]:
        """Devolve, dentre os informados, os tenant_ids que realmente existem.
        A diferença em relação à lista original são os bloqueadores do erro
        TENANT_NOT_FOUND."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM tenants WHERE id = ANY(%s)", (list(tenant_ids),))
                return [row[0] for row in cur.fetchall()]

    # --- BLOQUEIOS DE EXCLUSÃO (EDI-43) ---

    def get_tenants_by_prompt(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Tenants com vínculo ATIVO neste prompt.

        Serve a dois propósitos que são a mesma pergunta vista de ângulos
        diferentes: listar quem usa o prompt (tela de associação em massa) e
        listar quem impede a exclusão dele (blockers do 409). Vínculos inativos
        não entram: são histórico, não configuração vigente.
        """
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT t.id, t.name
                    FROM tenant_prompts tp
                    JOIN tenants t ON t.id = tp.tenant_id
                    WHERE tp.prompt_id = %s AND tp.is_active = TRUE
                    ORDER BY t.id
                """, (prompt_id,))
                return cur.fetchall()

    # Nome antigo, mantido porque expressa a intenção no contexto de exclusão.
    get_tenants_blocking_prompt = get_tenants_by_prompt

    def get_prompts_linked_to_tenant_active(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Prompts com vínculo ATIVO a este tenant (um por `node_type`, tipicamente).

        Usado pela exclusão em cascata de tenant (EDI-45): só vínculos ativos
        entram na decisão de exclusividade, pela mesma razão de
        `get_tenants_by_prompt` — vínculo inativo é histórico, não configuração
        vigente.
        """
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT p.id, p.titulo, p.node_type
                    FROM tenant_prompts tp
                    JOIN prompts p ON p.id = tp.prompt_id
                    WHERE tp.tenant_id = %s AND tp.is_active = TRUE
                    ORDER BY p.node_type
                """, (tenant_id,))
                return cur.fetchall()

    def get_prompts_blocking_guardrail(self, guardrail_id: str) -> List[Dict[str, Any]]:
        """Prompts que usam este guardrail E têm ao menos um tenant ativo.

        Um guardrail associado apenas a prompts sem tenant ativo não bloqueia:
        não há proteção em vigor a perder.
        """
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT p.id, p.titulo AS name, COUNT(DISTINCT tp.tenant_id) AS tenant_count
                    FROM prompt_guardrails pg
                    JOIN prompts p ON p.id = pg.prompt_id
                    JOIN tenant_prompts tp ON tp.prompt_id = p.id AND tp.is_active = TRUE
                    WHERE pg.guardrail_id = %s
                    GROUP BY p.id, p.titulo
                    ORDER BY p.titulo
                """, (guardrail_id,))
                return cur.fetchall()

    def get_guardrail_by_id(self, guardrail_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, titulo, conteudo, is_global FROM guardrails WHERE id = %s",
                    (guardrail_id,),
                )
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

    def get_guardrail_links_for_prompt(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Guardrails vinculados a este prompt via `prompt_guardrails` (associação
        explícita apenas — SEM misturar `is_global`, ao contrário de
        `get_guardrails_by_prompt`).

        Usado pela exclusão em cascata de tenant (EDI-45) para decidir, um a um,
        se cada guardrail explicitamente associado ao prompt pode ser excluído
        de fato ou deve ser preservado (global ou usado por outro prompt).
        """
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT g.id, g.titulo, g.conteudo, g.is_global
                    FROM prompt_guardrails pg
                    JOIN guardrails g ON g.id = pg.guardrail_id
                    WHERE pg.prompt_id = %s
                    ORDER BY g.titulo
                """, (prompt_id,))
                return cur.fetchall()


    def update_prompt(self, prompt_id: str, titulo: str, conteudo: str, is_default: bool, node_type: str = "operational") -> Optional[Dict[str, Any]]:
        """Atualiza um prompt. PUT substitui o estado completo do recurso — assim como
        titulo/conteudo/is_default, node_type também é sempre o valor enviado pelo
        chamador (mesma convenção já usada pelos demais campos deste endpoint)."""
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

    def delete_guardrail(self, guardrail_id: str) -> bool:
        """Remove um guardrail e seus vínculos (prompt_guardrails)."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM prompt_guardrails WHERE guardrail_id = %s", (guardrail_id,))
                cur.execute("DELETE FROM guardrails WHERE id = %s", (guardrail_id,))
                return cur.rowcount > 0

    def seed_missing_node_prompts(
        self,
        chitchat_default_titulo: str,
        chitchat_default_conteudo: str,
        node_prompt_seeds: Optional[Dict[str, Dict[str, str]]] = None,
        global_guardrail_seed: Optional[Dict[str, str]] = None,
    ) -> None:
        """Seed idempotente, roda com segurança em toda inicialização:

        1. Garante 1 prompt is_default=TRUE, node_type='chitchat' (cria apenas se nenhum existir ainda).
        2. (EDI-43) Garante ao menos 1 prompt por node_type, a partir dos arquivos .md do projeto,
           para o combo do cadastro de tenant nunca aparecer vazio numa instalação nova.
        3. (EDI-43) Garante 1 guardrail is_global=TRUE, a partir do guardrails.md. Reproduz o
           comportamento anterior — em que todo tenant recebia esse texto — sem depender de
           associação manual.
        4. Para cada tenant com vínculo operational ativo e SEM vínculo institutional ativo, copia o
           prompt operational ativo (conteúdo + prompt_guardrails) para um novo prompt
           node_type='institutional' e cria o vínculo institutional correspondente.

        Não duplica nada ao rodar novamente e NUNCA sobrescreve conteúdo editado pelo admin: o
        critério é sempre "existe algum registro deste tipo?", nunca o título — que o admin pode
        renomear, o que faria um seed baseado em título recriar duplicatas a cada boot.

        `node_prompt_seeds`: {node_type: {"titulo": str, "conteudo": str}}
        `global_guardrail_seed`: {"titulo": str, "conteudo": str}

        Ambos são opcionais para não quebrar chamadores existentes (e os testes que já passavam
        apenas o chitchat).
        """

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

                # 2. Um prompt semente por node_type (EDI-43 / FR-011).
                for node_type, seed in (node_prompt_seeds or {}).items():
                    cur.execute(
                        "SELECT id FROM prompts WHERE node_type = %s LIMIT 1",
                        (node_type,),
                    )
                    if cur.fetchone():
                        continue

                    cur.execute(
                        """
                        INSERT INTO prompts (titulo, conteudo, is_default, node_type)
                        VALUES (%s, %s, FALSE, %s)
                        """,
                        (seed["titulo"], seed["conteudo"], node_type),
                    )

                # 3. Um guardrail global (EDI-43 / FR-012). O critério é a existência de
                # QUALQUER is_global=TRUE: se o admin já mantém um, não criamos outro.
                if global_guardrail_seed:
                    cur.execute("SELECT id FROM guardrails WHERE is_global = TRUE LIMIT 1")
                    if not cur.fetchone():
                        cur.execute(
                            """
                            INSERT INTO guardrails (titulo, conteudo, is_global)
                            VALUES (%s, %s, TRUE)
                            """,
                            (global_guardrail_seed["titulo"], global_guardrail_seed["conteudo"]),
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

                # 2. Guardrails vinculados a este prompt na N:N MAIS os is_global.
                #
                # O `OR g.is_global = TRUE` é uma correção do EDI-43: esta query
                # antes fazia só o JOIN em prompt_guardrails, enquanto o runtime
                # (get_guardrails_by_prompt) já incluía os globais. Resultado: a
                # tela do admin mostrava MENOS guardrails do que o agente
                # aplicava, para o mesmo tenant. A cláusula precisa ser idêntica
                # à de get_guardrails_by_prompt — duas queries com a mesma regra
                # escrita em dois lugares foi exatamente como a divergência
                # nasceu.
                cur.execute("""
                    SELECT DISTINCT g.id, g.titulo, g.conteudo, g.is_global
                    FROM guardrails g
                    LEFT JOIN prompt_guardrails pg ON g.id = pg.guardrail_id AND pg.prompt_id = %s
                    WHERE g.is_global = TRUE OR pg.prompt_id = %s
                """, (tenant_data["prompt_id"], tenant_data["prompt_id"]))

                guardrails = cur.fetchall()

                # Retorna os dados agrupados
                return {
                    **tenant_data,
                    "guardrails_associados": guardrails
                }
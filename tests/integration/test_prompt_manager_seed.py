import uuid

CHITCHAT_DEFAULT_TITULO = "Chitchat Padrão (EDI-42 teste seed)"
CHITCHAT_DEFAULT_CONTEUDO = "Conteudo padrao de chitchat (teste seed EDI-42)."


def test_seed_creates_single_chitchat_default_and_is_idempotent(repo, db_cleanup):
    # Só rastreia para apagar se este teste for quem criou o default — se um
    # default legítimo já existia (ex.: seed real do app), o teste não deve mexer nele.
    ja_existia = repo.get_default_prompt(node_type="chitchat") is not None

    repo.seed_missing_node_prompts(CHITCHAT_DEFAULT_TITULO, CHITCHAT_DEFAULT_CONTEUDO)
    repo.seed_missing_node_prompts(CHITCHAT_DEFAULT_TITULO, CHITCHAT_DEFAULT_CONTEUDO)  # roda 2x, não duplica

    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prompts WHERE is_default = TRUE AND node_type = 'chitchat'")
            assert cur.fetchone()[0] == 1

    if not ja_existia:
        db_cleanup.track_prompt(repo.get_default_prompt(node_type="chitchat"))


def test_seed_copies_operational_prompt_and_guardrails_to_institutional(repo, db_cleanup):
    tenant_id = f"test-tenant-edi42-seed-{uuid.uuid4().hex[:8]}"
    db_cleanup.track_tenant(tenant_id)

    operational_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Operational Seed EDI42", conteudo="conteudo op seed {guardrails}",
        is_default=False, node_type="operational",
    ))
    guardrail = db_cleanup.track_guardrail(
        repo.create_guardrail(titulo="Guardrail Seed EDI42", conteudo="Regra copiada no seed.", is_global=False)
    )
    repo.sync_prompt_guardrails(operational_prompt["id"], [str(guardrail["id"])])
    repo.sync_tenant_prompt(tenant_id, operational_prompt["id"])

    # Antes do seed: sem vínculo institutional
    assert repo.get_active_prompt_by_tenant(tenant_id, node_type="institutional") is None

    repo.seed_missing_node_prompts(CHITCHAT_DEFAULT_TITULO, CHITCHAT_DEFAULT_CONTEUDO)

    institutional_prompt = repo.get_active_prompt_by_tenant(tenant_id, node_type="institutional")
    assert institutional_prompt is not None
    db_cleanup.track_prompt(institutional_prompt)  # copiado pelo seed, precisa ser limpo também
    assert institutional_prompt["conteudo"] == operational_prompt["conteudo"]

    institutional_guardrails = repo.get_guardrails_by_prompt(institutional_prompt["id"])
    assert any(g["conteudo"] == "Regra copiada no seed." for g in institutional_guardrails)

    # Idempotente: rodar de novo não cria um segundo prompt institutional para o mesmo tenant
    repo.seed_missing_node_prompts(CHITCHAT_DEFAULT_TITULO, CHITCHAT_DEFAULT_CONTEUDO)
    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM tenant_prompts tp
                JOIN prompts p ON tp.prompt_id = p.id
                WHERE tp.tenant_id = %s AND tp.is_active = TRUE AND p.node_type = 'institutional'
                """,
                (tenant_id,),
            )
            assert cur.fetchone()[0] == 1


def test_seed_does_not_touch_tenant_that_already_has_institutional_link(repo, db_cleanup):
    tenant_id = f"test-tenant-edi42-seed-existing-{uuid.uuid4().hex[:8]}"
    db_cleanup.track_tenant(tenant_id)

    operational_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Operational Seed EDI42 B", conteudo="conteudo op b", is_default=False, node_type="operational"
    ))
    own_institutional_prompt = db_cleanup.track_prompt(repo.create_prompt(
        titulo="Institutional Manual EDI42", conteudo="conteudo institutional manual",
        is_default=False, node_type="institutional",
    ))
    repo.sync_tenant_prompt(tenant_id, operational_prompt["id"])
    repo.sync_tenant_prompt(tenant_id, own_institutional_prompt["id"])

    repo.seed_missing_node_prompts(CHITCHAT_DEFAULT_TITULO, CHITCHAT_DEFAULT_CONTEUDO)

    institutional_ativo = repo.get_active_prompt_by_tenant(tenant_id, node_type="institutional")
    assert institutional_ativo["id"] == own_institutional_prompt["id"]
    assert institutional_ativo["conteudo"] == "conteudo institutional manual"


# --- EDI-43: seed a partir dos .md do projeto -------------------------------
#
# Estes testes rodam contra o banco de desenvolvimento, que normalmente já foi
# semeado pela subida da API. Por isso afirmam o INVARIANTE ("existe ao menos
# um") e a IDEMPOTÊNCIA (contagem não muda), em vez de exigir banco vazio — que
# não é reproduzível numa suíte compartilhada. A validação de banco realmente
# vazio está no roteiro do quickstart.md.

SEEDS_POR_NODE = {
    "operational": {"titulo": "Operacional EDI43 teste", "conteudo": "op {guardrails}"},
    "institutional": {"titulo": "Institucional EDI43 teste", "conteudo": "inst {guardrails}"},
    "chitchat": {"titulo": "Chitchat EDI43 teste", "conteudo": "chit {guardrails}"},
}
GUARDRAIL_GLOBAL_SEED = {"titulo": "Global EDI43 teste", "conteudo": "regra global semeada"}


def _contar(repo, sql, params=None):
    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()[0]


def _seed(repo):
    repo.seed_missing_node_prompts(
        CHITCHAT_DEFAULT_TITULO,
        CHITCHAT_DEFAULT_CONTEUDO,
        node_prompt_seeds=SEEDS_POR_NODE,
        global_guardrail_seed=GUARDRAIL_GLOBAL_SEED,
    )


def test_seed_garante_ao_menos_um_prompt_por_node_type(repo):
    """FR-011: o combo do cadastro de tenant nunca pode aparecer vazio."""
    _seed(repo)

    for node_type in ("operational", "institutional", "chitchat"):
        total = _contar(repo, "SELECT COUNT(*) FROM prompts WHERE node_type = %s", (node_type,))
        assert total >= 1, f"nenhum prompt para node_type={node_type}"


def test_seed_garante_ao_menos_um_guardrail_global(repo):
    """FR-012: a rede de proteção padrão não depende de associação manual."""
    _seed(repo)

    assert _contar(repo, "SELECT COUNT(*) FROM guardrails WHERE is_global = TRUE") >= 1


def test_seed_rodando_duas_vezes_nao_duplica(repo):
    """FR-013 / SC-007."""
    _seed(repo)

    antes_prompts = _contar(repo, "SELECT COUNT(*) FROM prompts")
    antes_guardrails = _contar(repo, "SELECT COUNT(*) FROM guardrails")

    _seed(repo)

    assert _contar(repo, "SELECT COUNT(*) FROM prompts") == antes_prompts
    assert _contar(repo, "SELECT COUNT(*) FROM guardrails") == antes_guardrails


def test_seed_nao_sobrescreve_conteudo_editado_pelo_admin(repo, db_cleanup):
    """FR-013: a edição do admin precisa sobreviver ao próximo restart."""
    _seed(repo)

    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM prompts WHERE node_type = 'operational' LIMIT 1")
            prompt_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE prompts SET conteudo = %s WHERE id = %s",
                ("CONTEUDO EDITADO PELO ADMIN {guardrails}", prompt_id),
            )

    _seed(repo)

    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT conteudo FROM prompts WHERE id = %s", (prompt_id,))
            assert cur.fetchone()[0] == "CONTEUDO EDITADO PELO ADMIN {guardrails}"


def test_conteudo_semeado_preserva_o_placeholder_cru(repo):
    """FR-014: se o seed renderizasse o texto, os guardrails congelariam e
    deixariam de ser injetados a cada atendimento."""
    _seed(repo)

    with repo.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM prompts WHERE conteudo LIKE %s AND node_type = 'operational'",
                ("%{guardrails}%",),
            )
            assert cur.fetchone()[0] >= 1

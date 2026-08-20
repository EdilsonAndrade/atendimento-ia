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

import pytest

from modules.tenant_limits.application.notify_usage_milestones import NotifyUsageMilestonesUseCase


class _FakeConfigPort:
    def __init__(self, limit=None, emails=None):
        self._limit = limit
        self._emails = emails or []

    def get_limit_and_emails(self, tenant_id):
        return self._limit, self._emails


class _FakeUsageCounter:
    def __init__(self, count=0):
        self._count = count

    def count_current_month(self, tenant_id):
        return self._count


class _FakeClaimPort:
    def __init__(self, already_claimed: set[tuple] | None = None):
        self.calls = []
        self._already_claimed = already_claimed or set()

    def try_claim(self, tenant_id, year_month, milestone):
        self.calls.append((tenant_id, year_month, milestone))
        key = (tenant_id, year_month, milestone)
        if key in self._already_claimed:
            return False
        self._already_claimed.add(key)
        return True


class _FakeGlobalRecipients:
    def __init__(self, emails=None):
        self._emails = emails or ["contato@interasisai.com.br"]

    def list_active_emails(self):
        return self._emails


class _FakeEmailSender:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


def _use_case(limit, emails, count, claim_port=None, global_recipients=None, email_sender=None):
    return (
        NotifyUsageMilestonesUseCase(
            _FakeConfigPort(limit=limit, emails=emails),
            _FakeUsageCounter(count=count),
            claim_port or _FakeClaimPort(),
            global_recipients or _FakeGlobalRecipients(),
            email_sender or _FakeEmailSender(),
        ),
    )


def test_sem_limite_nao_faz_nada():
    email_sender = _FakeEmailSender()
    claim_port = _FakeClaimPort()
    (use_case,) = _use_case(limit=None, emails=["a@x.com"], count=9999, claim_port=claim_port, email_sender=email_sender)

    use_case.execute("tenant_x")

    assert claim_port.calls == []
    assert email_sender.sent == []


def test_cruzar_50_por_cento_envia_email_so_ao_tenant():
    email_sender = _FakeEmailSender()
    (use_case,) = _use_case(limit=1000, emails=["a@x.com"], count=500, email_sender=email_sender)

    use_case.execute("tenant_x")

    assert len(email_sender.sent) == 1
    assert email_sender.sent[0]["to"] == ["a@x.com"]
    assert "50%" in email_sender.sent[0]["subject"] or "50" in email_sender.sent[0]["body"]


def test_cruzar_100_por_cento_envia_tambem_aos_globais():
    email_sender = _FakeEmailSender()
    global_recipients = _FakeGlobalRecipients(emails=["ops@interasisai.com.br"])
    (use_case,) = _use_case(
        limit=1000, emails=["a@x.com"], count=1000, email_sender=email_sender, global_recipients=global_recipients
    )

    use_case.execute("tenant_x")

    # 50%, 80% e 100% são todos cruzados nesta única chamada (rajada) — 3 e-mails.
    assert len(email_sender.sent) == 3
    email_100 = email_sender.sent[-1]
    assert set(email_100["to"]) == {"a@x.com", "ops@interasisai.com.br"}


def test_marco_ja_reclamado_nao_reenvia():
    email_sender = _FakeEmailSender()
    claim_port = _FakeClaimPort(already_claimed={("tenant_x", _current_year_month(), 50)})
    (use_case,) = _use_case(limit=1000, emails=["a@x.com"], count=500, claim_port=claim_port, email_sender=email_sender)

    use_case.execute("tenant_x")

    assert email_sender.sent == []


def test_rajada_de_45_para_85_envia_50_e_80_na_mesma_chamada():
    email_sender = _FakeEmailSender()
    (use_case,) = _use_case(limit=1000, emails=["a@x.com"], count=850, email_sender=email_sender)

    use_case.execute("tenant_x")

    assert len(email_sender.sent) == 2


def test_falha_interna_nunca_propaga():
    class _RaisingConfigPort:
        def get_limit_and_emails(self, tenant_id):
            raise RuntimeError("Postgres indisponível")

    use_case = NotifyUsageMilestonesUseCase(
        _RaisingConfigPort(), _FakeUsageCounter(), _FakeClaimPort(), _FakeGlobalRecipients(), _FakeEmailSender()
    )

    use_case.execute("tenant_x")  # não deve lançar


def _current_year_month() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

"""Listagem/busca de tenants (grid da tela de Tenants, EDI-46).

`GET /tenants` deixou de exigir `q`: sem termo, lista tudo paginado; com
termo, filtra por match parcial em id/name — mesmo endpoint, mesmo contrato de
resposta (`{items, total}`, cada item já com as tags de prompt/guardrail).
"""

from modules.tenant.tenant_repository import TenantRepository
from modules.tenant.tenant_service import TenantService


class FakeCursor:
    def __init__(self, rows, count=None):
        self._rows = rows
        self._count = count
        self.executed = None

    def execute(self, query, params=None):
        self.executed = (query, params)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return (self._count,)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows, count=None):
        self._rows = rows
        self._count = count if count is not None else len(rows)
        self.last_cursor = None

    def cursor(self, **kwargs):
        self.last_cursor = FakeCursor(self._rows, self._count)
        return self.last_cursor


def make_repository(monkeypatch, rows, count=None):
    connection = FakeConnection(rows, count)
    monkeypatch.setattr(
        "modules.tenant.tenant_repository.get_db_connection",
        lambda: connection,
    )
    return TenantRepository(), connection


# --- TenantRepository.list_tenants / count_tenants --------------------------


def test_list_tenants_maps_rows_to_dicts(monkeypatch):
    rows = [("1234", "Barbearia Central", "cal@x", ["barbeariacentral.com.br"], None, None)]
    repo, _ = make_repository(monkeypatch, rows)

    result = repo.list_tenants(None)

    assert result == [
        {
            "id": "1234",
            "name": "Barbearia Central",
            "google_calendar_id": "cal@x",
            "allowed_domains": ["barbeariacentral.com.br"],
            "created_at": None,
            "updated_at": None,
        }
    ]


def test_list_tenants_sem_termo_nao_usa_ilike(monkeypatch):
    repo, connection = make_repository(monkeypatch, [])

    repo.list_tenants(None, limit=20, offset=0)

    query, params = connection.last_cursor.executed
    assert "ILIKE" not in query
    assert "WHERE" not in query
    assert params == (20, 0)


def test_list_tenants_com_termo_usa_ilike_limit_e_offset(monkeypatch):
    repo, connection = make_repository(monkeypatch, [])

    repo.list_tenants("abc", limit=5, offset=10)

    query, params = connection.last_cursor.executed
    assert "ILIKE" in query
    assert params == ("%abc%", "%abc%", 5, 10)


def test_list_tenants_default_limit_e_offset(monkeypatch):
    repo, connection = make_repository(monkeypatch, [])

    repo.list_tenants("abc")

    _, params = connection.last_cursor.executed
    assert params[-2:] == (20, 0)


def test_count_tenants_sem_termo(monkeypatch):
    repo, connection = make_repository(monkeypatch, [], count=42)

    total = repo.count_tenants(None)

    assert total == 42
    query, params = connection.last_cursor.executed
    assert "ILIKE" not in query
    assert params is None


def test_count_tenants_com_termo(monkeypatch):
    repo, connection = make_repository(monkeypatch, [], count=3)

    total = repo.count_tenants("abc")

    assert total == 3
    query, params = connection.last_cursor.executed
    assert "ILIKE" in query
    assert params == ("%abc%", "%abc%")


# --- TenantService.search_tenants: contrato antigo, intacto (Base de --------
# Conhecimento depende dele — ver tenant_service.py) -------------------------


def test_service_search_tenants_delegates_to_repository(monkeypatch):
    monkeypatch.setattr(
        "modules.tenant.tenant_repository.get_db_connection",
        lambda: FakeConnection([]),
    )
    service = TenantService()

    calls = {}

    class FakeRepo:
        def list_tenants(self, term, limit=20, offset=0):
            calls["args"] = (term, limit, offset)
            return [{"id": "1234"}]

    service.tenant_repository = FakeRepo()

    result = service.search_tenants("barbearia")

    assert result == [{"id": "1234"}]
    assert calls["args"] == ("barbearia", 20, 0)

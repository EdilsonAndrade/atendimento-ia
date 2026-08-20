from modules.tenant.tenant_repository import TenantRepository
from modules.tenant.tenant_service import TenantService


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, query, params=None):
        self.executed = (query, params)

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self._rows = rows
        self.last_cursor = None

    def cursor(self, **kwargs):
        self.last_cursor = FakeCursor(self._rows)
        return self.last_cursor


def make_repository(monkeypatch, rows):
    connection = FakeConnection(rows)
    monkeypatch.setattr(
        "modules.tenant.tenant_repository.get_db_connection",
        lambda: connection,
    )
    return TenantRepository(), connection


def test_search_tenants_maps_rows_to_dicts(monkeypatch):
    rows = [("1234", "Barbearia Central", "cal@x", ["barbeariacentral.com.br"], None, None)]
    repo, _ = make_repository(monkeypatch, rows)

    result = repo.search_tenants("barbearia")

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


def test_search_tenants_uses_case_insensitive_partial_match_and_limit(monkeypatch):
    repo, connection = make_repository(monkeypatch, [])

    repo.search_tenants("abc", limit=5)

    query, params = connection.last_cursor.executed
    assert "ILIKE" in query
    assert params == ("%abc%", "%abc%", 5)


def test_search_tenants_default_limit_is_twenty(monkeypatch):
    repo, connection = make_repository(monkeypatch, [])

    repo.search_tenants("abc")

    _, params = connection.last_cursor.executed
    assert params[-1] == 20


def test_service_search_tenants_delegates_to_repository(monkeypatch):
    monkeypatch.setattr(
        "modules.tenant.tenant_repository.get_db_connection",
        lambda: FakeConnection([]),
    )
    service = TenantService()

    calls = {}

    class FakeRepo:
        def search_tenants(self, term, limit=20):
            calls["args"] = (term, limit)
            return [{"id": "1234"}]

    service.tenant_repository = FakeRepo()

    result = service.search_tenants("barbearia")

    assert result == [{"id": "1234"}]
    assert calls["args"] == ("barbearia", 20)

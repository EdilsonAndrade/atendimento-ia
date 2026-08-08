import asyncio
import unittest
from unittest.mock import patch

from modules.webhook import whatsapp


class FakeCursor:
    description = [("id",), ("tenant_id",), ("instance_name",), ("status",)]

    def __init__(self):
        self.executed_query = None
        self.executed_params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params):
        self.executed_query = query
        self.executed_params = params

    def fetchone(self):
        return (7, "tenant-123", "barbearia", "connecting")


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class SalvarInstanciaBancoTest(unittest.TestCase):
    def test_usa_api_sincrona_do_psycopg(self):
        connection = FakeConnection()

        with patch.object(whatsapp, "get_db_connection", return_value=connection):
            result = asyncio.run(
                whatsapp.salvar_instancia_banco("tenant-123", "barbearia")
            )

        self.assertEqual(
            result,
            {
                "id": 7,
                "tenant_id": "tenant-123",
                "instance_name": "barbearia",
                "status": "connecting",
            },
        )
        self.assertIn("VALUES (%s, %s, 'connecting')", connection.cursor_instance.executed_query)
        self.assertEqual(
            connection.cursor_instance.executed_params,
            ("tenant-123", "barbearia"),
        )


if __name__ == "__main__":
    unittest.main()
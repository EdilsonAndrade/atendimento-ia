import unittest
from datetime import datetime, timezone

from util.time_helpers import get_tabela_dias


class CalendarReferenceTimezoneTest(unittest.TestCase):
    def test_amanha_respects_brazil_timezone_near_midnight_utc(self):
        reference_now = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)

        tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(
            2,
            reference_now=reference_now,
        )

        self.assertEqual(data_hoje_iso, "2026-08-12")
        self.assertEqual(hora_atual_str, "23:30")
        self.assertIn("Hoje (quarta-feira): 12/08/2026 (ISO: '2026-08-12')", tabela_dias[0])
        self.assertIn("Amanhã (quinta-feira): 13/08/2026 (ISO: '2026-08-13')", tabela_dias[1])


if __name__ == "__main__":
    unittest.main()
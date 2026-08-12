import unittest
from datetime import datetime, timezone

from util.time_helpers import ensure_business_timezone, get_tabela_dias


class EnsureBusinessTimezoneTest(unittest.TestCase):
    def test_naive_iso_gets_business_offset(self):
        result = ensure_business_timezone("2026-08-13T11:00:00")

        self.assertEqual(result, "2026-08-13T11:00:00-03:00")

    def test_iso_with_offset_is_preserved(self):
        result = ensure_business_timezone("2026-08-13T11:00:00-03:00")

        self.assertEqual(result, "2026-08-13T11:00:00-03:00")

    def test_utc_offset_is_kept_and_not_forced_to_local(self):
        result = ensure_business_timezone("2026-08-13T14:00:00+00:00")

        self.assertEqual(result, "2026-08-13T14:00:00+00:00")

    def test_none_and_unparseable_pass_through(self):
        self.assertIsNone(ensure_business_timezone(None))
        self.assertEqual(ensure_business_timezone("not-a-date"), "not-a-date")


class TabelaDiasTimezoneTest(unittest.TestCase):
    def test_amanha_respects_business_timezone_near_midnight_utc(self):
        reference_now = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)

        tabela_dias, hora_atual_str, data_hoje_iso = get_tabela_dias(
            2,
            reference_now=reference_now,
        )

        self.assertEqual(data_hoje_iso, "2026-08-12")
        self.assertEqual(hora_atual_str, "23:30")
        self.assertIn("2026-08-12", tabela_dias[0])
        self.assertIn("2026-08-13", tabela_dias[1])


if __name__ == "__main__":
    unittest.main()

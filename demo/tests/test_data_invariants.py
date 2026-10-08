import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DataInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = sqlite3.connect(ROOT / "outputs/gamepulse.db")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_player_ids_are_unique(self):
        total, distinct = self.connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT player_id) FROM players"
        ).fetchone()
        self.assertEqual(total, distinct)

    def test_sessions_reference_players(self):
        orphans = self.connection.execute(
            "SELECT COUNT(*) FROM sessions s LEFT JOIN players p USING(player_id) WHERE p.player_id IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_crash_values_are_binary(self):
        invalid = self.connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE crashed NOT IN (0, 1)"
        ).fetchone()[0]
        self.assertEqual(invalid, 0)


if __name__ == "__main__":
    unittest.main()

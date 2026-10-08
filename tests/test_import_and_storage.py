import tempfile
import unittest
from pathlib import Path

import pandas as pd

from gamepulse.collectors.community_export import collect_community_export
from gamepulse.storage import upsert_csv


ROOT = Path(__file__).resolve().parents[1]


class ImportAndStorageTests(unittest.TestCase):
    def test_authorized_export_is_normalized(self):
        rows = collect_community_export("Example Game", ROOT / "tests/fixtures/community_export.csv", "xiaohongshu")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "xiaohongshu")
        self.assertEqual(rows[1]["language"], None)

    def test_incremental_upsert_deduplicates(self):
        rows = collect_community_export("Example Game", ROOT / "tests/fixtures/community_export.csv", "douyin")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.csv"
            upsert_csv(rows, path)
            incoming, duplicates = upsert_csv(rows, path)
            self.assertEqual(incoming, 2)
            self.assertEqual(duplicates, 2)
            self.assertEqual(len(pd.read_csv(path)), 2)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from gamepulse.compatibility import normalized_voice_row_to_evidence
from gamepulse.models import SCHEMA_MODELS


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityContractTests(unittest.TestCase):
    def test_current_voice_sample_converts_without_losing_native_fields(self):
        frame = pd.read_csv(ROOT / "data/processed/voice.csv")
        self.assertEqual(len(frame), 327)
        for source_row in frame.to_dict(orient="records"):
            evidence = normalized_voice_row_to_evidence(source_row)
            self.assertEqual(evidence.source, str(source_row["source"]))
            self.assertEqual(evidence.source_content_id, str(source_row["source_content_id"]))
            self.assertEqual(evidence.original_text, source_row["text"])
            self.assertEqual(evidence.source_url, source_row["url"])
            self.assertEqual(evidence.published_at.isoformat(), source_row["created_at"])
            self.assertEqual(evidence.retrieved_at.isoformat(), source_row["collected_at"])
            if pd.notna(source_row["rating"]):
                self.assertEqual(evidence.rating, float(source_row["rating"]))
            if pd.notna(source_row["recommended"]):
                expected = str(source_row["recommended"]).casefold() == "true"
                self.assertEqual(evidence.recommended, expected)
            if pd.notna(source_row["engagement_score"]):
                self.assertEqual(evidence.engagement, float(source_row["engagement_score"]))
            if pd.notna(source_row["reply_count"]):
                self.assertEqual(evidence.reply_count, int(source_row["reply_count"]))
            if pd.notna(source_row["playtime_hours"]):
                self.assertEqual(evidence.playtime_hours, float(source_row["playtime_hours"]))

    def test_checked_in_json_schemas_match_models(self):
        for filename, model in SCHEMA_MODELS.items():
            with self.subTest(filename=filename):
                checked_in = (ROOT / "schemas" / filename).read_text(encoding="utf-8")
                expected = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                self.assertEqual(checked_in, expected)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_feedback import classify  # noqa: E402


class FeedbackClassificationTests(unittest.TestCase):
    def test_performance_topic(self):
        topic, hits = classify("The game crashes and the frame rate drops during combat")
        self.assertEqual(topic, "Performance")
        self.assertGreaterEqual(hits, 2)

    def test_monetization_topic(self):
        topic, _ = classify("The outfit price and gacha pity are too expensive")
        self.assertEqual(topic, "Monetization")

    def test_unknown_text(self):
        self.assertEqual(classify("lovely morning")[0], "Other")


if __name__ == "__main__":
    unittest.main()

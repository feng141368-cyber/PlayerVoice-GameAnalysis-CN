import unittest

from gamepulse.analysis import classify_topic, lexical_sentiment


class AnalysisTests(unittest.TestCase):
    def test_chinese_performance_topic(self):
        topic, hits = classify_topic("更新以后一直闪退而且特别卡顿，手机还发热")
        self.assertEqual(topic, "Performance")
        self.assertGreaterEqual(hits, 2)

    def test_english_monetization_topic(self):
        topic, _ = classify_topic("The gacha pity and outfit price are too expensive")
        self.assertEqual(topic, "Monetization")

    def test_bilingual_sentiment(self):
        self.assertLess(lexical_sentiment("太失望了，真的很糟糕"), 0)
        self.assertGreater(lexical_sentiment("beautiful and fun, I love it"), 0)


if __name__ == "__main__":
    unittest.main()

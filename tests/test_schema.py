import unittest

from gamepulse.schema import record, stable_id, validate_record


class SchemaTests(unittest.TestCase):
    def test_ids_are_stable(self):
        self.assertEqual(stable_id("steam", "123"), stable_id("steam", "123"))
        self.assertNotEqual(stable_id("steam", "123"), stable_id("reddit", "123"))

    def test_record_validates(self):
        item = record(
            source="steam", source_type="store_review", game="Game", channel="1",
            content_type="review", source_content_id="123", created_at="2026-01-01T00:00:00+00:00",
            text="review", title=None, url=None, language="en", recommended=True, rating=None,
            engagement_score=0, reply_count=0, playtime_hours=1, parent_id=None, metadata_json={},
        )
        validate_record(item)


if __name__ == "__main__":
    unittest.main()

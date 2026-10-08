import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "skill/game-product-intelligence/scripts/validate_output.py"
spec = importlib.util.spec_from_file_location("validator", VALIDATOR)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ReportValidationTests(unittest.TestCase):
    def test_generated_report_is_valid(self):
        report = json.loads((ROOT / "outputs/product_intelligence.json").read_text())
        self.assertEqual(validator.validate(report), [])

    def test_causal_overclaim_is_rejected(self):
        report = json.loads((ROOT / "outputs/product_intelligence.json").read_text())
        report["recommendations"][0]["interpretation"] = "This proves that crashes caused the retention decline."
        errors = validator.validate(report)
        self.assertTrue(any("unsupported causal phrase" in error for error in errors))

    def test_missing_evidence_is_rejected(self):
        report = json.loads((ROOT / "outputs/product_intelligence.json").read_text())
        report["recommendations"][0]["evidence"] = []
        errors = validator.validate(report)
        self.assertTrue(any("no observed evidence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

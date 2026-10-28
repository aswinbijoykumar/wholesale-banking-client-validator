"""Unit tests for Cost and Performance Estimation Service."""
import unittest
from pathlib import Path

from backend.models import (
    CheckResult,
    DocType,
    Priority,
    RawDocExtraction,
    Verdict,
)
from backend.services.cost_estimator import (
    ESTIMATIONS_DIR,
    calculate_cost_usd,
    record_run_estimation,
)


class TestCostEstimator(unittest.TestCase):
    def test_calculate_cost(self):
        # 1M prompt ($2.50) + 1M completion ($10.00) = $12.50
        cost = calculate_cost_usd(1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 12.50, places=4)

        # 10,000 prompt = $0.025, 1,000 completion = $0.010 -> total $0.035
        cost2 = calculate_cost_usd(10_000, 1_000)
        self.assertAlmostEqual(cost2, 0.035, places=4)

    def test_record_run_estimation(self):
        ext1 = RawDocExtraction(
            doc_type=DocType.BIZFILE,
            filename="ACRA_Bizfile.pdf",
            prompt_tokens=4200,
            completion_tokens=450,
            total_tokens=4650,
            extraction_time_seconds=2.15,
        )
        ext2 = RawDocExtraction(
            doc_type=DocType.TRANSACTION_LISTING,
            filename="transactions.csv",
            is_transaction_listing=True,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            extraction_time_seconds=0.04,
        )

        cr = CheckResult(
            check_id="CHK_01_FRESHNESS",
            rule_name="ACRA BizFile Freshness (12-Month Lookback)",
            verdict=Verdict.PASS,
            priority=Priority.HIGH,
            evidence="Valid within 12 months",
        )

        p = record_run_estimation(
            run_id="test_run_12345678",
            bundle_id="b_123",
            bundle_name="DBS Bank LTD",
            entity_type="Public Listed Company",
            overall_verdict="PASS",
            summary_text="Validation Completed: PASS. 1/1 checks passed.",
            elapsed_seconds=4.56,
            total_prompt_tokens=4200,
            total_completion_tokens=450,
            total_tokens=4650,
            estimated_cost_usd=calculate_cost_usd(4200, 450),
            extractions=[ext1, ext2],
            check_results=[cr],
        )

        self.assertTrue(p.exists())
        content = p.read_text(encoding="utf-8")
        self.assertIn("DBS Bank LTD", content)
        self.assertIn("4,650", content)
        self.assertIn("4.56 seconds", content)
        self.assertIn("ACRA_Bizfile.pdf", content)
        self.assertIn("transactions.csv", content)
        self.assertIn("Zero-Token", content)
        print("[OK] Cost and Performance Estimation filing verified.")


if __name__ == "__main__":
    unittest.main()

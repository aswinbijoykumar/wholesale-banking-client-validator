"""Unit tests for Granular Sub-Checks Matrix, Executive Summary, and PDF Audit Report.
"""
import unittest
from backend.models import CheckResult, Verdict, Priority, SubCheckStatus, ValidationFinding, ItemizedDocStatus
from backend.validators.subcheck_matrix import build_subchecks_for_result, build_executive_summary, SUBCHECK_DEFINITIONS
from backend.reports import render_wholesale_pdf


class TestSubchecksAndUI(unittest.TestCase):
    def test_all_14_checks_have_specs(self):
        check_ids = [
            "CHK_01_BIZFILE", "CHK_02_INCORP", "CHK_03_CONST", "CHK_04_CORP_STRUCT",
            "CHK_05_ID_EXPIRY", "CHK_06_UBO_COMPLEX", "CHK_07_SANCTIONS", "CHK_08_INSTITUTIONAL",
            "CHK_09_CDD_EDD", "CHK_10_INGESTION_QUALITY", "CHK_11_MAS_REGISTER", "CHK_12_RISK_CALCULATOR",
            "CHK_13_DIGITAL_FOOTPRINT", "CHK_14_TRANSACTION_REVIEW"
        ]
        total_subchecks = 0
        for cid in check_ids:
            specs = SUBCHECK_DEFINITIONS.get(cid)
            self.assertIsNotNone(specs, f"Check {cid} missing from subcheck specs")
            self.assertGreater(len(specs), 0, f"Check {cid} has 0 sub-checks")
            total_subchecks += len(specs)
        self.assertGreaterEqual(total_subchecks, 55, f"Expected at least 55 sub-checks from check.md, got {total_subchecks}")

    def test_build_subchecks_for_pass_and_fail(self):
        # Test passing check
        eval_docs = [ItemizedDocStatus(doc_name="bizfile.pdf", doc_type="bizfile", verdict=Verdict.PASS, details="Active")]
        sub_pass = build_subchecks_for_result("CHK_01_BIZFILE", Verdict.PASS, [], eval_docs)
        self.assertEqual(len(sub_pass), 4)
        for sc in sub_pass:
            self.assertEqual(sc.verdict, Verdict.PASS)

        # Test failing check with findings
        finding = ValidationFinding(
            check_id="CHK_05_ID_EXPIRY",
            finding_type="EXPIRED_DOCUMENT",
            target_field="expiry_date",
            reason="ID_EXPIRED",
            details="Passport expired on 2024-01-10",
            severity=Priority.HIGH
        )
        fail_docs = [ItemizedDocStatus(doc_name="passport.jpg", doc_type="id_document", verdict=Verdict.FAIL, details="Expired")]
        sub_fail = build_subchecks_for_result("CHK_05_ID_EXPIRY", Verdict.FAIL, [finding], fail_docs)
        self.assertEqual(len(sub_fail), 6)
        failed_subs = [s for s in sub_fail if s.verdict == Verdict.FAIL]
        self.assertGreater(len(failed_subs), 0)

    def test_executive_summary_generation(self):
        findings = [
            ValidationFinding(
                check_id="CHK_05_ID_EXPIRY",
                finding_type="EXPIRED_DOCUMENT",
                target_field="expiry_date",
                reason="ID_EXPIRED",
                details="Passport expired",
                severity=Priority.HIGH
            )
        ]
        exec_sum = build_executive_summary(
            bundle_name="Global Trading Pte Ltd",
            uen="202012345K",
            entity_type="Private Limited Company",
            overall_verdict="FAIL",
            passed_count=13,
            total_count=14,
            findings=findings,
            elapsed_seconds=1.45,
            total_tokens=2500,
            cost_usd=0.0125
        )
        self.assertEqual(exec_sum["entity_name"], "Global Trading Pte Ltd")
        self.assertEqual(exec_sum["uen"], "202012345K")
        self.assertEqual(exec_sum["verdict"], "FAIL")
        self.assertIn("High", exec_sum["risk_tier"])
        self.assertIn("recommendation", exec_sum)
        self.assertIn("key_risk_indicators", exec_sum)
        self.assertEqual(len(exec_sum["key_risk_indicators"]), 5)

    def test_pdf_report_with_executive_summary_and_subchecks(self):
        bundle_payload = {
            "id": "test_bundle_123",
            "name": "ACME Holding Pte Ltd",
            "uen": "201901234A",
            "entity_type": "Private Limited Company",
            "last_run": {
                "overall_verdict": "FAIL",
                "summary": "1 check failed (ID Expiry)",
                "executive_summary": {
                    "compliance_percentage": 92.8,
                    "passed_count": 13,
                    "total_count": 14,
                    "risk_tier": "HIGH",
                    "narrative": "ACME Holding Pte Ltd cleared 13 of 14 wholesale banking checks with 1 non-compliance item identified.",
                    "recommendation": "Require updated non-expired identification document before account opening.",
                },
                "results": [
                    {
                        "check_id": "CHK_01_BIZFILE",
                        "rule_name": "ACRA BizFile",
                        "verdict": "PASS",
                        "evidence": "ACRA Bizfile is up-to-date.",
                        "priority": "HIGH",
                        "evaluated_files": [{"doc_name": "bizfile.pdf", "doc_type": "bizfile", "verdict": "PASS", "details": "Active"}],
                        "sub_checks": [
                            {"sub_id": "CHK_01.1", "name": "Document Recency", "verdict": "PASS", "details": "Issued 2026-01-10"},
                            {"sub_id": "CHK_01.2", "name": "ACRA Registration Status", "verdict": "PASS", "details": "Live Company"}
                        ]
                    },
                    {
                        "check_id": "CHK_05_ID_EXPIRY",
                        "rule_name": "Director & UBO Identification Documents Expiry & Validity",
                        "verdict": "FAIL",
                        "evidence": "Passport for Director John Doe expired.",
                        "priority": "HIGH",
                        "reason_code": "ID_EXPIRED",
                        "evaluated_files": [{"doc_name": "director_passport.jpg", "doc_type": "id_document", "verdict": "FAIL", "details": "Expired"}],
                        "sub_checks": [
                            {"sub_id": "CHK_05.1", "name": "ID Validity Check", "verdict": "FAIL", "details": "Passport expired on 2024-05-12"}
                        ]
                    }
                ],
                "findings": [
                    {"rule_id": "CHK_05_ID_EXPIRY", "target_field": "expiry_date", "reason": "Passport expired"}
                ]
            }
        }
        pdf_bytes = render_wholesale_pdf(bundle_payload)
        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

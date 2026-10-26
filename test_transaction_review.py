import unittest
from datetime import date
from backend.models import (
    DocType,
    RawDocExtraction,
    RmReviewMonthlyItem,
    TransactionRecord,
    Verdict,
)
from backend.validators.context import BundleContext
from backend.validators.rules.transaction_review import TransactionReviewValidator


class TestTransactionReviewValidator(unittest.TestCase):
    def test_missing_transaction_listing(self):
        ctx = BundleContext(
            bundle_name="SAMPLE ENTITY PTE. LTD.",
            bundle_entity_type="PVT_LTD",
            extractions=[],
            today=date(2026, 10, 23),
        )
        results, findings = TransactionReviewValidator.validate(ctx)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].verdict, Verdict.FAIL)
        self.assertEqual(results[0].reason_code, "MISSING_TRANSACTION_LISTING")

    def test_complete_6month_transactions_and_rm_reconciliation(self):
        # 6 months of data: May 2026 to Oct 2026 (>= 170 days lookback)
        dates = [
            date(2026, 5, 2),
            date(2026, 6, 5),
            date(2026, 7, 10),
            date(2026, 8, 15),
            date(2026, 9, 20),
            date(2026, 10, 22),
        ]
        records = []
        for idx, d in enumerate(dates):
            records.append(
                TransactionRecord(
                    customer_key="CUST-00123",
                    account_holder_name="SAMPLE ENTITY PTE. LTD.",
                    account_key="GLDB-SGD-88001",
                    transaction_key=f"TXN-{idx+1000}",
                    transact_date=d,
                    value_date=d,
                    transaction_type="FAST",
                    transact_currency="SGD",
                    credit_transact_amount=100000.0,
                    debit_transact_amount=40000.0,
                    home_currency="SGD",
                    credit_home_amount=100000.0,
                    debit_home_amount=40000.0,
                    counterparty_account_no="SG987654321",
                    counterparty_name="GLOBAL SUPPLIER PTE LTD",
                    segment="Wholesale Banking",
                )
            )

        # RM Review Table with matching totals
        rm_items = [
            RmReviewMonthlyItem(month_year="2026-05", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
            RmReviewMonthlyItem(month_year="2026-06", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
            RmReviewMonthlyItem(month_year="2026-07", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
            RmReviewMonthlyItem(month_year="2026-08", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
            RmReviewMonthlyItem(month_year="2026-09", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
            RmReviewMonthlyItem(month_year="2026-10", account_key="GLDB-SGD-88001", reported_inflow_amount=100000.0),
        ]

        trans_doc = RawDocExtraction(
            doc_type=DocType.TRANSACTION_LISTING,
            filename="GLDB Past 6-Month Transaction Listing.csv",
            is_transaction_listing=True,
            transaction_records=records,
            rm_review_records=rm_items,
        )

        cdd_doc = RawDocExtraction(
            doc_type=DocType.CDD_EDD_QUESTIONNAIRE,
            filename="GLDB CDD-EDD Questionnaire.pdf",
            expected_monthly_turnover=95000.0,  # ~5% variance, well within 50%
        )

        ctx = BundleContext(
            bundle_name="SAMPLE ENTITY PTE. LTD.",
            bundle_entity_type="PVT_LTD",
            extractions=[trans_doc, cdd_doc],
            today=date(2026, 10, 23),
        )

        results, findings = TransactionReviewValidator.validate(ctx)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].verdict, Verdict.PASS)
        self.assertEqual(len(findings), 0)
        self.assertTrue(ctx.profile.transaction_listing.has_full_6m_lookback)
        self.assertTrue(ctx.profile.transaction_listing.rm_reconciliation_pass)

    def test_dormancy_and_rm_mismatch_flags(self):
        # Only 2 dates -> lookback < 170 days, dormancy, and RM mismatch
        records = [
            TransactionRecord(
                customer_key="CUST-00999",
                account_key="GLDB-SGD-99999",
                transact_date=date(2026, 9, 1),
                value_date=date(2026, 9, 1),
                credit_home_amount=50000.0,
            ),
            TransactionRecord(
                customer_key="CUST-00999",
                account_key="GLDB-SGD-99999",
                transact_date=date(2026, 10, 1),
                value_date=date(2026, 10, 1),
                credit_home_amount=50000.0,
            ),
        ]

        rm_mismatch = [
            RmReviewMonthlyItem(month_year="2026-09", account_key="GLDB-SGD-99999", reported_inflow_amount=999999.0)  # Mismatch!
        ]

        trans_doc = RawDocExtraction(
            doc_type=DocType.TRANSACTION_LISTING,
            filename="Short_Listing.csv",
            is_transaction_listing=True,
            transaction_records=records,
            rm_review_records=rm_mismatch,
        )

        ctx = BundleContext(
            bundle_name="SAMPLE ENTITY PTE. LTD.",
            bundle_entity_type="PVT_LTD",
            extractions=[trans_doc],
            today=date(2026, 10, 23),
        )

        results, findings = TransactionReviewValidator.validate(ctx)
        self.assertEqual(results[0].verdict, Verdict.FAIL)
        finding_types = [f.finding_type for f in findings]
        self.assertIn("INCOMPLETE_LOOKBACK_WINDOW", finding_types)
        self.assertIn("RM_TEMPLATE_RECONCILIATION_ERROR", finding_types)


if __name__ == "__main__":
    unittest.main()

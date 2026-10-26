"""Unit and integration test for Tabular (Excel / CSV) Ingestion and Check 14 Validator."""
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from backend.models import (
    DocType,
    RawDocExtraction,
    TransactionRecord,
    Verdict,
    Priority,
)
from backend.services.tabular_parser import parse_tabular_file
from backend.validators.context import BundleContext
from backend.validators.rules.transaction_review import TransactionReviewValidator


class TestTabularIngestion(unittest.TestCase):
    def setUp(self):
        self.tmp_csv = Path("temp_test_tx_listing.csv")
        self.tmp_xlsx = Path("temp_test_tx_listing.xlsx")

        # Generate 6 months of sample transactions across 21 columns
        start_date = date(2025, 10, 1)
        rows = []
        for i in range(185):
            curr_date = start_date + timedelta(days=i)
            # Create alternating wire in/out
            is_inflow = (i % 2 == 0)
            rows.append({
                "Customer Key": "CUST_SG_8839",
                "Account Holder Name": "Apex Global Trading Pte. Ltd.",
                "Account Key": "771-882-9901",
                "Transaction Key": f"TX_{i+1:05d}",
                "Transact Date": curr_date.isoformat(),
                "Transact Date Time": f"{curr_date.isoformat()} 11:22:33",
                "Transaction Type": "WIRE_IN" if is_inflow else "WIRE_OUT",
                "Transact Currency": "SGD",
                "Credit Transact Amount": 12500.0 if is_inflow else 0.0,
                "Debit Transact Amount": 0.0 if is_inflow else 8500.0,
                "Home Currency": "SGD",
                "Credit Home Amount": 12500.0 if is_inflow else 0.0,
                "Debit Home Amount": 0.0 if is_inflow else 8500.0,
                "Counterparty Account No": f"CPTY_{9000+i}",
                "Counterparty Name": f"Supplier Partner {i % 5 + 1} Pte Ltd",
                "Description": "Commercial settlement for bulk electronics shipment",
                "Value Date": curr_date.isoformat(),
                "Segment": "Wholesale Banking",
                "Counterparty Bank1": "DBS Bank",
                "Counterparty Bank2": "Standard Chartered SG",
                "Payment Detail": f"INVOICE-SG-{2025000+i}",
            })

        self.df = pd.DataFrame(rows)
        self.df.to_csv(self.tmp_csv, index=False)
        self.df.to_excel(self.tmp_xlsx, index=False)

    def tearDown(self):
        for p in [self.tmp_csv, self.tmp_xlsx]:
            if p.exists():
                p.unlink()

    def test_csv_ingestion_and_validation(self):
        extraction = parse_tabular_file(self.tmp_csv, "Apex_6M_Transactions.csv")
        self.assertEqual(extraction.doc_type, DocType.TRANSACTION_LISTING)
        self.assertTrue(extraction.is_transaction_listing)
        self.assertEqual(len(extraction.transaction_records), 185)

        # Inspect first record for all 21 columns mapping
        rec0 = extraction.transaction_records[0]
        self.assertEqual(rec0.customer_key, "CUST_SG_8839")
        self.assertEqual(rec0.account_holder_name, "Apex Global Trading Pte. Ltd.")
        self.assertEqual(rec0.account_key, "771-882-9901")
        self.assertEqual(rec0.transaction_key, "TX_00001")
        self.assertEqual(rec0.transact_date, date(2025, 10, 1))
        self.assertEqual(rec0.transact_datetime, "2025-10-01 11:22:33")
        self.assertEqual(rec0.transaction_type, "WIRE_IN")
        self.assertEqual(rec0.transact_currency, "SGD")
        self.assertEqual(rec0.credit_transact_amount, 12500.0)
        self.assertEqual(rec0.debit_transact_amount, 0.0)
        self.assertEqual(rec0.home_currency, "SGD")
        self.assertEqual(rec0.credit_home_amount, 12500.0)
        self.assertEqual(rec0.debit_home_amount, 0.0)
        self.assertEqual(rec0.counterparty_account_no, "CPTY_9000")
        self.assertEqual(rec0.counterparty_name, "Supplier Partner 1 Pte Ltd")
        self.assertEqual(rec0.description, "Commercial settlement for bulk electronics shipment")
        self.assertEqual(rec0.value_date, date(2025, 10, 1))
        self.assertEqual(rec0.segment, "Wholesale Banking")
        self.assertEqual(rec0.counterparty_bank1, "DBS Bank")
        self.assertEqual(rec0.counterparty_bank2, "Standard Chartered SG")
        self.assertEqual(rec0.payment_detail, "INVOICE-SG-2025000")

        # Run Validator
        ctx = BundleContext(
            bundle_name="Apex Global Trading Pte. Ltd.",
            bundle_entity_type="Private Limited Company",
            extractions=[extraction],
            today=date(2026, 4, 15),
        )
        results, findings = TransactionReviewValidator.validate(ctx)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].check_id, "CHK_14_TRANSACTION_REVIEW")
        self.assertEqual(results[0].verdict, Verdict.PASS)
        print("[OK] CSV Ingestion & Check 14 Validator PASSED")

    def test_excel_ingestion_and_validation(self):
        extraction = parse_tabular_file(self.tmp_xlsx, "Apex_6M_Transactions.xlsx")
        self.assertEqual(extraction.doc_type, DocType.TRANSACTION_LISTING)
        self.assertTrue(extraction.is_transaction_listing)
        self.assertEqual(len(extraction.transaction_records), 185)

        ctx = BundleContext(
            bundle_name="Apex Global Trading Pte. Ltd.",
            bundle_entity_type="Private Limited Company",
            extractions=[extraction],
            today=date(2026, 4, 15),
        )
        results, findings = TransactionReviewValidator.validate(ctx)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].check_id, "CHK_14_TRANSACTION_REVIEW")
        self.assertEqual(results[0].verdict, Verdict.PASS)
        print("[OK] Excel Ingestion & Check 14 Validator PASSED")


if __name__ == "__main__":
    unittest.main()

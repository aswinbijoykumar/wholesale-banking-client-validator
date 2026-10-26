"""Tabular File Parser for Wholesale Banking Transactions and Spreadsheets.

Parses .csv, .xlsx, and .xls files directly into structured RawDocExtraction objects,
extracting all 21 mandated transaction fields deterministically without LLM vision overhead.
"""
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import csv
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

from ..models import (
    DocType,
    RawDocExtraction,
    TransactionRecord,
    RmReviewMonthlyItem,
)


COLUMN_MAPPINGS: Dict[str, str] = {
    # 1. Customer Key
    "customerkey": "customer_key",
    "customerid": "customer_key",
    "clientkey": "customer_key",
    "custkey": "customer_key",
    # 2. Account Holder Name
    "accountholdername": "account_holder_name",
    "accountholder": "account_holder_name",
    "holdername": "account_holder_name",
    "accountname": "account_holder_name",
    "clientname": "account_holder_name",
    # 3. Account Key
    "accountkey": "account_key",
    "accountno": "account_key",
    "accountnumber": "account_key",
    "acctno": "account_key",
    "acctkey": "account_key",
    # 4. Transaction Key
    "transactionkey": "transaction_key",
    "transkey": "transaction_key",
    "txkey": "transaction_key",
    "txnid": "transaction_key",
    "transactionid": "transaction_key",
    "referenceno": "transaction_key",
    "refno": "transaction_key",
    # 5. Transact Date
    "transactdate": "transact_date",
    "transactiondate": "transact_date",
    "txdate": "transact_date",
    "date": "transact_date",
    "bookingdate": "transact_date",
    # 6. Transact Date Time
    "transactdatetime": "transact_datetime",
    "transactiondatetime": "transact_datetime",
    "txdatetime": "transact_datetime",
    "datetime": "transact_datetime",
    "timestamp": "transact_datetime",
    # 7. Transaction Type
    "transactiontype": "transaction_type",
    "txtype": "transaction_type",
    "type": "transaction_type",
    "channel": "transaction_type",
    # 8. Transact Currency
    "transactcurrency": "transact_currency",
    "txcurrency": "transact_currency",
    "currency": "transact_currency",
    "ccy": "transact_currency",
    # 9. Credit Transact Amount
    "credittransactamount": "credit_transact_amount",
    "creditamount": "credit_transact_amount",
    "credit": "credit_transact_amount",
    "inflow": "credit_transact_amount",
    "inflowamount": "credit_transact_amount",
    "creditamt": "credit_transact_amount",
    # 10. Debit Transact Amount
    "debittransactamount": "debit_transact_amount",
    "debitamount": "debit_transact_amount",
    "debit": "debit_transact_amount",
    "outflow": "debit_transact_amount",
    "outflowamount": "debit_transact_amount",
    "debitamt": "debit_transact_amount",
    # 11. Home Currency
    "homecurrency": "home_currency",
    "basecurrency": "home_currency",
    "localcurrency": "home_currency",
    "homeccy": "home_currency",
    # 12. Credit Home Amount
    "credithomeamount": "credit_home_amount",
    "creditbaseamount": "credit_home_amount",
    "homecreditamount": "credit_home_amount",
    # 13. Debit Home Amount
    "debithomeamount": "debit_home_amount",
    "debitbaseamount": "debit_home_amount",
    "homedebitamount": "debit_home_amount",
    # 14. Counterparty Account No
    "counterpartyaccountno": "counterparty_account_no",
    "counterpartyaccount": "counterparty_account_no",
    "counterpartyacno": "counterparty_account_no",
    "cptyaccountno": "counterparty_account_no",
    "cptyaccount": "counterparty_account_no",
    "cptyacctno": "counterparty_account_no",
    "beneficiaryaccount": "counterparty_account_no",
    # 15. Counterparty Name
    "counterpartyname": "counterparty_name",
    "counterparty": "counterparty_name",
    "cptyname": "counterparty_name",
    "beneficiary": "counterparty_name",
    "beneficiaryname": "counterparty_name",
    # 16. Description
    "description": "description",
    "narrative": "description",
    "narration": "description",
    "particulars": "description",
    "desc": "description",
    "details": "description",
    # 17. Value Date
    "valuedate": "value_date",
    "valdate": "value_date",
    # 18. Segment
    "segment": "segment",
    "customersegment": "segment",
    "businesssegment": "segment",
    # 19. Counterparty Bank1
    "counterpartybank1": "counterparty_bank1",
    "cptybank1": "counterparty_bank1",
    "bank1": "counterparty_bank1",
    "receivingbank": "counterparty_bank1",
    # 20. Counterparty Bank2
    "counterpartybank2": "counterparty_bank2",
    "cptybank2": "counterparty_bank2",
    "bank2": "counterparty_bank2",
    "intermediarybank": "counterparty_bank2",
    # 21. Payment Detail
    "paymentdetail": "payment_detail",
    "paymentdetails": "payment_detail",
    "remittancedetail": "payment_detail",
    "remittanceinfo": "payment_detail",
    "remittancedetails": "payment_detail",
    "paymentreference": "payment_detail",
}


def _normalize_header(name: Any) -> str:
    """Normalize column header to alphanumeric lowercase."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _is_na(val: Any) -> bool:
    if val is None:
        return True
    if HAS_PANDAS and pd is not None:
        try:
            return bool(pd.isna(val))
        except Exception:
            pass
    s = str(val).strip().lower()
    return s in ("", "nan", "none", "null", "nat")


def _to_date_safe(val: Any) -> Optional[date]:
    """Parse dates safely from strings, Timestamps, or date/datetime objects."""
    if _is_na(val):
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if hasattr(val, "date"):
        try:
            return val.date()
        except Exception:
            pass

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "nat"):
        return None

    # Handle string with time component
    if " " in s:
        s = s.split(" ")[0]
    if "T" in s:
        s = s.split("T")[0]

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    if HAS_PANDAS and pd is not None:
        try:
            ts = pd.to_datetime(s)
            return ts.date()
        except Exception:
            pass
    return None


def _to_float_safe(val: Any) -> float:
    """Convert value to float safely, stripping currency symbols and commas."""
    if _is_na(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    for symbol in ["$", ",", "SGD", "USD", "EUR", "GBP", " "]:
        s = s.replace(symbol, "")
    try:
        return float(s)
    except Exception:
        return 0.0


def _to_str_safe(val: Any) -> Optional[str]:
    """Convert value to string, stripping NaN / None."""
    if _is_na(val):
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "null") else None


def parse_tabular_file(
    file_path: Path,
    original_name: str,
    today: date | None = None,
) -> RawDocExtraction:
    """Ingest CSV, XLSX, or XLS spreadsheet and extract transaction records across the 21 schema fields."""
    ext = file_path.suffix.lower()

    # Load dataframe(s)
    dfs: Dict[str, pd.DataFrame] = {}
    if ext == ".csv":
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="latin-1", dtype=str)
        dfs["default"] = df
    elif ext in {".xlsx", ".xls"}:
        with pd.ExcelFile(file_path) as excel_file:
            for sname in excel_file.sheet_names:
                dfs[sname] = pd.read_excel(excel_file, sheet_name=sname, dtype=str)
    else:
        raise ValueError(f"Unsupported tabular file extension: {ext}")

    # Determine main transactions sheet
    tx_sheet_name = "default"
    for sname in dfs.keys():
        s_lower = sname.lower()
        if any(k in s_lower for k in ["trans", "tx", "listing", "statement", "ledger"]):
            tx_sheet_name = sname
            break
    if tx_sheet_name not in dfs and dfs:
        tx_sheet_name = list(dfs.keys())[0]

    df_tx = dfs.get(tx_sheet_name, pd.DataFrame())

    # Map column headers to 21 fields
    col_mapping: Dict[str, str] = {}
    for col in df_tx.columns:
        norm = _normalize_header(col)
        if norm in COLUMN_MAPPINGS:
            col_mapping[COLUMN_MAPPINGS[norm]] = col

    records: List[TransactionRecord] = []
    for _, row in df_tx.iterrows():
        t_date = _to_date_safe(row.get(col_mapping.get("transact_date"))) if "transact_date" in col_mapping else None
        v_date = _to_date_safe(row.get(col_mapping.get("value_date"))) if "value_date" in col_mapping else t_date
        if v_date is None:
            v_date = t_date
        if t_date is None:
            t_date = v_date

        tx_curr = _to_str_safe(row.get(col_mapping.get("transact_currency"))) or "SGD"
        home_curr = _to_str_safe(row.get(col_mapping.get("home_currency"))) or tx_curr

        cr_tx_amt = _to_float_safe(row.get(col_mapping.get("credit_transact_amount"))) if "credit_transact_amount" in col_mapping else 0.0
        dr_tx_amt = _to_float_safe(row.get(col_mapping.get("debit_transact_amount"))) if "debit_transact_amount" in col_mapping else 0.0

        cr_home_amt = _to_float_safe(row.get(col_mapping.get("credit_home_amount"))) if "credit_home_amount" in col_mapping else 0.0
        dr_home_amt = _to_float_safe(row.get(col_mapping.get("debit_home_amount"))) if "debit_home_amount" in col_mapping else 0.0

        # Auto-mirror home amount if home_curr == tx_curr and home amount is zero
        if cr_home_amt == 0.0 and cr_tx_amt > 0.0 and home_curr == tx_curr:
            cr_home_amt = cr_tx_amt
        if dr_home_amt == 0.0 and dr_tx_amt > 0.0 and home_curr == tx_curr:
            dr_home_amt = dr_tx_amt

        rec = TransactionRecord(
            customer_key=_to_str_safe(row.get(col_mapping.get("customer_key"))),
            account_holder_name=_to_str_safe(row.get(col_mapping.get("account_holder_name"))),
            account_key=_to_str_safe(row.get(col_mapping.get("account_key"))),
            transaction_key=_to_str_safe(row.get(col_mapping.get("transaction_key"))),
            transact_date=t_date,
            transact_datetime=_to_str_safe(row.get(col_mapping.get("transact_datetime"))),
            transaction_type=_to_str_safe(row.get(col_mapping.get("transaction_type"))),
            transact_currency=tx_curr,
            credit_transact_amount=cr_tx_amt,
            debit_transact_amount=dr_tx_amt,
            home_currency=home_curr,
            credit_home_amount=cr_home_amt,
            debit_home_amount=dr_home_amt,
            counterparty_account_no=_to_str_safe(row.get(col_mapping.get("counterparty_account_no"))),
            counterparty_name=_to_str_safe(row.get(col_mapping.get("counterparty_name"))),
            description=_to_str_safe(row.get(col_mapping.get("description"))),
            value_date=v_date,
            segment=_to_str_safe(row.get(col_mapping.get("segment"))),
            counterparty_bank1=_to_str_safe(row.get(col_mapping.get("counterparty_bank1"))),
            counterparty_bank2=_to_str_safe(row.get(col_mapping.get("counterparty_bank2"))),
            payment_detail=_to_str_safe(row.get(col_mapping.get("payment_detail"))),
        )
        # Skip completely empty rows
        if any([
            rec.transact_date,
            rec.value_date,
            rec.credit_transact_amount > 0,
            rec.debit_transact_amount > 0,
            rec.counterparty_name,
            rec.description,
            rec.transaction_key,
        ]):
            records.append(rec)

    # Optional RM Review secondary sheet extraction
    rm_reviews: List[RmReviewMonthlyItem] = []
    for sname, sdf in dfs.items():
        if sname == tx_sheet_name:
            continue
        s_lower = sname.lower()
        if any(k in s_lower for k in ["rm_review", "rm review", "monthly review", "reconciliation"]):
            # Normalize headers
            rm_cols = {_normalize_header(c): c for c in sdf.columns}
            my_col = rm_cols.get("monthyear") or rm_cols.get("month") or rm_cols.get("period")
            in_col = rm_cols.get("reportedinflowamount") or rm_cols.get("inflow") or rm_cols.get("inflows")
            out_col = rm_cols.get("reportedoutflowamount") or rm_cols.get("outflow") or rm_cols.get("outflows")
            for _, r in sdf.iterrows():
                my = _to_str_safe(r.get(my_col)) if my_col else None
                if my:
                    rm_reviews.append(
                        RmReviewMonthlyItem(
                            month_year=my,
                            currency="SGD",
                            reported_inflow_amount=_to_float_safe(r.get(in_col)) if in_col else 0.0,
                            reported_outflow_amount=_to_float_safe(r.get(out_col)) if out_col else 0.0,
                        )
                    )

    return RawDocExtraction(
        doc_type=DocType.TRANSACTION_LISTING,
        filename=original_name,
        is_transaction_listing=True,
        transaction_records=records,
        rm_review_records=rm_reviews,
        notes=f"Parsed {len(records)} transaction rows from tabular file ({original_name}) across 21 schema fields.",
    )

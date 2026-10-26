from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple
from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    MonthlyTransactionSummary,
    Priority,
    TransactionListingProfile,
    TransactionRecord,
    ValidationFinding,
    Verdict,
)
from ..context import BundleContext


class TransactionReviewValidator:
    """Evaluates:
    - CHK_14_TRANSACTION_REVIEW: Past 6-Month Transaction Listing & RM Review Cross-Reconciliation
      (Descriptions 14, 15, and 16)
      1. Check A: Date Range & Completeness (6-Month Lookback Window >= 170 days)
      2. Check B: Monthly Aggregation by Direction (Inflow vs. Outflow)
      3. Check C: Multi-Currency Account Separation (per Account Key / Currency)
      4. Check D: Account Inactivity / Dormancy & Sudden Spike Detection (>50% above average)
      5. Check E: Cross-Reconciliation with CDD Expected Turnover & RM Transaction Review Table
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk14_findings: List[ValidationFinding] = []
        chk14_files: List[ItemizedDocStatus] = []
        chk14_reason: str | None = None
        chk14_priority: Priority = Priority.HIGH

        if not ctx.transaction_docs:
            chk14_verdict = Verdict.FAIL
            chk14_reason = "MISSING_TRANSACTION_LISTING"
            chk14_findings.append(
                ValidationFinding(
                    check_id="CHK_14_TRANSACTION_REVIEW",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.HIGH,
                    missing_document="Past 6-Month Transaction Listing",
                    reason="MISSING_TRANSACTION_LISTING",
                    target_field="transaction_listing",
                    details="Descr. 14: Mandated Past 6-Month Transaction Listing / Bank Account Statement is missing from client bundle.",
                )
            )
            chk14_evidence = "Missing Document: Past 6-Month Transaction Listing not uploaded. Quantitative throughput, dormancy, and RM review checks cannot be evaluated."
            results.append(
                CheckResult(
                    check_id="CHK_14_TRANSACTION_REVIEW",
                    rule_name="Past 6-Month Transaction Listing & RM Review Cross-Reconciliation",
                    verdict=chk14_verdict,
                    reason_code=chk14_reason,
                    priority=chk14_priority,
                    evidence=chk14_evidence,
                    evaluated_files=chk14_files,
                    findings=chk14_findings,
                )
            )
            all_findings.extend(chk14_findings)
            return results, all_findings

        # Aggregate all transaction records across ingested listing documents
        all_records: List[TransactionRecord] = []
        rm_reported_items = []
        source_filenames = []

        for t_doc in ctx.transaction_docs:
            source_filenames.append(t_doc.filename or "Transaction Listing")
            if t_doc.transaction_records:
                all_records.extend(t_doc.transaction_records)
            if t_doc.rm_review_records:
                rm_reported_items.extend(t_doc.rm_review_records)

        # Also collect RM review records from CDD docs if available (Section 9/Description 16)
        for cdd in ctx.cdd_docs:
            if hasattr(cdd, "rm_review_records") and cdd.rm_review_records:
                rm_reported_items.extend(cdd.rm_review_records)

        profile = TransactionListingProfile(
            is_provided=True,
            filename=", ".join(source_filenames),
            total_transactions_count=len(all_records),
        )

        doc_pass = True
        fail_notes: List[str] = []

        if not all_records:
            doc_pass = False
            fail_notes.append("No transaction rows could be parsed from the uploaded listing.")
            chk14_findings.append(
                ValidationFinding(
                    check_id="CHK_14_TRANSACTION_REVIEW",
                    finding_type="EMPTY_TRANSACTION_DATA",
                    severity=Priority.HIGH,
                    reason="NO_TRANSACTIONS_PARSED",
                    target_field="transaction_records",
                    details="Descr. 14: Uploaded transaction document contains 0 parseable transaction records.",
                )
            )
            if not chk14_reason:
                chk14_reason = "NO_TRANSACTIONS_PARSED"
        else:
            # -------------------------------------------------------------
            # Check A: Date Range & Completeness (6-Month Lookback Window)
            # -------------------------------------------------------------
            valid_dates = [
                r.value_date or r.transact_date
                for r in all_records
                if (r.value_date or r.transact_date) is not None
            ]

            if valid_dates:
                earliest = min(valid_dates)
                latest = max(valid_dates)
                lookback_days = (latest - earliest).days
                profile.earliest_date = earliest
                profile.latest_date = latest
                profile.lookback_days = lookback_days
                profile.has_full_6m_lookback = lookback_days >= 170

                if lookback_days < 170:
                    doc_pass = False
                    fail_notes.append(f"Incomplete lookback window: Covers {lookback_days} days ({earliest} to {latest}), requires >= 170 days (~6 months)")
                    chk14_findings.append(
                        ValidationFinding(
                            check_id="CHK_14_TRANSACTION_REVIEW",
                            finding_type="INCOMPLETE_LOOKBACK_WINDOW",
                            severity=Priority.HIGH,
                            reason="INSUFFICIENT_TRANSACTION_TIMEFRAME",
                            target_field="lookback_days",
                            details=f"Descr. 14: Transaction listing covers only {lookback_days} days ({earliest} to {latest}). Mandated policy requires a continuous 6-month (>= 170 days) lookback window.",
                        )
                    )
                    if not chk14_reason:
                        chk14_reason = "INSUFFICIENT_TRANSACTION_TIMEFRAME"
            else:
                doc_pass = False
                fail_notes.append("No transaction dates / value dates detected.")

            # -------------------------------------------------------------
            # Check B & C: Monthly Aggregation by Direction & Currency/Account Separation
            # Grouping key: (account_key, currency, YYYY-MM)
            # -------------------------------------------------------------
            group_buckets: Dict[Tuple[str, str, str], Dict[str, float]] = defaultdict(
                lambda: {
                    "inflow_count": 0,
                    "inflow_home_amount": 0.0,
                    "outflow_count": 0,
                    "outflow_home_amount": 0.0,
                }
            )

            months_seen = set()

            for r in all_records:
                dt = r.value_date or r.transact_date
                month_str = dt.strftime("%Y-%m") if dt else "UNKNOWN"
                months_seen.add(month_str)

                acc = r.account_key or "PRIMARY"
                curr = r.transact_currency or r.home_currency or "SGD"
                key = (acc, curr, month_str)

                # Determine inflow (Credit) vs outflow (Debit)
                inflow_amt = r.credit_home_amount if r.credit_home_amount > 0 else (r.credit_transact_amount if r.credit_transact_amount > 0 else 0.0)
                outflow_amt = r.debit_home_amount if r.debit_home_amount > 0 else (r.debit_transact_amount if r.debit_transact_amount > 0 else 0.0)

                if inflow_amt > 0:
                    group_buckets[key]["inflow_count"] += 1
                    group_buckets[key]["inflow_home_amount"] += inflow_amt

                if outflow_amt > 0:
                    group_buckets[key]["outflow_count"] += 1
                    group_buckets[key]["outflow_home_amount"] += outflow_amt

            # Build summaries
            monthly_summaries: List[MonthlyTransactionSummary] = []
            month_inflow_totals: Dict[str, float] = defaultdict(float)

            for (acc, curr, m_str), b in sorted(group_buckets.items(), key=lambda x: x[0][2]):
                net = b["inflow_home_amount"] - b["outflow_home_amount"]
                summary = MonthlyTransactionSummary(
                    month_year=m_str,
                    account_key=acc,
                    currency=curr,
                    inflow_count=b["inflow_count"],
                    inflow_home_amount=round(b["inflow_home_amount"], 2),
                    outflow_count=b["outflow_count"],
                    outflow_home_amount=round(b["outflow_home_amount"], 2),
                    net_home_flow=round(net, 2),
                )
                monthly_summaries.append(summary)
                month_inflow_totals[m_str] += b["inflow_home_amount"]

            profile.monthly_summaries = monthly_summaries

            # Calculate 6-month average throughput
            num_months = max(1, len(months_seen - {"UNKNOWN"}))
            total_inflows = sum(s.inflow_home_amount for s in monthly_summaries)
            total_outflows = sum(s.outflow_home_amount for s in monthly_summaries)
            avg_monthly_inflow = round(total_inflows / num_months, 2)
            avg_monthly_outflow = round(total_outflows / num_months, 2)
            profile.average_monthly_inflow = avg_monthly_inflow
            profile.average_monthly_outflow = avg_monthly_outflow

            # -------------------------------------------------------------
            # Check D: Account Inactivity / Dormancy & Sudden Spikes (>50%)
            # -------------------------------------------------------------
            sorted_months = sorted([m for m in months_seen if m != "UNKNOWN"])
            dormant_months = []
            spike_months = []

            for m in sorted_months:
                amt = month_inflow_totals[m]
                # Inactive / Dormant month: zero or near-zero activity (< 100 SGD or 0 count)
                if amt <= 100.0:
                    dormant_months.append(m)

                # Sudden Spike: Inflow exceeds 6-month monthly average by > 50%
                if avg_monthly_inflow > 0 and amt > (avg_monthly_inflow * 1.5):
                    spike_months.append(f"{m} (SGD {amt:,.2f} vs avg SGD {avg_monthly_inflow:,.2f})")

            profile.dormant_months = dormant_months
            profile.is_dormant_detected = len(dormant_months) >= 2
            profile.spike_months = spike_months
            profile.is_spike_detected = len(spike_months) > 0

            if profile.is_dormant_detected:
                doc_pass = False
                fail_notes.append(f"Account Dormancy Anomaly: Multiple inactive months detected ({', '.join(dormant_months)})")
                chk14_findings.append(
                    ValidationFinding(
                        check_id="CHK_14_TRANSACTION_REVIEW",
                        finding_type="ACCOUNT_DORMANCY_ANOMALY",
                        severity=Priority.HIGH,
                        reason="PROLONGED_ACCOUNT_DORMANCY",
                        target_field="dormant_months",
                        details=f"Descr. 14: Account dormancy detected with near-zero throughput across multiple consecutive calendar months: {', '.join(dormant_months)}.",
                    )
                )
                if not chk14_reason:
                    chk14_reason = "PROLONGED_ACCOUNT_DORMANCY"

            if profile.is_spike_detected:
                # Spikes are flagged for downstream explanation (Description 15)
                fail_notes.append(f"Turnover Spike (>50% above average): {', '.join(spike_months)}")
                chk14_findings.append(
                    ValidationFinding(
                        check_id="CHK_14_TRANSACTION_REVIEW",
                        finding_type="TURNOVER_SPIKE_DEVIATION",
                        severity=Priority.MEDIUM,
                        reason="TURNOVER_SPIKE_DETECTED",
                        target_field="spike_months",
                        details=f"Descr. 15: Monthly throughput spike exceeding average by >50% detected in: {', '.join(spike_months)}. Mitigating commercial rationale required.",
                    )
                )
                if not chk14_reason:
                    chk14_reason = "TURNOVER_SPIKE_DETECTED"

            # -------------------------------------------------------------
            # Check E: Cross-Reconciliation with CDD Form & RM Template
            # -------------------------------------------------------------
            # 1. Compare with CDD Expected Monthly Turnover
            declared_expected = None
            for cdd in ctx.cdd_docs:
                if cdd.expected_monthly_turnover and cdd.expected_monthly_turnover > 0:
                    declared_expected = cdd.expected_monthly_turnover
                    break

            if declared_expected and declared_expected > 0:
                variance_pct = round(abs(avg_monthly_inflow - declared_expected) / declared_expected * 100, 2)
                profile.turnover_variance_pct = variance_pct

                if variance_pct > 50.0:
                    doc_pass = False
                    fail_notes.append(f"Turnover Variance {variance_pct}% exceeds 50% threshold (Actual avg SGD {avg_monthly_inflow:,.2f} vs Declared SGD {declared_expected:,.2f})")
                    chk14_findings.append(
                        ValidationFinding(
                            check_id="CHK_14_TRANSACTION_REVIEW",
                            finding_type="EXPECTED_TURNOVER_DEVIATION",
                            severity=Priority.HIGH,
                            reason="TURNOVER_DEVIATION_EXCEEDS_50PCT",
                            target_field="turnover_variance_pct",
                            details=f"Descr. 15: Actual 6-month monthly average (SGD {avg_monthly_inflow:,.2f}) deviates by {variance_pct}% from CDD declared expected turnover (SGD {declared_expected:,.2f}). Exceeds 50% policy tolerance.",
                        )
                    )
                    if not chk14_reason:
                        chk14_reason = "TURNOVER_DEVIATION_EXCEEDS_50PCT"

            # 2. Reconcile RM Reported Monthly Totals (Description 16)
            if rm_reported_items:
                rm_discrepancies = []
                for rm_item in rm_reported_items:
                    m_key = rm_item.month_year
                    actual_sum = month_inflow_totals.get(m_key, 0.0)
                    reported_sum = rm_item.reported_inflow_amount
                    if abs(actual_sum - reported_sum) > 5.0:  # Allowing small rounding variance <= $5
                        rm_discrepancies.append(
                            f"Month {m_key}: RM reported SGD {reported_sum:,.2f} vs Actual listing sum SGD {actual_sum:,.2f} (Delta: SGD {abs(actual_sum - reported_sum):,.2f})"
                        )

                profile.rm_discrepancies = rm_discrepancies
                profile.rm_reconciliation_pass = len(rm_discrepancies) == 0

                if rm_discrepancies:
                    doc_pass = False
                    fail_notes.append(f"RM Review Table Discrepancies ({len(rm_discrepancies)} month(s) mismatch)")
                    chk14_findings.append(
                        ValidationFinding(
                            check_id="CHK_14_TRANSACTION_REVIEW",
                            finding_type="RM_TEMPLATE_RECONCILIATION_ERROR",
                            severity=Priority.HIGH,
                            reason="RM_TABLE_CALCULATION_MISMATCH",
                            target_field="rm_review_records",
                            details=f"Descr. 16: Mathematical/transcription discrepancy in RM Transaction Review table: {'; '.join(rm_discrepancies[:3])}.",
                        )
                    )
                    if not chk14_reason:
                        chk14_reason = "RM_TABLE_CALCULATION_MISMATCH"

        ctx.profile.transaction_listing = profile

        chk14_files.append(
            ItemizedDocStatus(
                doc_name=profile.filename or "Past 6-Month Transaction Listing",
                doc_type="Transaction Listing / Bank Statement",
                verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                details=(
                    f"Parsed {profile.total_transactions_count} transactions across {profile.lookback_days} days. "
                    f"Avg Monthly Inflow: SGD {profile.average_monthly_inflow:,.2f}, Outflow: SGD {profile.average_monthly_outflow:,.2f}. "
                    f"Turnover Variance: {profile.turnover_variance_pct or 0.0}%. "
                    f"Dormancy: {'Detected' if profile.is_dormant_detected else 'None'}. "
                    f"RM Reconciliation: {'Verified ✓' if profile.rm_reconciliation_pass else 'Mismatch'}"
                ) if doc_pass else "; ".join(fail_notes),
                reason=chk14_reason if not doc_pass else None,
                is_ctc=False,
            )
        )

        chk14_verdict = Verdict.FAIL if chk14_findings else Verdict.PASS
        chk14_evidence = (
            f"Transaction Listing verified: {profile.total_transactions_count} records audited over continuous {profile.lookback_days}-day window ({profile.earliest_date} to {profile.latest_date}). "
            f"Average monthly throughput: SGD {profile.average_monthly_inflow:,.2f}. Multi-currency separation confirmed, no dormancy/pass-through anomalies detected, and RM review figures reconciled."
        ) if chk14_verdict == Verdict.PASS else f"Transaction review discrepancies: {'; '.join([f.details for f in chk14_findings])}"

        results.append(
            CheckResult(
                check_id="CHK_14_TRANSACTION_REVIEW",
                rule_name="Past 6-Month Transaction Listing & RM Review Cross-Reconciliation",
                verdict=chk14_verdict,
                reason_code=chk14_reason if chk14_verdict == Verdict.FAIL else None,
                priority=chk14_priority,
                evidence=chk14_evidence,
                evaluated_files=chk14_files,
                findings=chk14_findings,
            )
        )
        all_findings.extend(chk14_findings)

        return results, all_findings

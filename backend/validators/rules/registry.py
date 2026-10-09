from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from ..context import BundleContext, parse_date_safe, calculate_month_diff


class RegistryAndFormationValidator:
    """Evaluates:
    - CHK_01_BIZFILE: Latest Official Registry Extract & Operations Review (Desc 7, 8)
    - CHK_02_INCORP: Relevant Incorporation Documentation
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        # =========================================================================
        # CHECK 1: Official Registry Extract & Operations Review (Desc 7, 8)
        # =========================================================================
        chk1_findings: List[ValidationFinding] = []
        chk1_files: List[ItemizedDocStatus] = []
        chk1_reason: str | None = None
        chk1_priority: Priority = Priority.HIGH

        if not ctx.bizfile_docs:
            chk1_findings.append(
                ValidationFinding(
                    check_id="CHK_01_BIZFILE",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.HIGH,
                    missing_document="ACRA BizFile / Registry Extract",
                    reason="MISSING_BIZFILE",
                    target_field="bizfile",
                    details="Latest official registry extract (ACRA BizFile) is not provided in customer bundle.",
                )
            )
            chk1_reason = "MISSING_BIZFILE"
        else:
            for biz in ctx.bizfile_docs:
                doc_pass = True
                fail_notes = []

                # 1a. Validity window
                b_date = parse_date_safe(biz.bizfile_date)
                if b_date:
                    months_old = calculate_month_diff(ctx.today, b_date)
                    if months_old > 12:
                        doc_pass = False
                        fail_notes.append(f"Dated {biz.bizfile_date} ({months_old} months old, exceeds 12-month validity window)")
                        chk1_findings.append(
                            ValidationFinding(
                                check_id="CHK_01_BIZFILE",
                                finding_type="EXPIRED_DOCUMENT",
                                severity=Priority.HIGH,
                                reason="EXPIRED",
                                target_field="bizfile_date",
                                details=f"ACRA BizFile '{biz.filename or 'BizFile'}' is {months_old} months old (exceeds mandatory 12-month validity period).",
                            )
                        )
                        if not chk1_reason:
                            chk1_reason = "EXPIRED"
                else:
                    fail_notes.append("Extract date could not be parsed")

                # 1b. Company Status
                c_status = (biz.company_status or ctx.profile.company_status or "").upper()
                if c_status and not any(k in c_status for k in ["LIVE", "ACTIVE"]):
                    doc_pass = False
                    fail_notes.append(f"Company status is '{c_status}' instead of Live/Active")
                    chk1_findings.append(
                        ValidationFinding(
                            check_id="CHK_01_BIZFILE",
                            finding_type="INVALID_STATUS",
                            severity=Priority.HIGH,
                            reason="INACTIVE_COMPANY",
                            target_field="company_status",
                            details=f"Company status is recorded as '{c_status}' instead of Live/Active.",
                        )
                    )
                    if not chk1_reason:
                        chk1_reason = "INACTIVE_COMPANY"

                # 1c. Description 7: Place of incorporation, place of business, and business operations
                p_incorp = biz.place_of_incorporation or ctx.profile.country_of_operations or "Singapore"
                p_biz = biz.place_of_business or biz.business_operations_address or ctx.profile.place_of_business
                if not p_biz and not p_incorp:
                    doc_pass = False
                    fail_notes.append("Place of business / business operations address is missing or unverified")
                    chk1_findings.append(
                        ValidationFinding(
                            check_id="CHK_01_BIZFILE",
                            finding_type="MISSING_OPERATIONS_ADDRESS",
                            severity=Priority.MEDIUM,
                            reason="UNVERIFIED_BUSINESS_OPERATIONS",
                            target_field="place_of_business",
                            details="Place of business and business operations address could not be verified from registry extract.",
                        )
                    )
                    if not chk1_reason:
                        chk1_reason = "UNVERIFIED_BUSINESS_OPERATIONS"

                # 1d. Description 8: Core business activities, products/services, geographic coverage & website
                act = biz.core_business_activities or biz.products_services_description or ctx.profile.core_business_activities
                if not act:
                    doc_pass = False
                    fail_notes.append("Detailed core business activities (products/services) missing from profile")
                    chk1_findings.append(
                        ValidationFinding(
                            check_id="CHK_01_BIZFILE",
                            finding_type="MISSING_BUSINESS_ACTIVITIES",
                            severity=Priority.HIGH,
                            reason="MISSING_CORE_BUSINESS_ACTIVITIES",
                            target_field="core_business_activities",
                            details="Description of core business activities (products/services produced/traded) is missing from extract.",
                        )
                    )
                    if not chk1_reason:
                        chk1_reason = "MISSING_CORE_BUSINESS_ACTIVITIES"

                chk1_files.append(
                    ItemizedDocStatus(
                        doc_name=biz.filename or "ACRA BizFile",
                        doc_type="ACRA BizFile / Extract",
                        verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                        details="Valid extract (≤12m), Live status, and verified operations & core activities." if doc_pass else "; ".join(fail_notes),
                        reason=chk1_reason if not doc_pass else None,
                        is_ctc=biz.is_ctc,
                    )
                )

        chk1_verdict = Verdict.FAIL if chk1_findings else Verdict.PASS
        chk1_evidence = (
            f"Verified BizFile ({ctx.profile.legal_name or ctx.bundle_name}, UEN: {ctx.profile.uen or 'N/A'}, Status: {ctx.profile.company_status or 'Live'}, Core Activities: {ctx.profile.core_business_activities or 'Documented'}, Website: {ctx.profile.customer_website or 'N/A'})."
            if chk1_verdict == Verdict.PASS
            else f"Failed BizFile / Operations verification: {'; '.join([f.details for f in chk1_findings])}"
        )

        results.append(
            CheckResult(
                check_id="CHK_01_BIZFILE",
                rule_name="Latest Official Registry Extract & Operations Review",
                verdict=chk1_verdict,
                reason_code=chk1_reason if chk1_verdict == Verdict.FAIL else None,
                priority=chk1_priority,
                evidence=chk1_evidence,
                evaluated_files=chk1_files,
                findings=chk1_findings,
            )
        )
        all_findings.extend(chk1_findings)

        # =========================================================================
        # CHECK 2: Incorporation Documentation
        # =========================================================================
        chk2_findings: List[ValidationFinding] = []
        chk2_files: List[ItemizedDocStatus] = []
        chk2_reason: str | None = None
        chk2_priority: Priority = Priority.HIGH

        inc_source_list = ctx.incorp_docs if ctx.incorp_docs else ctx.bizfile_docs

        if not inc_source_list:
            chk2_findings.append(
                ValidationFinding(
                    check_id="CHK_02_INCORP",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.HIGH,
                    missing_document="Certificate of Incorporation",
                    reason="MISSING_INCORPORATION_DOC",
                    target_field="cert_incorporation",
                    details="No incorporation documentation or official certificate found on file.",
                )
            )
            chk2_reason = "MISSING_INCORPORATION_DOC"
        else:
            for inc in inc_source_list:
                doc_pass = True
                fail_notes = []
                if not ctx.profile.legal_name:
                    doc_pass = False
                    fail_notes.append("Missing full legal name")
                    chk2_findings.append(
                        ValidationFinding(
                            check_id="CHK_02_INCORP",
                            finding_type="MISSING_FIELD",
                            severity=Priority.HIGH,
                            reason="MISSING_LEGAL_NAME",
                            target_field="legal_name",
                            details="Full legal name is missing from incorporation documentation.",
                        )
                    )
                    if not chk2_reason:
                        chk2_reason = "MISSING_LEGAL_NAME"

                if not ctx.profile.uen:
                    doc_pass = False
                    fail_notes.append("Missing business registration number (UEN)")
                    chk2_findings.append(
                        ValidationFinding(
                            check_id="CHK_02_INCORP",
                            finding_type="MISSING_FIELD",
                            severity=Priority.HIGH,
                            reason="MISSING_UEN",
                            target_field="uen",
                            details="Business Registration Number (UEN) is missing from incorporation record.",
                        )
                    )
                    if not chk2_reason:
                        chk2_reason = "MISSING_UEN"

                if not ctx.profile.incorporation_date:
                    doc_pass = False
                    fail_notes.append("Missing incorporation date")
                    chk2_findings.append(
                        ValidationFinding(
                            check_id="CHK_02_INCORP",
                            finding_type="MISSING_FIELD",
                            severity=Priority.HIGH,
                            reason="MISSING_INCORP_DATE",
                            target_field="incorporation_date",
                            details="Date of incorporation is missing from company record.",
                        )
                    )
                    if not chk2_reason:
                        chk2_reason = "MISSING_INCORP_DATE"

                chk2_files.append(
                    ItemizedDocStatus(
                        doc_name=inc.filename or "Incorporation Document",
                        doc_type="Certificate of Incorporation",
                        verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                        details=f"Legal Name: {ctx.profile.legal_name or 'N/A'}, UEN: {ctx.profile.uen or 'N/A'}, Inc Date: {ctx.profile.incorporation_date or 'N/A'}" if doc_pass else "; ".join(fail_notes),
                        reason=chk2_reason if not doc_pass else None,
                        is_ctc=inc.is_ctc,
                    )
                )

        chk2_verdict = Verdict.FAIL if chk2_findings else Verdict.PASS
        chk2_evidence = (
            f"Incorporation verified (Entity: {ctx.profile.legal_name}, UEN: {ctx.profile.uen}, Inc Date: {ctx.profile.incorporation_date}, Country: {ctx.profile.country_of_operations or 'Singapore'})."
            if chk2_verdict == Verdict.PASS
            else f"Incorporation verification failed: {'; '.join([f.details for f in chk2_findings])}"
        )

        results.append(
            CheckResult(
                check_id="CHK_02_INCORP",
                rule_name="Relevant Incorporation Documentation",
                verdict=chk2_verdict,
                reason_code=chk2_reason if chk2_verdict == Verdict.FAIL else None,
                priority=chk2_priority,
                evidence=chk2_evidence,
                evaluated_files=chk2_files,
                findings=chk2_findings,
            )
        )
        all_findings.extend(chk2_findings)

        return results, all_findings

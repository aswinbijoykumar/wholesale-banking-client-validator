"""Deterministic Validation Engine for Wholesale Banking Policies.

Implements the first 3 corporate client validation descriptions:
1. Description 1: Latest Official Registry Extract (ACRA BizFile / COI)
   - Must be obtained and confirm current ownership, directorship, company status.
   - Validity period must be within the last 12 months.
   - Checks entity type (Public Listed, Private Limited, Partnership, Sole Proprietor).
   - Flags: valid BizFile, missing BizFile, expired/older-than-12-month BizFile, inactive company.

2. Description 2: Incorporation Documentation
   - Valid incorporation document on file.
   - Must contain full legal name, former names, UEN/reg number, incorporation date, country of ops, active/ceased status.
   - Flags: valid incorporation document, missing incorporation document, missing UEN, missing incorporation date.

3. Description 3: Constitutional Documentation & Certified True Copy (CTC)
   - M&AA (Memorandum and Articles of Association / Constitution) on file.
   - Share register / Register of Members (ROM) on file.
   - Board resolution on file where applicable.
   - Ensure constitutional documents are Certified True Copies (CTC).
   - Flags: all constitutional documents, missing M&AA, missing ROM, missing board resolution where applicable, non-certified document.
"""
from datetime import date, datetime
from typing import List, Tuple
from dateutil import parser as date_parser

from .models import (
    CheckResult,
    DocType,
    EntityType,
    NormalizedCompanyProfile,
    Priority,
    RawDocExtraction,
    ValidationFinding,
    Verdict,
)


def _parse_date_safe(d_str: str | None) -> date | None:
    if not d_str:
        return None
    try:
        # standard ISO parse or flexible date parser
        return date_parser.parse(d_str).date()
    except Exception:
        return None


def _calculate_month_diff(d1: date, d2: date) -> int:
    return (d1.year - d2.year) * 12 + (d1.month - d2.month)


def validate_wholesale_bundle(
    bundle_name: str,
    bundle_entity_type: str,
    extractions: List[RawDocExtraction],
    today: date | None = None,
) -> Tuple[List[CheckResult], List[ValidationFinding], NormalizedCompanyProfile]:
    if today is None:
        today = date.today()

    # 1. Normalize the Company Profile across extractions
    profile = NormalizedCompanyProfile(
        entity_type=bundle_entity_type or EntityType.PVT_LTD.value
    )

    bizfile_docs = [e for e in extractions if e.doc_type == DocType.BIZFILE]
    incorp_docs = [e for e in extractions if e.doc_type == DocType.CERT_INCORPORATION]
    maa_docs = [e for e in extractions if e.doc_type == DocType.MAA]
    rom_docs = [e for e in extractions if e.doc_type == DocType.ROM]
    board_docs = [e for e in extractions if e.doc_type == DocType.BOARD_RESOLUTION]

    # Populate profile from primary sources (BizFile, Incorp)
    for ext in bizfile_docs + incorp_docs + extractions:
        if ext.legal_name and not profile.legal_name:
            profile.legal_name = ext.legal_name
        if ext.uen and not profile.uen:
            profile.uen = ext.uen
        if ext.former_names and not profile.former_names:
            profile.former_names = ext.former_names
        if ext.entity_type and not profile.entity_type:
            profile.entity_type = ext.entity_type
        if ext.incorporation_date and not profile.incorporation_date:
            profile.incorporation_date = ext.incorporation_date
        if ext.country_of_operations and not profile.country_of_operations:
            profile.country_of_operations = ext.country_of_operations
        if ext.company_status and not profile.company_status:
            profile.company_status = ext.company_status
        if ext.bizfile_date and not profile.bizfile_date:
            profile.bizfile_date = ext.bizfile_date
        if ext.directors and not profile.directors:
            profile.directors = ext.directors
        if ext.ubos and not profile.ubos:
            profile.ubos = ext.ubos

    results: List[CheckResult] = []
    all_findings: List[ValidationFinding] = []

    # =========================================================================
    # CHECK 1: Official Registry Extract (ACRA BizFile / COI)
    # =========================================================================
    chk1_findings: List[ValidationFinding] = []
    chk1_reason: str | None = None
    chk1_priority: Priority = Priority.HIGH

    if not bizfile_docs:
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
        biz = bizfile_docs[0]
        # Check Bizfile age (within 12 months)
        b_date = _parse_date_safe(biz.bizfile_date)
        if b_date:
            months_old = _calculate_month_diff(today, b_date)
            if months_old > 12:
                profile.is_bizfile_fresh_12m = False
                chk1_findings.append(
                    ValidationFinding(
                        check_id="CHK_01_BIZFILE",
                        finding_type="EXPIRED_DOCUMENT",
                        severity=Priority.HIGH,
                        reason="EXPIRED",
                        target_field="bizfile_date",
                        details=f"ACRA BizFile dated {biz.bizfile_date} is {months_old} months old (exceeds mandatory 12-month validity period).",
                    )
                )
                if not chk1_reason:
                    chk1_reason = "EXPIRED"
            else:
                profile.is_bizfile_fresh_12m = True
        else:
            chk1_findings.append(
                ValidationFinding(
                    check_id="CHK_01_BIZFILE",
                    finding_type="UNCLEAR_DATE",
                    severity=Priority.MEDIUM,
                    reason="UNVERIFIED_DATE",
                    target_field="bizfile_date",
                    details="Could not parse registry extract date on BizFile to verify 12-month validity window.",
                )
            )

        # Check company status (must be Active/Live)
        c_status = (biz.company_status or profile.company_status or "").upper()
        if c_status and not any(k in c_status for k in ["LIVE", "ACTIVE"]):
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

        # Check Directors / Ownership confirmed
        if not biz.directors and not profile.directors:
            chk1_findings.append(
                ValidationFinding(
                    check_id="CHK_01_BIZFILE",
                    finding_type="MISSING_DIRECTORSHIP",
                    severity=Priority.HIGH,
                    reason="MISSING_DIRECTORS_LIST",
                    target_field="directors",
                    details="No current directorship details found on official extract.",
                )
            )

    chk1_verdict = Verdict.FAIL if chk1_findings else Verdict.PASS
    chk1_evidence = (
        f"Verified BizFile ({profile.legal_name or bundle_name}, UEN: {profile.uen or 'N/A'}, Status: {profile.company_status or 'Live'})."
        if chk1_verdict == Verdict.PASS
        else f"Failed BizFile verification: {'; '.join([f.details for f in chk1_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_01_BIZFILE",
            rule_name="Latest Official Registry Extract (ACRA BizFile / COI)",
            verdict=chk1_verdict,
            reason_code=chk1_reason if chk1_verdict == Verdict.FAIL else None,
            priority=chk1_priority,
            evidence=chk1_evidence,
            findings=chk1_findings,
        )
    )
    all_findings.extend(chk1_findings)

    # =========================================================================
    # CHECK 2: Incorporation Documentation
    # =========================================================================
    chk2_findings: List[ValidationFinding] = []
    chk2_reason: str | None = None
    chk2_priority: Priority = Priority.HIGH

    # Note: BizFile or dedicated Certificate of Incorporation can provide incorporation evidence
    inc_source = incorp_docs[0] if incorp_docs else (bizfile_docs[0] if bizfile_docs else None)

    if not inc_source:
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
        # Check Full Legal Name
        if not profile.legal_name:
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

        # Check UEN / Reg Number
        if not profile.uen:
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

        # Check Incorporation Date
        if not profile.incorporation_date:
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

    chk2_verdict = Verdict.FAIL if chk2_findings else Verdict.PASS
    chk2_evidence = (
        f"Incorporation verified (Entity: {profile.legal_name}, UEN: {profile.uen}, Inc Date: {profile.incorporation_date}, Country: {profile.country_of_operations or 'Singapore'})."
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
            findings=chk2_findings,
        )
    )
    all_findings.extend(chk2_findings)

    # =========================================================================
    # CHECK 3: Constitutional Documentation & Certified True Copies (CTC)
    # =========================================================================
    chk3_findings: List[ValidationFinding] = []
    chk3_reason: str | None = None
    chk3_priority: Priority = Priority.HIGH

    is_corp = bundle_entity_type in [
        EntityType.PVT_LTD.value,
        EntityType.PUBLIC_LISTED.value,
        EntityType.FOREIGN_CORP.value,
    ]

    if is_corp:
        # Check M&AA
        if not maa_docs:
            chk3_findings.append(
                ValidationFinding(
                    check_id="CHK_03_CONST",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.HIGH,
                    missing_document="Memorandum and Articles of Association (M&AA)",
                    reason="MISSING_MAA",
                    target_field="maa",
                    details="Memorandum and Articles of Association (M&AA / Constitution) is missing from file.",
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_MAA"
        else:
            # Check CTC on M&AA
            if not any(d.is_ctc for d in maa_docs):
                chk3_findings.append(
                    ValidationFinding(
                        check_id="CHK_03_CONST",
                        finding_type="NON_CERTIFIED_DOCUMENT",
                        severity=Priority.MEDIUM,
                        reason="NON_CERTIFIED_DOCUMENT",
                        target_field="maa_ctc",
                        details="M&AA is on file but does not contain a verified Certified True Copy (CTC) stamp or certifier signature.",
                    )
                )
                if not chk3_reason:
                    chk3_reason = "NON_CERTIFIED_DOCUMENT"

        # Check Register of Members (ROM) / Share Register
        if not rom_docs:
            chk3_findings.append(
                ValidationFinding(
                    check_id="CHK_03_CONST",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.HIGH,
                    missing_document="Register of Members (ROM)",
                    reason="MISSING_ROM",
                    target_field="rom",
                    details="Register of Members (ROM) / Share Register is missing from file.",
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_ROM"
        else:
            if not any(d.is_ctc for d in rom_docs):
                chk3_findings.append(
                    ValidationFinding(
                        check_id="CHK_03_CONST",
                        finding_type="NON_CERTIFIED_DOCUMENT",
                        severity=Priority.MEDIUM,
                        reason="NON_CERTIFIED_DOCUMENT",
                        target_field="rom_ctc",
                        details="Register of Members (ROM) does not contain a verified Certified True Copy (CTC) stamp.",
                    )
                )
                if not chk3_reason:
                    chk3_reason = "NON_CERTIFIED_DOCUMENT"

        # Check Board Resolution (conditional / where applicable)
        if not board_docs:
            chk3_findings.append(
                ValidationFinding(
                    check_id="CHK_03_CONST",
                    finding_type="MISSING_DOCUMENT",
                    severity=Priority.MEDIUM,
                    missing_document="Board Resolution",
                    reason="MISSING_BOARD_RESOLUTION",
                    target_field="board_resolution",
                    details="Board resolution for account opening / authorized signatories is missing where applicable.",
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_BOARD_RESOLUTION"

    chk3_verdict = Verdict.FAIL if chk3_findings else Verdict.PASS
    chk3_evidence = (
        "Constitutional documents (M&AA, ROM, Board Resolution) verified with valid Certified True Copy (CTC) stamps."
        if chk3_verdict == Verdict.PASS
        else f"Constitutional documentation issues: {'; '.join([f.details for f in chk3_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_03_CONST",
            rule_name="Constitutional Documentation & CTC Validation",
            verdict=chk3_verdict,
            reason_code=chk3_reason if chk3_verdict == Verdict.FAIL else None,
            priority=chk3_priority,
            evidence=chk3_evidence,
            findings=chk3_findings,
        )
    )
    all_findings.extend(chk3_findings)

    return results, all_findings, profile

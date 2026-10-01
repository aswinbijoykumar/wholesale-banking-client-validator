"""Deterministic Validation Engine for Wholesale Bank Policies.

Implements all 6 corporate client validation descriptions:
1. Description 1: Latest Official Registry Extract (ACRA BizFile / COI)
2. Description 2: Relevant Incorporation Documentation
3. Description 3: Constitutional Documentation & Certified True Copy (CTC)
4. Description 4: Corporate Structure (Directorship & UBO changes) + Key Controllers + ID CTCs
5. Description 5: Non-expired ID Documents & Proof of Address
6. Description 6: Nominee Arrangements, Bearer Shares & Complex Structures (GLDB Declaration)
"""
from datetime import date, datetime
from typing import List, Tuple
from dateutil import parser as date_parser

from .models import (
    CheckResult,
    DocType,
    EntityType,
    ItemizedDocStatus,
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

    profile = NormalizedCompanyProfile(
        entity_type=bundle_entity_type or EntityType.PVT_LTD.value
    )

    bizfile_docs = [e for e in extractions if e.doc_type == DocType.BIZFILE]
    incorp_docs = [e for e in extractions if e.doc_type == DocType.CERT_INCORPORATION]
    maa_docs = [e for e in extractions if e.doc_type == DocType.MAA]
    rom_docs = [e for e in extractions if e.doc_type == DocType.ROM]
    rod_docs = [e for e in extractions if e.doc_type == DocType.ROD]
    board_docs = [e for e in extractions if e.doc_type == DocType.BOARD_RESOLUTION]
    ubo_decl_docs = [e for e in extractions if e.doc_type == DocType.UBO_DECLARATION]
    id_docs = [e for e in extractions if e.doc_type == DocType.ID_DOCUMENT]
    poa_docs = [e for e in extractions if e.doc_type == DocType.PROOF_OF_ADDRESS]

    # Populate profile from primary sources (BizFile, Incorp, ROD, UBO Declaration)
    for ext in bizfile_docs + incorp_docs + rod_docs + ubo_decl_docs + extractions:
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
        if ext.has_nominee_arrangement:
            profile.has_nominee_arrangement = True
        if ext.has_bearer_shares:
            profile.has_bearer_shares = True
        if ext.has_complex_structure:
            profile.has_complex_structure = True
            profile.complex_structure_rationale = ext.complex_structure_rationale
            profile.risk_rating = "HIGH"

    results: List[CheckResult] = []
    all_findings: List[ValidationFinding] = []

    # =========================================================================
    # CHECK 1: Official Registry Extract (ACRA BizFile / COI)
    # =========================================================================
    chk1_findings: List[ValidationFinding] = []
    chk1_files: List[ItemizedDocStatus] = []
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
        for biz in bizfile_docs:
            doc_pass = True
            fail_notes = []
            b_date = _parse_date_safe(biz.bizfile_date)
            if b_date:
                months_old = _calculate_month_diff(today, b_date)
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

            c_status = (biz.company_status or profile.company_status or "").upper()
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

            chk1_files.append(
                ItemizedDocStatus(
                    doc_name=biz.filename or "ACRA BizFile",
                    doc_type="ACRA BizFile / Extract",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details="Valid extract within 12 months & active status." if doc_pass else "; ".join(fail_notes),
                    reason=chk1_reason if not doc_pass else None,
                    is_ctc=biz.is_ctc,
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

    inc_source_list = incorp_docs if incorp_docs else bizfile_docs

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
            if not profile.legal_name:
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

            if not profile.uen:
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

            if not profile.incorporation_date:
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
                    details=f"Legal Name: {profile.legal_name or 'N/A'}, UEN: {profile.uen or 'N/A'}, Inc Date: {profile.incorporation_date or 'N/A'}" if doc_pass else "; ".join(fail_notes),
                    reason=chk2_reason if not doc_pass else None,
                    is_ctc=inc.is_ctc,
                )
            )

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
            evaluated_files=chk2_files,
            findings=chk2_findings,
        )
    )
    all_findings.extend(chk2_findings)

    # =========================================================================
    # CHECK 3: Constitutional Documentation & Certified True Copies (CTC)
    # =========================================================================
    chk3_findings: List[ValidationFinding] = []
    chk3_files: List[ItemizedDocStatus] = []
    chk3_reason: str | None = None
    chk3_priority: Priority = Priority.HIGH

    is_corp = bundle_entity_type in [
        EntityType.PVT_LTD.value,
        EntityType.PUBLIC_LISTED.value,
        EntityType.FOREIGN_CORP.value,
    ]

    if is_corp:
        # 3a. Evaluate Memorandum and Articles of Association (M&AA)
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
            chk3_files.append(
                ItemizedDocStatus(
                    doc_name="M&AA / Constitution",
                    doc_type="Memorandum & Articles of Association",
                    verdict=Verdict.FAIL,
                    details="Missing document — not provided in client file.",
                    reason="MISSING_MAA",
                    is_ctc=False,
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_MAA"
        else:
            for m in maa_docs:
                m_pass = m.is_ctc and m.is_fully_executed and not m.is_blank_template
                details = "M&AA verified with valid Certified True Copy (CTC) stamp." if m_pass else ("Missing Certified True Copy (CTC) stamp/signature." if not m.is_ctc else "Incomplete/unexecuted M&AA.")
                if not m_pass:
                    chk3_findings.append(
                        ValidationFinding(
                            check_id="CHK_03_CONST",
                            finding_type="NON_CERTIFIED_DOCUMENT",
                            severity=Priority.MEDIUM,
                            reason="NON_CERTIFIED_DOCUMENT",
                            target_field="maa_ctc",
                            details=f"M&AA '{m.filename or 'M&AA'}' is on file but lacks a verified Certified True Copy (CTC) stamp/signature.",
                        )
                    )
                    if not chk3_reason:
                        chk3_reason = "NON_CERTIFIED_DOCUMENT"

                chk3_files.append(
                    ItemizedDocStatus(
                        doc_name=m.filename or "M&AA Document",
                        doc_type="Memorandum & Articles of Association",
                        verdict=Verdict.PASS if m_pass else Verdict.FAIL,
                        details=details,
                        reason="NON_CERTIFIED_DOCUMENT" if not m_pass else None,
                        is_ctc=m.is_ctc,
                    )
                )

        # 3b. Evaluate Register of Members (ROM)
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
            chk3_files.append(
                ItemizedDocStatus(
                    doc_name="Register of Members (ROM)",
                    doc_type="Register of Members",
                    verdict=Verdict.FAIL,
                    details="Missing document — not provided in client file.",
                    reason="MISSING_ROM",
                    is_ctc=False,
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_ROM"
        else:
            for r_doc in rom_docs:
                r_pass = r_doc.is_ctc and r_doc.is_fully_executed
                details = "ROM verified with valid Certified True Copy (CTC) stamp." if r_pass else "Register of Members lacks a verified Certified True Copy (CTC) stamp."
                if not r_pass:
                    chk3_findings.append(
                        ValidationFinding(
                            check_id="CHK_03_CONST",
                            finding_type="NON_CERTIFIED_DOCUMENT",
                            severity=Priority.MEDIUM,
                            reason="NON_CERTIFIED_DOCUMENT",
                            target_field="rom_ctc",
                            details=f"ROM '{r_doc.filename or 'ROM'}' does not contain a verified Certified True Copy (CTC) stamp.",
                        )
                    )
                    if not chk3_reason:
                        chk3_reason = "NON_CERTIFIED_DOCUMENT"

                chk3_files.append(
                    ItemizedDocStatus(
                        doc_name=r_doc.filename or "Register of Members",
                        doc_type="Register of Members (ROM)",
                        verdict=Verdict.PASS if r_pass else Verdict.FAIL,
                        details=details,
                        reason="NON_CERTIFIED_DOCUMENT" if not r_pass else None,
                        is_ctc=r_doc.is_ctc,
                    )
                )

        # 3c. Evaluate Board Resolution
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
            chk3_files.append(
                ItemizedDocStatus(
                    doc_name="Board Resolution",
                    doc_type="Board Resolution / Signing Mandate",
                    verdict=Verdict.FAIL,
                    details="Missing document — not provided where applicable.",
                    reason="MISSING_BOARD_RESOLUTION",
                    is_ctc=False,
                )
            )
            if not chk3_reason:
                chk3_reason = "MISSING_BOARD_RESOLUTION"
        else:
            for b_doc in board_docs:
                b_pass = not b_doc.is_blank_template and b_doc.is_fully_executed
                details = "Board resolution properly executed with director signatures." if b_pass else "Board Resolution on file is blank, incomplete, or lacks authorized director signatures/dates."
                if not b_pass:
                    chk3_findings.append(
                        ValidationFinding(
                            check_id="CHK_03_CONST",
                            finding_type="INCOMPLETE_DOCUMENT",
                            severity=Priority.HIGH,
                            missing_document="Executed Board Resolution",
                            reason="UNEXECUTED_BOARD_RESOLUTION",
                            target_field="board_resolution_execution",
                            details=f"Board Resolution '{b_doc.filename or 'Board Resolution'}' is incomplete, blank, or lacks authorized director execution signatures/dates.",
                        )
                    )
                    if not chk3_reason:
                        chk3_reason = "UNEXECUTED_BOARD_RESOLUTION"

                chk3_files.append(
                    ItemizedDocStatus(
                        doc_name=b_doc.filename or "Board Resolution",
                        doc_type="Board Resolution / Signing Mandate",
                        verdict=Verdict.PASS if b_pass else Verdict.FAIL,
                        details=details,
                        reason="UNEXECUTED_BOARD_RESOLUTION" if not b_pass else None,
                        is_ctc=b_doc.is_ctc,
                    )
                )

    chk3_verdict = Verdict.FAIL if chk3_findings else Verdict.PASS
    chk3_evidence = (
        "All constitutional documents (M&AA, ROM, Board Resolution) verified with valid CTC stamps and proper execution."
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
            evaluated_files=chk3_files,
            findings=chk3_findings,
        )
    )
    all_findings.extend(chk3_findings)

    # =========================================================================
    # CHECK 4: Corporate Structure Changes, Key Controllers & ID CTCs
    # =========================================================================
    chk4_findings: List[ValidationFinding] = []
    chk4_files: List[ItemizedDocStatus] = []
    chk4_reason: str | None = None
    chk4_priority: Priority = Priority.HIGH

    # Check Register of Directors (ROD)
    if not rod_docs and not bizfile_docs:
        chk4_findings.append(
            ValidationFinding(
                check_id="CHK_04_CORP_STRUCT",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="Register of Directors (ROD)",
                reason="MISSING_ROD",
                target_field="rod",
                details="Register of Directors (ROD) is missing from client file.",
            )
        )
        chk4_files.append(
            ItemizedDocStatus(
                doc_name="Register of Directors (ROD)",
                doc_type="Register of Directors",
                verdict=Verdict.FAIL,
                details="Missing Register of Directors file.",
                reason="MISSING_ROD",
            )
        )
        chk4_reason = "MISSING_ROD"
    else:
        for r_doc in (rod_docs if rod_docs else bizfile_docs):
            chk4_files.append(
                ItemizedDocStatus(
                    doc_name=r_doc.filename or "Register of Directors",
                    doc_type="Register of Directors (ROD)",
                    verdict=Verdict.PASS,
                    details=f"Confirmed {len(profile.directors)} directorship record(s) on file.",
                    is_ctc=r_doc.is_ctc,
                )
            )

    # Confirm UBOs and shareholding percentages recorded
    all_ubos = profile.ubos
    if not all_ubos:
        for ext in ubo_decl_docs + rom_docs + bizfile_docs:
            if ext.ubos:
                all_ubos = ext.ubos
                break

    if not all_ubos:
        chk4_findings.append(
            ValidationFinding(
                check_id="CHK_04_CORP_STRUCT",
                finding_type="UNVERIFIED_UBO",
                severity=Priority.HIGH,
                reason="MISSING_UBO_IDENTIFICATION",
                target_field="ubos",
                details="No Ultimate Beneficial Owners (UBOs) or shareholding percentages identified on file.",
            )
        )
        if not chk4_reason:
            chk4_reason = "MISSING_UBO_IDENTIFICATION"
    else:
        for u in all_ubos:
            if u.ownership_percentage is None or u.ownership_percentage <= 0:
                chk4_findings.append(
                    ValidationFinding(
                        check_id="CHK_04_CORP_STRUCT",
                        finding_type="MISSING_SHAREHOLDING",
                        severity=Priority.HIGH,
                        reason="UNSPECIFIED_SHAREHOLDING_PERCENTAGE",
                        target_field="ubos",
                        details=f"UBO '{u.name}' is recorded without explicit shareholding percentage.",
                    )
                )
                if not chk4_reason:
                    chk4_reason = "UNSPECIFIED_SHAREHOLDING_PERCENTAGE"

    # Check that ID documents for Directors/UBOs are Certified True Copies (CTC)
    if id_docs:
        for id_doc in id_docs:
            if not id_doc.is_ctc:
                chk4_findings.append(
                    ValidationFinding(
                        check_id="CHK_04_CORP_STRUCT",
                        finding_type="NON_CERTIFIED_ID",
                        severity=Priority.MEDIUM,
                        reason="NON_CERTIFIED_ID_DOCUMENT",
                        target_field="id_ctc",
                        details=f"ID document '{id_doc.filename or 'ID'}' lacks a verified Certified True Copy (CTC) stamp.",
                    )
                )
                chk4_files.append(
                    ItemizedDocStatus(
                        doc_name=id_doc.filename or "ID Document",
                        doc_type="Director / UBO ID",
                        verdict=Verdict.FAIL,
                        details="ID on file lacks Certified True Copy (CTC) certification stamp.",
                        reason="NON_CERTIFIED_ID_DOCUMENT",
                        is_ctc=False,
                    )
                )
                if not chk4_reason:
                    chk4_reason = "NON_CERTIFIED_ID_DOCUMENT"
            else:
                chk4_files.append(
                    ItemizedDocStatus(
                        doc_name=id_doc.filename or "ID Document",
                        doc_type="Director / UBO ID",
                        verdict=Verdict.PASS,
                        details="Verified Certified True Copy (CTC) identification document.",
                        is_ctc=True,
                    )
                )

    chk4_verdict = Verdict.FAIL if chk4_findings else Verdict.PASS
    chk4_evidence = (
        f"Corporate structure verified: {len(profile.directors)} Director(s) on ROD, {len(all_ubos)} UBO(s) with confirmed shareholding percentages and CTC verified identification."
        if chk4_verdict == Verdict.PASS
        else f"Corporate structure / Controller issues: {'; '.join([f.details for f in chk4_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_04_CORP_STRUCT",
            rule_name="Corporate Structure & Key Controllers Review",
            verdict=chk4_verdict,
            reason_code=chk4_reason if chk4_verdict == Verdict.FAIL else None,
            priority=chk4_priority,
            evidence=chk4_evidence,
            evaluated_files=chk4_files,
            findings=chk4_findings,
        )
    )
    all_findings.extend(chk4_findings)

    # =========================================================================
    # CHECK 5: ID Documents & Proof of Address Expiry & Validity Review
    # =========================================================================
    chk5_findings: List[ValidationFinding] = []
    chk5_files: List[ItemizedDocStatus] = []
    chk5_reason: str | None = None
    chk5_priority: Priority = Priority.HIGH

    # 1. Missing ID Document Check
    if not id_docs:
        chk5_findings.append(
            ValidationFinding(
                check_id="CHK_05_ID_EXPIRY",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="Identification Document (Passport / National ID)",
                reason="MISSING_ID_DOCUMENT",
                target_field="id_document",
                details="No identification document images/PDFs on file for directors or beneficial owners.",
            )
        )
        chk5_reason = "MISSING_ID_DOCUMENT"
        chk5_files.append(
            ItemizedDocStatus(
                doc_name="Identity Document (Passport / NRIC)",
                doc_type="Passport / National ID",
                verdict=Verdict.FAIL,
                details="No identification document uploaded.",
                reason="MISSING_ID_DOCUMENT",
                is_ctc=False,
            )
        )

    # 2. Evaluate ID Documents
    for d in id_docs:
        d_pass = True
        fail_notes = []
        doc_reason = None

        # 2a. Fraudulent / Template / Synthetic ID Detection
        if d.is_fraudulent_or_template or d.fraud_reasons or d.has_watermark_or_template_generator or d.has_synthetic_placeholder_data:
            d_pass = False
            reasons_str = "; ".join(d.fraud_reasons) if d.fraud_reasons else "Template watermark or synthetic placeholder data detected."
            fail_notes.append(reasons_str)
            chk5_findings.append(
                ValidationFinding(
                    check_id="CHK_05_ID_EXPIRY",
                    finding_type="FRAUDULENT_DOCUMENT",
                    severity=Priority.HIGH,
                    reason="FRAUDULENT_DOCUMENT_DETECTED",
                    target_field="id_document",
                    details=f"FRAUDULENT / UNACCEPTABLE DOCUMENT DETECTED: ID document '{d.filename or 'ID'}' {reasons_str}",
                )
            )
            doc_reason = "FRAUDULENT_DOCUMENT_DETECTED"
            if not chk5_reason:
                chk5_reason = "FRAUDULENT_DOCUMENT_DETECTED"

        # 2b. Expiry check
        if d.id_expiry_date:
            exp_d = _parse_date_safe(d.id_expiry_date)
            if exp_d and exp_d < today:
                if not d.has_exceptional_approval:
                    d_pass = False
                    fail_notes.append(f"Expired on {d.id_expiry_date} without exceptional approval")
                    chk5_findings.append(
                        ValidationFinding(
                            check_id="CHK_05_ID_EXPIRY",
                            finding_type="EXPIRED_DOCUMENT",
                            severity=Priority.HIGH,
                            reason="EXPIRED_ID_DOCUMENT",
                            target_field="id_expiry_date",
                            details=f"ID document '{d.filename or 'ID'}' ({d.id_type or 'Passport'} for {d.id_holder_name or 'Individual'}, Exp: {d.id_expiry_date}) is EXPIRED without exceptional approval.",
                        )
                    )
                    if not doc_reason:
                        doc_reason = "EXPIRED_ID_DOCUMENT"
                    if not chk5_reason:
                        chk5_reason = "EXPIRED_ID_DOCUMENT"
        elif d.is_expired and not d.has_exceptional_approval:
            d_pass = False
            fail_notes.append("ID marked expired without exceptional approval")
            chk5_findings.append(
                ValidationFinding(
                    check_id="CHK_05_ID_EXPIRY",
                    finding_type="EXPIRED_DOCUMENT",
                    severity=Priority.HIGH,
                    reason="EXPIRED_ID_DOCUMENT",
                    target_field="id_expiry_date",
                    details=f"ID document '{d.filename or 'ID'}' for {d.id_holder_name or 'Individual'} is expired.",
                )
            )
            if not doc_reason:
                doc_reason = "EXPIRED_ID_DOCUMENT"
            if not chk5_reason:
                chk5_reason = "EXPIRED_ID_DOCUMENT"

        chk5_files.append(
            ItemizedDocStatus(
                doc_name=d.filename or "ID Document",
                doc_type=d.id_type or "Passport / National ID",
                verdict=Verdict.PASS if d_pass else Verdict.FAIL,
                details=f"Holder: {d.id_holder_name or 'Individual'}, Expiry: {d.id_expiry_date or 'Valid'}" if d_pass else "; ".join(fail_notes),
                reason=doc_reason,
                is_ctc=d.is_ctc,
            )
        )

    # 3. Evaluate Proof of Address (POA)
    for p in poa_docs:
        p_pass = True
        p_fail_notes = []
        p_reason = None

        # 3a. Watermarks / template generator in Utility Bill
        if p.is_fraudulent_or_template or p.has_watermark_or_template_generator or p.fraud_reasons:
            p_pass = False
            p_reasons_str = "; ".join(p.fraud_reasons) if p.fraud_reasons else "Template generator watermark detected on utility bill."
            p_fail_notes.append(p_reasons_str)
            chk5_findings.append(
                ValidationFinding(
                    check_id="CHK_05_ID_EXPIRY",
                    finding_type="FRAUDULENT_DOCUMENT",
                    severity=Priority.HIGH,
                    reason="FRAUDULENT_DOCUMENT_DETECTED",
                    target_field="proof_of_address",
                    details=f"FRAUDULENT / UNACCEPTABLE UTILITY BILL: Proof of address '{p.filename or 'POA'}' {p_reasons_str}",
                )
            )
            p_reason = "FRAUDULENT_DOCUMENT_DETECTED"
            if not chk5_reason:
                chk5_reason = "FRAUDULENT_DOCUMENT_DETECTED"

        # 3b. 90-day validity threshold for Proof of Address
        if p.address_issue_date:
            issue_d = _parse_date_safe(p.address_issue_date)
            if issue_d:
                days_old = (today - issue_d).days
                if days_old > 90 and not p.has_exceptional_approval:
                    p_pass = False
                    p_fail_notes.append(f"Dated {p.address_issue_date} ({days_old} days old, exceeds 90-day validity threshold; no exceptional approval)")
                    chk5_findings.append(
                        ValidationFinding(
                            check_id="CHK_05_ID_EXPIRY",
                            finding_type="EXPIRED_DOCUMENT",
                            severity=Priority.HIGH,
                            reason="EXPIRED_PROOF_OF_ADDRESS",
                            target_field="address_issue_date",
                            details=f"EXPIRED PROOF OF ADDRESS: Utility bill dated {p.address_issue_date} exceeds the 90-day validity threshold ({days_old} days old); no exceptional approval attached.",
                        )
                    )
                    if not p_reason:
                        p_reason = "EXPIRED_PROOF_OF_ADDRESS"
                    if not chk5_reason:
                        chk5_reason = "EXPIRED_PROOF_OF_ADDRESS"

        # 3c. Entity & Address Mismatch against ID documents
        if id_docs:
            primary_id = id_docs[0]
            # Name comparison
            id_name = (primary_id.id_holder_name or "").strip().upper()
            poa_name = (p.address_holder_name or "").strip().upper()
            if id_name and poa_name:
                clean_id = id_name.replace("MR ", "").replace("MS ", "").replace("DR ", "").strip()
                clean_poa = poa_name.replace("MR ", "").replace("MS ", "").replace("DR ", "").strip()
                if clean_id != clean_poa and not (clean_id in clean_poa or clean_poa in clean_id):
                    p_pass = False
                    p_fail_notes.append(f"Name mismatch: ID '{primary_id.id_holder_name}' vs Utility Bill '{p.address_holder_name}'")
                    chk5_findings.append(
                        ValidationFinding(
                            check_id="CHK_05_ID_EXPIRY",
                            finding_type="MISMATCH_NAME",
                            severity=Priority.HIGH,
                            reason="NAME_MISMATCH",
                            target_field="address_holder_name",
                            details=f"ENTITY MISMATCH: ID Name: \"{primary_id.id_holder_name}\" vs Utility Bill Name: \"{p.address_holder_name}\".",
                        )
                    )
                    if not p_reason:
                        p_reason = "ENTITY_ADDRESS_MISMATCH"
                    if not chk5_reason:
                        chk5_reason = "ENTITY_ADDRESS_MISMATCH"

            # Address comparison
            id_addr = (primary_id.id_address or "").strip().upper()
            poa_addr = (p.proof_address or "").strip().upper()
            if id_addr and poa_addr:
                # Check for major token overlap
                id_tokens = set(id_addr.replace(",", " ").split())
                poa_tokens = set(poa_addr.replace(",", " ").split())
                common_meaningful = [t for t in id_tokens.intersection(poa_tokens) if len(t) > 3 and t not in ["SINGAPORE", "ROAD", "STREET", "DRIVE", "AVENUE", "BLOCK", "LTD"]]
                if not common_meaningful and id_addr != poa_addr:
                    p_pass = False
                    p_fail_notes.append(f"Address mismatch: ID '{primary_id.id_address}' vs Utility Bill '{p.proof_address}'")
                    chk5_findings.append(
                        ValidationFinding(
                            check_id="CHK_05_ID_EXPIRY",
                            finding_type="MISMATCH_ADDRESS",
                            severity=Priority.HIGH,
                            reason="ADDRESS_MISMATCH",
                            target_field="proof_address",
                            details=f"ADDRESS MISMATCH: ID Address: \"{primary_id.id_address}\" vs Utility Bill Address: \"{p.proof_address}\".",
                        )
                    )
                    if not p_reason:
                        p_reason = "ENTITY_ADDRESS_MISMATCH"
                    if not chk5_reason:
                        chk5_reason = "ENTITY_ADDRESS_MISMATCH"

        chk5_files.append(
            ItemizedDocStatus(
                doc_name=p.filename or "Proof of Address",
                doc_type="Proof of Address / Utility Bill",
                verdict=Verdict.PASS if p_pass else Verdict.FAIL,
                details=f"Holder: {p.address_holder_name or 'Client'}, Issued: {p.address_issue_date or 'Recent'}" if p_pass else "; ".join(p_fail_notes),
                reason=p_reason,
                is_ctc=p.is_ctc,
            )
        )

    chk5_verdict = Verdict.FAIL if chk5_findings else Verdict.PASS
    chk5_evidence = (
        f"All {len(id_docs)} identity document(s) and {len(poa_docs)} proof of address document(s) verified as authentic, matching, current, and within 90 days."
        if chk5_verdict == Verdict.PASS
        else f"ID & Proof of Address Validity Failures: {'; '.join([f.details for f in chk5_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_05_ID_EXPIRY",
            rule_name="ID & Proof of Address Validity Review",
            verdict=chk5_verdict,
            reason_code=chk5_reason if chk5_verdict == Verdict.FAIL else None,
            priority=chk5_priority,
            evidence=chk5_evidence,
            evaluated_files=chk5_files,
            findings=chk5_findings,
        )
    )
    all_findings.extend(chk5_findings)

    # =========================================================================
    # CHECK 6: Nominee, Bearer Share & Complex Structure Risk Review
    # =========================================================================
    chk6_findings: List[ValidationFinding] = []
    chk6_files: List[ItemizedDocStatus] = []
    chk6_reason: str | None = None
    chk6_priority: Priority = Priority.HIGH

    if not ubo_decl_docs:
        chk6_findings.append(
            ValidationFinding(
                check_id="CHK_06_UBO_COMPLEX",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="GLDB Declaration of Ultimate Beneficial Owners (Mar 2026)",
                reason="MISSING_UBO_DECLARATION",
                target_field="ubo_declaration",
                details="Official GLDB Declaration of Ultimate Beneficial Owners form is missing from client bundle.",
            )
        )
        chk6_files.append(
            ItemizedDocStatus(
                doc_name="GLDB UBO Declaration (Mar 2026)",
                doc_type="UBO Declaration Form",
                verdict=Verdict.FAIL,
                details="Missing GLDB Declaration of Ultimate Beneficial Owners form.",
                reason="MISSING_UBO_DECLARATION",
            )
        )
        chk6_reason = "MISSING_UBO_DECLARATION"
    else:
        for ubo_decl in ubo_decl_docs:
            decl_pass = True
            fail_notes = []
            if ubo_decl.is_blank_template or not ubo_decl.is_fully_executed:
                decl_pass = False
                fail_notes.append("Blank template or unexecuted signatory section")
                chk6_findings.append(
                    ValidationFinding(
                        check_id="CHK_06_UBO_COMPLEX",
                        finding_type="INCOMPLETE_DOCUMENT",
                        severity=Priority.HIGH,
                        reason="UNEXECUTED_UBO_DECLARATION",
                        target_field="ubo_declaration",
                        details=f"GLDB UBO Declaration '{ubo_decl.filename or 'UBO Declaration'}' is blank, incomplete, or lacks authorized signatory execution.",
                    )
                )
                if not chk6_reason:
                    chk6_reason = "UNEXECUTED_UBO_DECLARATION"

            if ubo_decl.has_bearer_shares or profile.has_bearer_shares:
                decl_pass = False
                fail_notes.append("Bearer shares identified (prohibited/restricted)")
                chk6_findings.append(
                    ValidationFinding(
                        check_id="CHK_06_UBO_COMPLEX",
                        finding_type="PROHIBITED_FEATURE",
                        severity=Priority.HIGH,
                        reason="BEARER_SHARES_IDENTIFIED",
                        target_field="bearer_shares",
                        details="Bearer shares identified in ownership structure (high risk / restricted under policy).",
                    )
                )
                if not chk6_reason:
                    chk6_reason = "BEARER_SHARES_IDENTIFIED"

            if ubo_decl.has_complex_structure or profile.has_complex_structure:
                if not ubo_decl.complex_structure_rationale and not profile.complex_structure_rationale:
                    decl_pass = False
                    fail_notes.append("Complex structure identified without documented legitimate business rationale (High Risk)")
                    chk6_findings.append(
                        ValidationFinding(
                            check_id="CHK_06_UBO_COMPLEX",
                            finding_type="COMPLEX_STRUCTURE_UNJUSTIFIED",
                            severity=Priority.HIGH,
                            reason="COMPLEX_STRUCTURE_WITHOUT_RATIONALE",
                            target_field="complex_structure_rationale",
                            details="Complex multi-tiered structure identified without documented legitimate business purpose (Rated HIGH RISK by default).",
                        )
                    )
                    if not chk6_reason:
                        chk6_reason = "COMPLEX_STRUCTURE_WITHOUT_RATIONALE"

            chk6_files.append(
                ItemizedDocStatus(
                    doc_name=ubo_decl.filename or "GLDB UBO Declaration",
                    doc_type="GLDB Declaration of UBOs",
                    verdict=Verdict.PASS if decl_pass else Verdict.FAIL,
                    details="UBO declaration executed, ownership structure verified." if decl_pass else "; ".join(fail_notes),
                    reason=chk6_reason if not decl_pass else None,
                    is_ctc=ubo_decl.is_ctc,
                )
            )

    chk6_verdict = Verdict.FAIL if chk6_findings else Verdict.PASS
    chk6_evidence = (
        "GLDB UBO Declaration verified: Ownership aligned, no prohibited bearer shares, and ownership structure risk evaluated."
        if chk6_verdict == Verdict.PASS
        else f"UBO Declaration & Structure findings: {'; '.join([f.details for f in chk6_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_06_UBO_COMPLEX",
            rule_name="Nominee, Bearer Share & Complex Structure Risk Review",
            verdict=chk6_verdict,
            reason_code=chk6_reason if chk6_verdict == Verdict.FAIL else None,
            priority=chk6_priority,
            evidence=chk6_evidence,
            evaluated_files=chk6_files,
            findings=chk6_findings,
        )
    )
    all_findings.extend(chk6_findings)

    return results, all_findings, profile

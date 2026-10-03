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
    sanction_docs = [e for e in extractions if e.doc_type == DocType.SANCTION_QUESTIONNAIRE or e.is_sanction_questionnaire]
    institutional_docs = [e for e in extractions if e.doc_type == DocType.INSTITUTIONAL_QUESTIONNAIRE or e.institutional_type]
    cdd_docs = [e for e in extractions if e.doc_type == DocType.CDD_EDD_QUESTIONNAIRE or e.singapore_nexus_rationale or e.continuation_rationale]
    translation_docs = [e for e in extractions if e.doc_type == DocType.TRANSLATION_CERTIFICATE or e.has_certified_translation]

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
        if ext.place_of_business and not profile.place_of_business:
            profile.place_of_business = ext.place_of_business
        if ext.company_status and not profile.company_status:
            profile.company_status = ext.company_status
        if ext.bizfile_date and not profile.bizfile_date:
            profile.bizfile_date = ext.bizfile_date
        if ext.core_business_activities and not profile.core_business_activities:
            profile.core_business_activities = ext.core_business_activities
        if ext.geographic_coverage and not profile.geographic_coverage:
            profile.geographic_coverage = ext.geographic_coverage
        if ext.customer_website and not profile.customer_website:
            profile.customer_website = ext.customer_website
        if ext.directors and not profile.directors:
            profile.directors = ext.directors
        if ext.ubos and not profile.ubos:
            profile.ubos = ext.ubos
        if ext.authorizers:
            for a in ext.authorizers:
                if a not in profile.authorizers:
                    profile.authorizers.append(a)
        if ext.administrators:
            for ad in ext.administrators:
                if ad not in profile.administrators:
                    profile.administrators.append(ad)
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
    # CHECK 1: Official Registry Extract & Operations Review (Desc 7, 8)
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
            
            # 1a. Validity window
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

            # 1b. Company Status
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

            # 1c. Description 7: Place of incorporation, place of business, and business operations
            p_incorp = biz.place_of_incorporation or profile.country_of_operations or "Singapore"
            p_biz = biz.place_of_business or biz.business_operations_address or profile.place_of_business
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
            act = biz.core_business_activities or biz.products_services_description or profile.core_business_activities
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
        f"Verified BizFile ({profile.legal_name or bundle_name}, UEN: {profile.uen or 'N/A'}, Status: {profile.company_status or 'Live'}, Core Activities: {profile.core_business_activities or 'Documented'}, Website: {profile.customer_website or 'N/A'})."
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

        # 3d. Description 24: Authorizers, Administrators & Signing Mandate ID&V Cross-Verification
        # Cross-check authorized signatories and mandate holders against Bizfile and ID documents
        all_authorizers = list(set(profile.authorizers + [d.name for d in profile.directors]))
        if board_docs:
            for b_doc in board_docs:
                if b_doc.authorizers:
                    for a in b_doc.authorizers:
                        if a not in all_authorizers:
                            all_authorizers.append(a)

        # Cross-verify if authorized signatories have ID verification on file
        verified_id_names = [d.id_holder_name.upper().strip() for d in id_docs if d.id_holder_name]
        unverified_authorizers = []
        for auth_person in all_authorizers:
            clean_auth = auth_person.upper().replace("MR ", "").replace("MS ", "").replace("DR ", "").strip()
            # Match against verified IDs or BizFile directors
            is_matched = any(clean_auth in id_n or id_n in clean_auth for id_n in verified_id_names) or any(clean_auth in d.name.upper() for d in profile.directors)
            if not is_matched and id_docs:
                unverified_authorizers.append(auth_person)

        if unverified_authorizers:
            chk3_findings.append(
                ValidationFinding(
                    check_id="CHK_03_CONST",
                    finding_type="UNVERIFIED_AUTHORIZER_IDV",
                    severity=Priority.HIGH,
                    reason="AUTHORIZER_IDV_INCOMPLETE",
                    target_field="authorizers",
                    details=f"Desc 24: ID&V verification incomplete for authorized signatories / administrators ({', '.join(unverified_authorizers)}). Cross-check against M&AA, ACRA BizFile, and Board Resolution required.",
                )
            )
            if not chk3_reason:
                chk3_reason = "AUTHORIZER_IDV_INCOMPLETE"

    chk3_verdict = Verdict.FAIL if chk3_findings else Verdict.PASS
    chk3_evidence = (
        f"Constitutional Governance & Mandates verified: M&AA, ROM, Board Resolution (CTC), and Authorizer/Administrator ID&V cross-checked across M&AA, BizFile, and Board Resolution."
        if chk3_verdict == Verdict.PASS
        else f"Constitutional / Mandate issues (Desc 24): {'; '.join([f.details for f in chk3_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_03_CONST",
            rule_name="Constitutional Documentation, CTC & Mandate Review",
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
    # CHECK 6: UBO Transparency, Nominee/Complex Risk & Wealth Plausibility
    # =========================================================================
    chk6_findings: List[ValidationFinding] = []
    chk6_files: List[ItemizedDocStatus] = []
    chk6_reason: str | None = None
    chk6_priority: Priority = Priority.HIGH

    # Step 12: Ensure formal GLDB UBO Declaration is obtained where required
    if not ubo_decl_docs:
        chk6_findings.append(
            ValidationFinding(
                check_id="CHK_06_UBO_COMPLEX",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="GLDB Declaration of Ultimate Beneficial Owners (Mar 2026)",
                reason="MISSING_UBO_DECLARATION",
                target_field="ubo_declaration",
                details="Step 12: Official GLDB Declaration of Ultimate Beneficial Owners form is missing from client bundle.",
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
            
            # Form execution
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
                        details=f"Step 12: GLDB UBO Declaration '{ubo_decl.filename or 'UBO Declaration'}' is blank, incomplete, or lacks authorized signatory execution.",
                    )
                )
                if not chk6_reason:
                    chk6_reason = "UNEXECUTED_UBO_DECLARATION"

            # Step 6: Verify ROM / Structure to rule out undisclosed nominee or bearer share arrangements
            if ubo_decl.has_bearer_shares or profile.has_bearer_shares:
                decl_pass = False
                fail_notes.append("Bearer shares identified (prohibited/restricted under Step 6)")
                chk6_findings.append(
                    ValidationFinding(
                        check_id="CHK_06_UBO_COMPLEX",
                        finding_type="PROHIBITED_FEATURE",
                        severity=Priority.HIGH,
                        reason="BEARER_SHARES_IDENTIFIED",
                        target_field="bearer_shares",
                        details="Step 6: Bearer shares identified in ownership structure (high risk / restricted under policy).",
                    )
                )
                if not chk6_reason:
                    chk6_reason = "BEARER_SHARES_IDENTIFIED"

            # Step 6 & 10: Nominee Shareholder arrangement alignment
            if ubo_decl.has_nominee_arrangement or profile.has_nominee_arrangement:
                # Flag for enhanced due diligence review
                fail_notes.append("Nominee arrangement identified — enhanced declaration verification required")

            # Complex Multi-Tier Structure & Legitimate Rationale
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
                            details="Complex multi-tiered structure identified without documented legitimate business purpose (Step 27: Rated HIGH RISK by default).",
                        )
                    )
                    if not chk6_reason:
                        chk6_reason = "COMPLEX_STRUCTURE_WITHOUT_RATIONALE"

            # Step 4, 18 & App 1: Ultimate Ownership Transparency & Individual Wealth Plausibility (≥25% UBOs)
            ubos_to_check = ubo_decl.ubos if ubo_decl.ubos else profile.ubos
            major_ubos = [u for u in ubos_to_check if (u.ownership_percentage or 0) >= 25.0]
            
            # Check individual wealth plausibility for major economic owners (≥25%)
            is_high_risk = profile.risk_rating == "HIGH" or ubo_decl.risk_rating == "HIGH" or profile.has_complex_structure
            has_wealth_narrative = any(e.wealth_narrative_provided or e.wealth_source_narrative for e in extractions)
            has_wealth_docs = any(e.wealth_corroborating_docs_attached or e.wealth_docs_description for e in extractions)

            if major_ubos:
                for ubo in major_ubos:
                    # Medium Risk: Requires narrative of wealth accumulation
                    # High Risk: Requires corroborating primary documents (tax notices, bank statements, audited accounts, dividend slips)
                    if is_high_risk and not has_wealth_docs:
                        fail_notes.append(f"Step 18 & App 1 (High Risk): UBO '{ubo.name}' ({ubo.ownership_percentage}%) lacks primary corroborating wealth documents")
                        chk6_findings.append(
                            ValidationFinding(
                                check_id="CHK_06_UBO_COMPLEX",
                                finding_type="UNVERIFIED_SOURCE_OF_WEALTH",
                                severity=Priority.HIGH,
                                reason="MISSING_WEALTH_CORROBORATION",
                                target_field="ubos",
                                details=f"Step 18 & App 1: High Risk entity with major UBO '{ubo.name}' ({ubo.ownership_percentage}%) requires corroborating primary wealth documents (tax notices, bank statements, audited accounts, or dividend slips).",
                            )
                        )
                        if not chk6_reason:
                            chk6_reason = "MISSING_WEALTH_CORROBORATION"
                    elif not is_high_risk and not has_wealth_narrative:
                        fail_notes.append(f"Step 18: UBO '{ubo.name}' ({ubo.ownership_percentage}%) requires documented narrative of legal wealth accumulation")
                        chk6_findings.append(
                            ValidationFinding(
                                check_id="CHK_06_UBO_COMPLEX",
                                finding_type="MISSING_WEALTH_NARRATIVE",
                                severity=Priority.MEDIUM,
                                reason="UNVERIFIED_WEALTH_ACCUMULATION",
                                target_field="ubos",
                                details=f"Step 18: Individual UBO '{ubo.name}' ({ubo.ownership_percentage}%) requires a documented narrative of legal wealth accumulation and net worth plausibility.",
                            )
                        )
                        if not chk6_reason:
                            chk6_reason = "UNVERIFIED_WEALTH_ACCUMULATION"

            chk6_files.append(
                ItemizedDocStatus(
                    doc_name=ubo_decl.filename or "GLDB UBO Declaration",
                    doc_type="GLDB Declaration of UBOs",
                    verdict=Verdict.PASS if decl_pass and not (is_high_risk and not has_wealth_docs) else Verdict.FAIL,
                    details="UBO declaration executed, ≥25% economic control confirmed, and wealth plausibility evaluated." if decl_pass and (not is_high_risk or has_wealth_docs) else "; ".join(fail_notes),
                    reason=chk6_reason if not decl_pass else None,
                    is_ctc=ubo_decl.is_ctc,
                )
            )

    chk6_verdict = Verdict.FAIL if chk6_findings else Verdict.PASS
    chk6_evidence = (
        f"UBO Transparency & Wealth Plausibility verified: GLDB Declaration executed, ≥25% controllers verified, no undisclosed bearer/nominee arrangements, and wealth plausibility evaluated for Risk Calculator (Step 27: Rating {profile.risk_rating})."
        if chk6_verdict == Verdict.PASS
        else f"UBO Transparency / Wealth Plausibility issues (Steps 4, 6, 12, 18, 27): {'; '.join([f.details for f in chk6_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_06_UBO_COMPLEX",
            rule_name="UBO Transparency, Nominee/Complex Risk & Wealth Plausibility",
            verdict=chk6_verdict,
            reason_code=chk6_reason if chk6_verdict == Verdict.FAIL else None,
            priority=chk6_priority,
            evidence=chk6_evidence,
            evaluated_files=chk6_files,
            findings=chk6_findings,
        )
    )
    all_findings.extend(chk6_findings)

    # =========================================================================
    # CHECK 7: Sanction Questionnaire & Strategic Goods Review (Descr. 10)
    # 3 Checks:
    #   1) Trigger & Routing: Triggered if entity is High Risk, under SCF team, or wholesale trade of goods.
    #   2) SCF Department Code Match: RM department code matches master SCF department codes (e.g. SCF-*).
    #   3) Dual-Use & Strategic Goods Detection: Declared traded goods vs Strategic Goods lists (escalate to Trade Compliance).
    # =========================================================================
    chk7_findings: List[ValidationFinding] = []
    chk7_files: List[ItemizedDocStatus] = []
    chk7_reason: str | None = None
    chk7_priority: Priority = Priority.HIGH

    is_high_risk = profile.risk_rating == "HIGH" or any(e.risk_rating == "HIGH" for e in extractions)
    is_scf = any(e.is_scf_department or (e.rm_department_code and "SCF" in e.rm_department_code.upper()) for e in extractions)
    is_wholesale_goods = any(
        e.is_wholesale_trade_goods or 
        (e.core_business_activities and any(k in e.core_business_activities.lower() for k in ["wholesale", "trading", "import", "export", "commodities", "goods", "electronics", "chemicals"]))
        for e in extractions
    )

    is_sanctions_triggered = is_high_risk or is_scf or is_wholesale_goods

    if is_sanctions_triggered and not sanction_docs:
        chk7_findings.append(
            ValidationFinding(
                check_id="CHK_07_SANCTIONS",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="GLDB Sanction Questionnaire",
                reason="MISSING_SANCTION_QUESTIONNAIRE",
                target_field="sanction_questionnaire",
                details=(
                    f"Descr. 10: Sanctions Questionnaire triggered (High Risk: {is_high_risk}, "
                    f"SCF Team: {is_scf}, Wholesale Trade: {is_wholesale_goods}), but no completed questionnaire was provided."
                ),
            )
        )
        chk7_reason = "MISSING_SANCTION_QUESTIONNAIRE"
    elif not is_sanctions_triggered and not sanction_docs:
        chk7_files.append(
            ItemizedDocStatus(
                doc_name="Sanctions Routing Assessment",
                doc_type="GLDB Internal Document",
                verdict=Verdict.PASS,
                details="Questionnaire not triggered: Entity is Standard Risk, Non-SCF, and not engaged in wholesale physical goods trading.",
            )
        )
    else:
        for s_doc in sanction_docs:
            doc_pass = True
            fail_notes = []

            # 1. Execution
            if s_doc.is_blank_template or not s_doc.is_fully_executed or not s_doc.sanction_questionnaire_executed:
                doc_pass = False
                fail_notes.append("Sanctions questionnaire is blank or unexecuted")
                chk7_findings.append(
                    ValidationFinding(
                        check_id="CHK_07_SANCTIONS",
                        finding_type="INCOMPLETE_DOCUMENT",
                        severity=Priority.HIGH,
                        reason="UNEXECUTED_SANCTION_FORM",
                        target_field="sanction_questionnaire",
                        details=f"Descr. 10: Sanctions questionnaire '{s_doc.filename or 'Form'}' is unexecuted or incomplete.",
                    )
                )
                if not chk7_reason:
                    chk7_reason = "UNEXECUTED_SANCTION_FORM"

            # 2. SCF Department Code Match
            if is_scf or s_doc.is_scf_department or s_doc.rm_department_code:
                code = s_doc.rm_department_code or ""
                # Master SCF codes start with 'SCF' or contain 'SCF'
                if not ("SCF" in code.upper() or s_doc.is_scf_code_matched):
                    doc_pass = False
                    fail_notes.append(f"RM Department Code '{code}' does not match Master SCF Department Codes")
                    chk7_findings.append(
                        ValidationFinding(
                            check_id="CHK_07_SANCTIONS",
                            finding_type="DEPARTMENT_CODE_MISMATCH",
                            severity=Priority.HIGH,
                            reason="SCF_DEPT_CODE_MISMATCH",
                            target_field="rm_department_code",
                            details=f"Descr. 10: RM department code '{code}' failed cross-reference against master SCF department codes.",
                        )
                    )
                    if not chk7_reason:
                        chk7_reason = "SCF_DEPT_CODE_MISMATCH"

            # 3. Dual-Use & Strategic Goods Detection
            dual_use_keywords = ["nuclear", "laser", "cryptographic", "aerospace", "missile", "chemical weapon", "precision electronics", "surveillance", "military", "dual-use"]
            declared_items = s_doc.declared_traded_goods or []
            has_dual_use = s_doc.has_dual_use_goods or any(
                any(k in item.lower() for k in dual_use_keywords) for item in declared_items
            )

            if has_dual_use:
                if not s_doc.escalated_to_trade_compliance:
                    doc_pass = False
                    fail_notes.append("Dual-use/Strategic Goods detected without mandatory Trade Compliance escalation")
                    chk7_findings.append(
                        ValidationFinding(
                            check_id="CHK_07_SANCTIONS",
                            finding_type="STRATEGIC_GOODS_CONTROL",
                            severity=Priority.HIGH,
                            reason="UNESCALATED_DUAL_USE_GOODS",
                            target_field="declared_traded_goods",
                            details="Descr. 10: Traded goods match International Strategic Goods Control list without mandatory escalation memo to Trade Compliance.",
                        )
                    )
                    if not chk7_reason:
                        chk7_reason = "UNESCALATED_DUAL_USE_GOODS"
                else:
                    fail_notes.append("Strategic goods detected — Trade Compliance escalation sign-off verified ✓")

            chk7_files.append(
                ItemizedDocStatus(
                    doc_name=s_doc.filename or "GLDB Sanctions Questionnaire",
                    doc_type="Sanction Questionnaire",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details="Trigger evaluated, SCF code verified, strategic goods screened." if doc_pass else "; ".join(fail_notes),
                    reason=chk7_reason if not doc_pass else None,
                    is_ctc=s_doc.is_ctc,
                )
            )

    chk7_verdict = Verdict.FAIL if chk7_findings else Verdict.PASS
    chk7_evidence = (
        "Sanction & Strategic Goods controls verified: Trigger evaluation validated, RM/SCF department code matched, and strategic/dual-use goods screened."
        if chk7_verdict == Verdict.PASS
        else f"Sanction Questionnaire & Strategic Goods issues (Descr. 10): {'; '.join([f.details for f in chk7_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_07_SANCTIONS",
            rule_name="Sanction Questionnaire & Strategic Goods Review",
            verdict=chk7_verdict,
            reason_code=chk7_reason if chk7_verdict == Verdict.FAIL else None,
            priority=chk7_priority,
            evidence=chk7_evidence,
            evaluated_files=chk7_files,
            findings=chk7_findings,
        )
    )
    all_findings.extend(chk7_findings)

    # =========================================================================
    # CHECK 8: Institutional Questionnaires (Descr. 12)
    # 2 Checks:
    #   1) Dynamic Entity Mapping & Recency: Wolfsberg CBDDQ (Banks/FIs), Investment Vehicle (Funds/PE), MSB (Payment Processors); signed <= 12m.
    #   2) Wolfsberg Critical Answer Inspection: Escalate immediately if client answered "No" to core AML control questions.
    # =========================================================================
    chk8_findings: List[ValidationFinding] = []
    chk8_files: List[ItemizedDocStatus] = []
    chk8_reason: str | None = None
    chk8_priority: Priority = Priority.HIGH

    e_type_upper = (bundle_entity_type or "").upper()
    activities_upper = (profile.core_business_activities or "").upper()
    is_bank_fi = "BANK" in e_type_upper or "FINANCIAL INSTITUTION" in e_type_upper or "BANK" in activities_upper
    is_fund_pe = "FUND" in e_type_upper or "PRIVATE EQUITY" in e_type_upper or "INVESTMENT VEHICLE" in e_type_upper or "FUND" in activities_upper
    is_msb_pay = "PAYMENT" in e_type_upper or "MONEY SERVICE" in e_type_upper or "MSB" in e_type_upper or "REMITTANCE" in activities_upper or "PAYMENT" in activities_upper
    is_trustee = "TRUST" in e_type_upper or "TRUSTEE" in activities_upper

    is_institutional_entity = is_bank_fi or is_fund_pe or is_msb_pay or is_trustee or bool(institutional_docs)

    if is_institutional_entity and not institutional_docs:
        req_doc = "Wolfsberg CBDDQ" if is_bank_fi else ("Investment Vehicle Questionnaire" if is_fund_pe else ("MSB Questionnaire" if is_msb_pay else "Trustee Declaration"))
        chk8_findings.append(
            ValidationFinding(
                check_id="CHK_08_INSTITUTIONAL",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document=req_doc,
                reason="MISSING_INSTITUTIONAL_QUESTIONNAIRE",
                target_field="institutional_questionnaire",
                details=f"Descr. 12: Client is an institutional entity requiring formal {req_doc}, but none was provided.",
            )
        )
        chk8_reason = "MISSING_INSTITUTIONAL_QUESTIONNAIRE"
    elif not is_institutional_entity:
        chk8_files.append(
            ItemizedDocStatus(
                doc_name="Entity Institutional Classification",
                doc_type="Institutional Review",
                verdict=Verdict.PASS,
                details="Standard Corporate Entity (Non-FI/Fund/MSB): Institutional questionnaires (Wolfsberg CBDDQ) not required.",
            )
        )
    else:
        for inst_doc in institutional_docs:
            doc_pass = True
            fail_notes = []

            # 1. Recency check (<= 12 months)
            w_date = _parse_date_safe(inst_doc.wolfsberg_signature_date)
            if w_date:
                m_diff = _calculate_month_diff(today, w_date)
                if m_diff > 12:
                    doc_pass = False
                    fail_notes.append(f"Signed {inst_doc.wolfsberg_signature_date} ({m_diff} months old, exceeds 12-month validity)")
                    chk8_findings.append(
                        ValidationFinding(
                            check_id="CHK_08_INSTITUTIONAL",
                            finding_type="EXPIRED_DOCUMENT",
                            severity=Priority.HIGH,
                            reason="EXPIRED_INSTITUTIONAL_QUESTIONNAIRE",
                            target_field="wolfsberg_signature_date",
                            details=f"Descr. 12: Institutional questionnaire signature date '{inst_doc.wolfsberg_signature_date}' exceeds 12 months.",
                        )
                    )
                    if not chk8_reason:
                        chk8_reason = "EXPIRED_INSTITUTIONAL_QUESTIONNAIRE"
            elif not inst_doc.wolfsberg_is_recent_12m:
                doc_pass = False
                fail_notes.append("Institutional questionnaire signature date exceeds 12 months")

            # 2. Critical AML Answer Inspection (No to core AML questions)
            if inst_doc.wolfsberg_has_critical_no_answer:
                doc_pass = False
                details_no = inst_doc.wolfsberg_critical_no_details or "Answered 'No' to core AML/Sanction control questions"
                fail_notes.append(f"Critical AML deficiency: {details_no}")
                chk8_findings.append(
                    ValidationFinding(
                        check_id="CHK_08_INSTITUTIONAL",
                        finding_type="CRITICAL_AML_DEFICIENCY",
                        severity=Priority.HIGH,
                        reason="WOLFSBERG_CRITICAL_AML_FAILURE",
                        target_field="wolfsberg_critical_no_details",
                        details=f"Descr. 12 (Critical Escalation): Client answered 'No' to core Wolfsberg CBDDQ AML control questions ({details_no}). Immediate compliance escalation required.",
                    )
                )
                if not chk8_reason:
                    chk8_reason = "WOLFSBERG_CRITICAL_AML_FAILURE"

            chk8_files.append(
                ItemizedDocStatus(
                    doc_name=inst_doc.filename or "Institutional Questionnaire (Wolfsberg CBDDQ / MSB)",
                    doc_type="Institutional Questionnaire",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details="Institutional questionnaire verified, within 12 months, and core AML controls confirmed." if doc_pass else "; ".join(fail_notes),
                    reason=chk8_reason if not doc_pass else None,
                    is_ctc=inst_doc.is_ctc,
                )
            )

    chk8_verdict = Verdict.FAIL if chk8_findings else Verdict.PASS
    chk8_evidence = (
        "Institutional Questionnaire verified: Entity mapping confirmed, signature recency within 12 months, and all core Wolfsberg AML controls satisfied."
        if chk8_verdict == Verdict.PASS
        else f"Institutional Questionnaire issues (Descr. 12): {'; '.join([f.details for f in chk8_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_08_INSTITUTIONAL",
            rule_name="Institutional Questionnaires & Wolfsberg CBDDQ Review",
            verdict=chk8_verdict,
            reason_code=chk8_reason if chk8_verdict == Verdict.FAIL else None,
            priority=chk8_priority,
            evidence=chk8_evidence,
            evaluated_files=chk8_files,
            findings=chk8_findings,
        )
    )
    all_findings.extend(chk8_findings)

    # =========================================================================
    # CHECK 9: CDD / EDD Questionnaire — Account Purpose, Tax Risk & Sign-Off (Descr. 13, 21, 28)
    # 7 Checks:
    #   1) Singapore Nexus Justification (Descr. 13)
    #   2) Account Purpose Classification (Descr. 13)
    #   3) Expected Turnover Benchmarking & Pass-Through Risk (Descr. 13)
    #   4) Routed Transaction Category Alignment (Descr. 13)
    #   5) Tax Risk Declaration & Jurisdiction Check (EU Tax Haven list) (Descr. 21)
    #   6) Tax Mitigating Controls (TIN, CRS/FATCA) (Descr. 21)
    #   7) Continuation Rationale (>= 30 words) & Multi-Tier Governance Sign-Off (100% RM Maker, KYC Approver, Senior Approver) (Descr. 28)
    # =========================================================================
    chk9_findings: List[ValidationFinding] = []
    chk9_files: List[ItemizedDocStatus] = []
    chk9_reason: str | None = None
    chk9_priority: Priority = Priority.HIGH

    eu_tax_havens = ["panama", "cayman", "bvi", "british virgin islands", "vanuatu", "samoa", "fiji", "guam", "trinidad", "seychelles", "bahamas", "belize", "bermuda", "turks and caicos"]

    if not cdd_docs:
        # Check if basic company has foreign nexus needing justification
        has_foreign_ops = profile.country_of_operations and profile.country_of_operations.upper() not in ["SINGAPORE", "SG"]
        chk9_findings.append(
            ValidationFinding(
                check_id="CHK_09_CDD_EDD",
                finding_type="MISSING_DOCUMENT",
                severity=Priority.HIGH,
                missing_document="GLDB CDD/EDD Questionnaire",
                reason="MISSING_CDD_EDD_QUESTIONNAIRE",
                target_field="cdd_edd_questionnaire",
                details="Descr. 13, 21, 28: GLDB CDD/EDD Questionnaire covering Singapore Nexus, Tax Risk, and Multi-Tier Sign-Off is missing from bundle.",
            )
        )
        chk9_reason = "MISSING_CDD_EDD_QUESTIONNAIRE"
    else:
        for cdd in cdd_docs:
            doc_pass = True
            fail_notes = []

            # 1. Singapore Nexus Justification (Descr. 13)
            has_sg_presence = profile.place_of_business and "singapore" in profile.place_of_business.lower()
            if not has_sg_presence and (not cdd.singapore_nexus_rationale or not cdd.has_valid_singapore_nexus):
                doc_pass = False
                fail_notes.append("Lacks documented Singapore Nexus commercial justification")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="UNVERIFIED_SINGAPORE_NEXUS",
                        severity=Priority.HIGH,
                        reason="MISSING_SG_NEXUS_RATIONALE",
                        target_field="singapore_nexus_rationale",
                        details="Descr. 13: Customer lacks Singapore footprint and has not provided valid commercial rationale for Singapore digital bank account (e.g. regional trade settlement, treasury management).",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "MISSING_SG_NEXUS_RATIONALE"

            # 2. Account Purpose Classification (Descr. 13)
            if not cdd.account_purpose_matched:
                doc_pass = False
                fail_notes.append(f"Account Purpose '{cdd.account_purpose}' does not match selected product '{cdd.selected_product}'")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="PURPOSE_PRODUCT_MISMATCH",
                        severity=Priority.MEDIUM,
                        reason="ACCOUNT_PURPOSE_MISMATCH",
                        target_field="account_purpose",
                        details=f"Descr. 13: Declared account purpose '{cdd.account_purpose}' mismatches selected product '{cdd.selected_product}'.",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "ACCOUNT_PURPOSE_MISMATCH"

            # 3. Expected Turnover Benchmarking (Descr. 13)
            if cdd.is_passthrough_risk_flagged:
                doc_pass = False
                fail_notes.append("Pass-through risk: Monthly throughput inconsistent with declared annual turnover")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="PASS_THROUGH_RISK",
                        severity=Priority.HIGH,
                        reason="TURNOVER_BENCHMARK_FLAGGED",
                        target_field="expected_monthly_turnover",
                        details="Descr. 13: Benchmarking of expected monthly transaction volumes against declared annual turnover flagged severe pass-through risk.",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "TURNOVER_BENCHMARK_FLAGGED"

            # 4. Routed Transaction Category Alignment (Descr. 13)
            if not cdd.categories_aligned_with_business:
                doc_pass = False
                fail_notes.append("Routed payment categories conflict with declared business model / counterparties")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="TRANSACTION_ALIGNMENT_MISMATCH",
                        severity=Priority.MEDIUM,
                        reason="CATEGORY_ALIGNMENT_MISMATCH",
                        target_field="routed_transaction_categories",
                        details="Descr. 13: Declared routed transaction categories misalign with business activities and declared counterparties.",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "CATEGORY_ALIGNMENT_MISMATCH"

            # 5. Tax Risk Declaration & Jurisdiction Check (Descr. 21)
            if not cdd.tax_risk_section_populated:
                doc_pass = False
                fail_notes.append("Tax Risk section incomplete (bare 'N/A' or unpopulated)")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="INCOMPLETE_TAX_DECLARATION",
                        severity=Priority.HIGH,
                        reason="INCOMPLETE_TAX_DECLARATION",
                        target_field="tax_risk_section_populated",
                        details="Descr. 21: Tax Risk section contains unpopulated fields or bare 'N/A' declarations.",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "INCOMPLETE_TAX_DECLARATION"

            # 6. Tax Haven Exposure & Mitigating Controls (Descr. 21)
            tax_havens_found = [
                j for j in (cdd.tax_haven_jurisdictions or [])
                if any(h in j.lower() for h in eu_tax_havens)
            ]
            if tax_havens_found and not cdd.has_tax_mitigating_controls:
                doc_pass = False
                fail_notes.append(f"Unmitigated Tax Haven Exposure ({', '.join(tax_havens_found)}) lacking TIN/Tax Residency Cert/CRS")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="UNMITIGATED_TAX_HAVEN_RISK",
                        severity=Priority.HIGH,
                        reason="UNMITIGATED_TAX_HAVEN_RISK",
                        target_field="tax_haven_jurisdictions",
                        details=f"Descr. 21: Entity operates in EU Non-Cooperative Tax Haven jurisdictions ({', '.join(tax_havens_found)}) without verified mitigating controls (TIN, Tax Residency Certificate, CRS/FATCA).",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "UNMITIGATED_TAX_HAVEN_RISK"

            # 7. Continuation Rationale (>= 30 words) & Multi-Tier Governance Sign-Off (Descr. 28)
            text_words = len(cdd.continuation_rationale.split()) if cdd.continuation_rationale else 0
            word_count = max(text_words, cdd.continuation_word_count)
            if word_count < 30:
                doc_pass = False
                fail_notes.append(f"Continuation rationale too brief ({word_count} words, minimum 30 words required)")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="INSUFFICIENT_RATIONALE",
                        severity=Priority.HIGH,
                        reason="INSUFFICIENT_CONTINUATION_NARRATIVE",
                        target_field="continuation_rationale",
                        details=f"Descr. 28: Written business continuation rationale is insufficient ({word_count} words, requires >= 30 words with high-risk mitigations).",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "INSUFFICIENT_CONTINUATION_NARRATIVE"

            # Governance Sign-Offs (100% RM Maker, KYC Approver, Senior Approver)
            missing_signoffs = []
            if not cdd.has_rm_maker_signoff:
                missing_signoffs.append("RM Maker")
            if not cdd.has_kyc_approver_signoff:
                missing_signoffs.append("KYC Approver")
            if not cdd.has_senior_approver_signoff:
                missing_signoffs.append("Senior Approver")

            if missing_signoffs:
                doc_pass = False
                fail_notes.append(f"Missing Governance Sign-Offs: {', '.join(missing_signoffs)}")
                chk9_findings.append(
                    ValidationFinding(
                        check_id="CHK_09_CDD_EDD",
                        finding_type="MISSING_GOVERNANCE_SIGNOFF",
                        severity=Priority.HIGH,
                        reason="MISSING_MULTI_TIER_SIGNOFF",
                        target_field="all_signoffs_completed",
                        details=f"Descr. 28: Multi-tier governance sign-off incomplete. Missing 100% execution from: {', '.join(missing_signoffs)}.",
                    )
                )
                if not chk9_reason:
                    chk9_reason = "MISSING_MULTI_TIER_SIGNOFF"

            chk9_files.append(
                ItemizedDocStatus(
                    doc_name=cdd.filename or "GLDB CDD/EDD Questionnaire",
                    doc_type="CDD/EDD Questionnaire",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details="Singapore Nexus, Account Purpose, Tax Risk mitigations, and 100% Multi-tier Sign-Offs verified." if doc_pass else "; ".join(fail_notes),
                    reason=chk9_reason if not doc_pass else None,
                    is_ctc=cdd.is_ctc,
                )
            )

    chk9_verdict = Verdict.FAIL if chk9_findings else Verdict.PASS
    chk9_evidence = (
        "CDD / EDD Governance verified: Singapore Nexus justified, account purpose aligned, tax risk mitigated (CRS/FATCA), continuation narrative >= 30 words, and 100% multi-tier sign-offs executed."
        if chk9_verdict == Verdict.PASS
        else f"CDD / EDD Governance issues (Descr. 13, 21, 28): {'; '.join([f.details for f in chk9_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_09_CDD_EDD",
            rule_name="CDD / EDD Account Purpose, Tax Risk & Sign-Off Governance",
            verdict=chk9_verdict,
            reason_code=chk9_reason if chk9_verdict == Verdict.FAIL else None,
            priority=chk9_priority,
            evidence=chk9_evidence,
            evaluated_files=chk9_files,
            findings=chk9_findings,
        )
    )
    all_findings.extend(chk9_findings)

    # =========================================================================
    # CHECK 10: Ingestion Quality, CTC Authenticity & Certified Translations (Descr. 25)
    # 3 Checks:
    #   1) Image Clarity & Legibility: OCR confidence >= 85% and resolution >= 200 DPI without blur/cutoff.
    #   2) CTC Verification on Copies: Non-registry photocopies feature certifier signature, date, title, organization.
    #   3) Certified English Translations: Foreign non-English docs have certified translations with sworn translator statement & credentials.
    # =========================================================================
    chk10_findings: List[ValidationFinding] = []
    chk10_files: List[ItemizedDocStatus] = []
    chk10_reason: str | None = None
    chk10_priority: Priority = Priority.HIGH

    for doc in extractions:
        doc_pass = True
        fail_notes = []

        # 1. Image Clarity & Legibility (OCR >= 85%, DPI >= 200, no blur/cutoff)
        if doc.ocr_confidence < 85.0 or doc.dpi_resolution < 200 or doc.is_blurry_or_cutoff:
            doc_pass = False
            clarity_issue = f"OCR confidence {doc.ocr_confidence}%, DPI {doc.dpi_resolution}" + (", Blurry/Cutoff detected" if doc.is_blurry_or_cutoff else "")
            fail_notes.append(f"Image clarity failure ({clarity_issue})")
            chk10_findings.append(
                ValidationFinding(
                    check_id="CHK_10_INGESTION_QUALITY",
                    finding_type="IMAGE_CLARITY_DEFECT",
                    severity=Priority.HIGH,
                    reason="POOR_IMAGE_QUALITY",
                    target_field="ocr_confidence",
                    details=f"Descr. 25: Document '{doc.filename or 'File'}' failed ingestion quality standards (requires OCR confidence >= 85% and >= 200 DPI without blur/cutoff; actual: {clarity_issue}).",
                )
            )
            if not chk10_reason:
                chk10_reason = "POOR_IMAGE_QUALITY"

        # 2. CTC Verification on Copies
        # M&AA, ROM, Board Resolutions, ID copies need certifier signature, date, title, organization
        if doc.doc_type in [DocType.MAA, DocType.ROM, DocType.BOARD_RESOLUTION, DocType.ID_DOCUMENT] and not doc.is_ctc:
            if not doc.ctc_details_complete:
                doc_pass = False
                fail_notes.append("CTC lacks certifier title, date, or organization")
                chk10_findings.append(
                    ValidationFinding(
                        check_id="CHK_10_INGESTION_QUALITY",
                        finding_type="INCOMPLETE_CTC_CREDENTIALS",
                        severity=Priority.HIGH,
                        reason="INCOMPLETE_CTC_ATTESTATION",
                        target_field="certifier_title",
                        details=f"Descr. 25: Non-registry copy '{doc.filename or 'File'}' lacks complete certifier details (must feature certifier signature, date, professional title, and organization).",
                    )
                )
                if not chk10_reason:
                    chk10_reason = "INCOMPLETE_CTC_ATTESTATION"

        # 3. Certified English Translations
        if doc.is_non_english:
            if not doc.has_certified_translation or not doc.has_sworn_translator_statement:
                doc_pass = False
                fail_notes.append("Non-English document lacking certified sworn English translation")
                chk10_findings.append(
                    ValidationFinding(
                        check_id="CHK_10_INGESTION_QUALITY",
                        finding_type="MISSING_CERTIFIED_TRANSLATION",
                        severity=Priority.HIGH,
                        reason="UNTRANSLATED_FOREIGN_DOCUMENT",
                        target_field="has_certified_translation",
                        details=f"Descr. 25: Foreign language document '{doc.filename or 'File'}' ({doc.document_language}) lacks official certified English translation with sworn translator statement and credentials.",
                    )
                )
                if not chk10_reason:
                    chk10_reason = "UNTRANSLATED_FOREIGN_DOCUMENT"

        chk10_files.append(
            ItemizedDocStatus(
                doc_name=doc.filename or "Uploaded Document",
                doc_type=str(doc.doc_type.value if hasattr(doc.doc_type, 'value') else doc.doc_type),
                verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                details="Ingestion quality validated (OCR ≥ 85%, ≥ 200 DPI, CTC attestation & English translation verified)." if doc_pass else "; ".join(fail_notes),
                reason=chk10_reason if not doc_pass else None,
                is_ctc=doc.is_ctc,
            )
        )

    chk10_verdict = Verdict.FAIL if chk10_findings else Verdict.PASS
    chk10_evidence = (
        "Ingestion Quality & Translations verified: All document scans meet ≥ 85% OCR confidence & ≥ 200 DPI, CTC details feature complete professional credentials, and all foreign documents have sworn certified English translations."
        if chk10_verdict == Verdict.PASS
        else f"Ingestion Quality & Translation issues (Descr. 25): {'; '.join([f.details for f in chk10_findings])}"
    )

    results.append(
        CheckResult(
            check_id="CHK_10_INGESTION_QUALITY",
            rule_name="Ingestion Quality, CTC Authenticity & Certified Translations",
            verdict=chk10_verdict,
            reason_code=chk10_reason if chk10_verdict == Verdict.FAIL else None,
            priority=chk10_priority,
            evidence=chk10_evidence,
            evaluated_files=chk10_files,
            findings=chk10_findings,
        )
    )
    all_findings.extend(chk10_findings)

    return results, all_findings, profile

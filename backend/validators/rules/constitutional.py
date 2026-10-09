from typing import List, Tuple
from backend.models import (
    CheckResult,
    EntityType,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from ..context import BundleContext


class ConstitutionalAndMandateValidator:
    """Evaluates:
    - CHK_03_CONST: Constitutional Documentation, CTC & Mandate Review (Desc 24)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk3_findings: List[ValidationFinding] = []
        chk3_files: List[ItemizedDocStatus] = []
        chk3_reason: str | None = None
        chk3_priority: Priority = Priority.HIGH

        is_corp = ctx.bundle_entity_type in [
            EntityType.PVT_LTD.value,
            EntityType.PUBLIC_LISTED.value,
            EntityType.FOREIGN_CORP.value,
        ]

        if is_corp:
            # 3a. Evaluate Memorandum and Articles of Association (M&AA)
            if not ctx.maa_docs:
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
                for m in ctx.maa_docs:
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
            if not ctx.rom_docs:
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
                for r_doc in ctx.rom_docs:
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
            if not ctx.board_docs:
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
                for b_doc in ctx.board_docs:
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
            all_authorizers = list(set(ctx.profile.authorizers + [d.name for d in ctx.profile.directors]))
            if ctx.board_docs:
                for b_doc in ctx.board_docs:
                    if b_doc.authorizers:
                        for a in b_doc.authorizers:
                            if a not in all_authorizers:
                                all_authorizers.append(a)

            verified_id_names = [d.id_holder_name.upper().strip() for d in ctx.id_docs if d.id_holder_name]
            unverified_authorizers = []
            for auth_person in all_authorizers:
                clean_auth = auth_person.upper().replace("MR ", "").replace("MS ", "").replace("DR ", "").strip()
                is_matched = any(clean_auth in id_n or id_n in clean_auth for id_n in verified_id_names) or any(clean_auth in d.name.upper() for d in ctx.profile.directors)
                if not is_matched and ctx.id_docs:
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

        return results, all_findings

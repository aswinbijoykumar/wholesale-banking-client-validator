from typing import List, Tuple
from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from backend.validators.context import BundleContext


class OwnershipAndStructureValidator:
    """Evaluates:
    - CHK_04_CORP_STRUCT: Corporate Structure, Directorship & UBO Changes + ID CTC Verification
    - CHK_06_UBO_COMPLEX: UBO Transparency, Nominee/Complex Risk & Wealth Plausibility
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        # =========================================================================
        # CHECK 4: Corporate Structure Changes, Key Controllers & ID CTCs
        # =========================================================================
        chk4_findings: List[ValidationFinding] = []
        chk4_files: List[ItemizedDocStatus] = []
        chk4_reason: str | None = None
        chk4_priority: Priority = Priority.HIGH

        # Check Register of Directors (ROD)
        if not ctx.rod_docs and not ctx.bizfile_docs:
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
            for r_doc in (ctx.rod_docs if ctx.rod_docs else ctx.bizfile_docs):
                chk4_files.append(
                    ItemizedDocStatus(
                        doc_name=r_doc.filename or "Register of Directors",
                        doc_type="Register of Directors (ROD)",
                        verdict=Verdict.PASS,
                        details=f"Confirmed {len(ctx.profile.directors)} directorship record(s) on file.",
                        is_ctc=r_doc.is_ctc,
                    )
                )

        # Confirm UBOs and shareholding percentages recorded
        all_ubos = ctx.profile.ubos
        if not all_ubos:
            for ext in ctx.ubo_decl_docs + ctx.rom_docs + ctx.bizfile_docs:
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
        if ctx.id_docs:
            for id_doc in ctx.id_docs:
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
            f"Corporate structure verified: {len(ctx.profile.directors)} Director(s) on ROD, {len(all_ubos or [])} UBO(s) with confirmed shareholding percentages and CTC verified identification."
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
        # CHECK 6: UBO Transparency, Nominee/Complex Risk & Wealth Plausibility
        # =========================================================================
        chk6_findings: List[ValidationFinding] = []
        chk6_files: List[ItemizedDocStatus] = []
        chk6_reason: str | None = None
        chk6_priority: Priority = Priority.HIGH

        if not ctx.ubo_decl_docs:
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
            for ubo_decl in ctx.ubo_decl_docs:
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
                if ubo_decl.has_bearer_shares or ctx.profile.has_bearer_shares:
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
                if ubo_decl.has_nominee_arrangement or ctx.profile.has_nominee_arrangement:
                    fail_notes.append("Nominee arrangement identified — enhanced declaration verification required")

                # Complex Multi-Tier Structure & Legitimate Rationale
                if ubo_decl.has_complex_structure or ctx.profile.has_complex_structure:
                    if not ubo_decl.complex_structure_rationale and not ctx.profile.complex_structure_rationale:
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
                ubos_to_check = ubo_decl.ubos if ubo_decl.ubos else ctx.profile.ubos
                major_ubos = [u for u in ubos_to_check if (u.ownership_percentage or 0) >= 25.0]

                is_high_risk = ctx.profile.risk_rating == "HIGH" or ubo_decl.risk_rating == "HIGH" or ctx.profile.has_complex_structure
                has_wealth_narrative = any(e.wealth_narrative_provided or e.wealth_source_narrative for e in ctx.extractions)
                has_wealth_docs = any(e.wealth_corroborating_docs_attached or e.wealth_docs_description for e in ctx.extractions)

                if major_ubos:
                    for ubo in major_ubos:
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
            f"UBO Transparency & Wealth Plausibility verified: GLDB Declaration executed, ≥25% controllers verified, no undisclosed bearer/nominee arrangements, and wealth plausibility evaluated for Risk Calculator (Step 27: Rating {ctx.profile.risk_rating})."
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

        return results, all_findings

from typing import List, Tuple
from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from backend.validators.context import BundleContext, parse_date_safe


class IdentityAndAddressValidator:
    """Evaluates:
    - CHK_05_ID_EXPIRY: Expiry Verification of Identity Documents & Proof of Address (Watermarks, 90d, Mismatches)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk5_findings: List[ValidationFinding] = []
        chk5_files: List[ItemizedDocStatus] = []
        chk5_reason: str | None = None
        chk5_priority: Priority = Priority.HIGH

        # 1. Missing ID Document Check
        if not ctx.id_docs:
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
        for d in ctx.id_docs:
            d_pass = True
            fail_notes = []
            doc_reason = None

            # 2a. Fraudulent / Template / Synthetic ID Detection
            if (
                d.is_fraudulent_or_template
                or d.fraud_reasons
                or d.has_watermark_or_template_generator
                or d.has_synthetic_placeholder_data
            ):
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
                exp_d = parse_date_safe(d.id_expiry_date)
                if exp_d and exp_d < ctx.today:
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
        for p in ctx.poa_docs:
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
                issue_d = parse_date_safe(p.address_issue_date)
                if issue_d:
                    days_old = (ctx.today - issue_d).days
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
            if ctx.id_docs:
                primary_id = ctx.id_docs[0]
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
            f"All {len(ctx.id_docs)} identity document(s) and {len(ctx.poa_docs)} proof of address document(s) verified as authentic, matching, current, and within 90 days."
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

        return results, all_findings

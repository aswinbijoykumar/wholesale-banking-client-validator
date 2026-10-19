from typing import List, Tuple
from backend.models import (
    CheckResult,
    DocType,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from backend.validators.context import BundleContext


class IngestionQualityValidator:
    """Evaluates:
    - CHK_10_INGESTION_QUALITY: Ingestion Quality, CTC Authenticity & Certified Translations (Descr. 25)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk10_findings: List[ValidationFinding] = []
        chk10_files: List[ItemizedDocStatus] = []
        chk10_reason: str | None = None
        chk10_priority: Priority = Priority.HIGH

        for doc in ctx.extractions:
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
                    doc_type=str(doc.doc_type.value if hasattr(doc.doc_type, "value") else doc.doc_type),
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

        return results, all_findings

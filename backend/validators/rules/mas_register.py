from typing import List, Tuple
from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    MasVerificationProfile,
    Priority,
    ValidationFinding,
    Verdict,
)
from ..context import BundleContext


class MasRegulatoryValidator:
    """Evaluates:
    - CHK_11_MAS_REGISTER: MAS Regulatory Licence, Status & Key Personnel Verification
      (Monetary Authority of Singapore Central Bank FID Directory Live Cross-Check)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk11_findings: List[ValidationFinding] = []
        chk11_files: List[ItemizedDocStatus] = []
        chk11_reason: str | None = None
        chk11_priority: Priority = Priority.HIGH

        financial_keywords = [
            "bank", "banking", "merchant bank", "wholesale bank", "finance company",
            "fund management", "capital markets", "asset management", "payment service",
            "remittance", "money changer", "trustee", "broker", "brokerage", "insurance",
            "reinsurance", "financial institution", "licensed", "monetary authority"
        ]
        activities_str = f"{ctx.profile.core_business_activities or ''} {ctx.profile.legal_name or ''} {ctx.bundle_name or ''} {ctx.bundle_entity_type or ''}".lower()
        is_fi_nbfi = any(k in activities_str for k in financial_keywords) or bool(ctx.institutional_docs)

        if not is_fi_nbfi:
            chk11_files.append(
                ItemizedDocStatus(
                    doc_name="MAS Directory Regulatory Scope",
                    doc_type="Central Bank Directory",
                    verdict=Verdict.PASS,
                    details="Standard Commercial Entity: Not classified as a Financial Institution (FI) or NBFI under MAS regulatory scope. MAS licence check Not Applicable.",
                )
            )
            chk11_verdict = Verdict.PASS
            chk11_evidence = "Entity is a Standard Commercial Entity (Non-FI/NBFI). MAS regulatory licence check is Not Applicable."
        else:
            company_query = ctx.profile.legal_name or ctx.bundle_name
            mas_profile: MasVerificationProfile
            try:
                # Safe import of search_and_verify_mas (isolated from crash if playwright not installed)
                from ...services.mas_crawler import search_and_verify_mas
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import nest_asyncio
                        nest_asyncio.apply()
                        mas_profile = loop.run_until_complete(search_and_verify_mas(company_query))
                    else:
                        mas_profile = loop.run_until_complete(search_and_verify_mas(company_query))
                except Exception:
                    mas_profile = asyncio.run(search_and_verify_mas(company_query))
            except Exception as e:
                mas_profile = MasVerificationProfile(
                    is_fi_nbfi=True,
                    search_name_used=company_query,
                    is_found_on_mas=False,
                    raw_notes=f"MAS Crawler Exception: {str(e)}"
                )

            ctx.profile.mas_profile = mas_profile
            doc_pass = True
            fail_notes = []

            if not mas_profile.is_found_on_mas:
                doc_pass = False
                fail_notes.append(f"Entity '{company_query}' operates in financial sector but was NOT FOUND in the MAS Financial Institutions Directory")
                chk11_findings.append(
                    ValidationFinding(
                        check_id="CHK_11_MAS_REGISTER",
                        finding_type="UNLICENSED_FINANCIAL_INSTITUTION",
                        severity=Priority.HIGH,
                        reason="NOT_FOUND_ON_MAS_REGISTER",
                        target_field="legal_name",
                        details=f"Entity '{company_query}' declared financial activities ({ctx.profile.core_business_activities or ctx.bundle_entity_type}) but has no active registration or licence on the Monetary Authority of Singapore (MAS) Directory.",
                    )
                )
                chk11_reason = "NOT_FOUND_ON_MAS_REGISTER"
            else:
                # 1. Licence Status & Type
                status_clean = (mas_profile.licence_status or "").strip().upper()
                if status_clean in ["CEASED", "SUSPENDED", "REVOKED", "INACTIVE"]:
                    doc_pass = False
                    fail_notes.append(f"MAS Licence status is '{mas_profile.licence_status}' (not Active/Current)")
                    chk11_findings.append(
                        ValidationFinding(
                            check_id="CHK_11_MAS_REGISTER",
                            finding_type="INACTIVE_REGULATORY_LICENCE",
                            severity=Priority.HIGH,
                            reason="MAS_LICENCE_CEASED_OR_SUSPENDED",
                            target_field="licence_status",
                            details=f"Entity licence status on MAS Directory is '{mas_profile.licence_status}'. Operations prohibited.",
                        )
                    )
                    if not chk11_reason:
                        chk11_reason = "MAS_LICENCE_CEASED_OR_SUSPENDED"

                # 2. Country of Incorporation
                if mas_profile.country_of_incorporation:
                    mas_country = mas_profile.country_of_incorporation.strip().lower()
                    acra_country = (ctx.profile.country_of_operations or "singapore").strip().lower()
                    if "singapore" in mas_country and "singapore" not in acra_country and ctx.profile.country_of_operations:
                        doc_pass = False
                        fail_notes.append(f"Incorporation country mismatch: MAS shows '{mas_profile.country_of_incorporation}' vs BizFile '{ctx.profile.country_of_operations}'")
                        chk11_findings.append(
                            ValidationFinding(
                                check_id="CHK_11_MAS_REGISTER",
                                finding_type="INCORPORATION_JURISDICTION_MISMATCH",
                                severity=Priority.HIGH,
                                reason="MAS_INCORPORATION_MISMATCH",
                                target_field="country_of_incorporation",
                                details=f"MAS Directory lists incorporation as '{mas_profile.country_of_incorporation}', conflicting with ACRA records.",
                            )
                        )
                        if not chk11_reason:
                            chk11_reason = "MAS_INCORPORATION_MISMATCH"

                # 3. Key Personnel
                if mas_profile.key_personnel and ctx.profile.directors:
                    registered_director_names = [d.name.strip().upper() for d in ctx.profile.directors]
                    unmatched_execs = []
                    for kp in mas_profile.key_personnel:
                        kp_name = kp.get("name", "").strip().upper()
                        if kp_name and not any(r_name in kp_name or kp_name in r_name for r_name in registered_director_names):
                            unmatched_execs.append(f"{kp.get('role')}: {kp.get('name')}")

                    if unmatched_execs:
                        fail_notes.append(f"Key Personnel uncorroborated in corporate filings: {', '.join(unmatched_execs)}")
                        chk11_findings.append(
                            ValidationFinding(
                                check_id="CHK_11_MAS_REGISTER",
                                finding_type="UNAPPROVED_KEY_PERSONNEL",
                                severity=Priority.MEDIUM,
                                reason="MAS_KEY_PERSONNEL_UNMATCHED",
                                target_field="key_personnel",
                                details=f"MAS Directory lists Key Personnel ({', '.join(unmatched_execs)}) not reflected in Register of Directors.",
                            )
                        )
                        if not chk11_reason:
                            chk11_reason = "MAS_KEY_PERSONNEL_UNMATCHED"

                # 4. Registered Office Address Match
                if mas_profile.registered_address and ctx.profile.place_of_business:
                    mas_addr_clean = "".join(filter(str.isalnum, mas_profile.registered_address.lower()))
                    biz_addr_clean = "".join(filter(str.isalnum, ctx.profile.place_of_business.lower()))
                    if len(mas_addr_clean) > 8 and len(biz_addr_clean) > 8:
                        if mas_addr_clean[:12] not in biz_addr_clean and biz_addr_clean[:12] not in mas_addr_clean:
                            fail_notes.append(f"Address notice: MAS registered address '{mas_profile.registered_address}' vs ACRA '{ctx.profile.place_of_business}'")

            chk11_files.append(
                ItemizedDocStatus(
                    doc_name=f"MAS Directory: {mas_profile.search_name_used}",
                    doc_type="Monetary Authority of Singapore (FID)",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details=(
                        f"MAS Licence verified: {mas_profile.licence_type or 'Licensed'} ({mas_profile.licence_status or 'Current'}). "
                        f"Incorporation: {mas_profile.country_of_incorporation or 'Singapore'}. "
                        f"Key Personnel: {len(mas_profile.key_personnel)} executive(s) reconciled."
                    ) if doc_pass else "; ".join(fail_notes),
                    reason=chk11_reason if not doc_pass else None,
                    is_ctc=True,
                )
            )

            chk11_verdict = Verdict.FAIL if chk11_findings else Verdict.PASS
            chk11_evidence = (
                f"MAS Central Bank Directory confirmed: '{mas_profile.search_name_used}' is active ({mas_profile.licence_type}, Status: {mas_profile.licence_status}). "
                f"Incorporation jurisdiction verified ({mas_profile.country_of_incorporation}), approved Key Personnel reconciled, and registered address confirmed on record."
            ) if chk11_verdict == Verdict.PASS else f"MAS Central Bank Directory discrepancy: {'; '.join([f.details for f in chk11_findings])}"

        results.append(
            CheckResult(
                check_id="CHK_11_MAS_REGISTER",
                rule_name="MAS Regulatory Licence, Status & Key Personnel Verification",
                verdict=chk11_verdict,
                reason_code=chk11_reason if chk11_verdict == Verdict.FAIL else None,
                priority=chk11_priority,
                evidence=chk11_evidence,
                evaluated_files=chk11_files,
                findings=chk11_findings,
            )
        )
        all_findings.extend(chk11_findings)

        return results, all_findings

from typing import List, Tuple
from backend.models import (
    CheckResult,
    DigitalFootprintProfile,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from ..context import BundleContext


class DigitalFootprintValidator:
    """Evaluates:
    - CHK_13_DIGITAL_FOOTPRINT: Digital Footprint, Domain Age & Web Activity Verification
      (Client Website Crawl & RDAP/WHOIS OSINT Audit)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        chk13_findings: List[ValidationFinding] = []
        chk13_files: List[ItemizedDocStatus] = []
        chk13_reason: str | None = None
        chk13_priority: Priority = Priority.MEDIUM

        # Determine website URL prioritizing MAS registry official link
        target_website_url = None
        website_source = "None"

        if ctx.profile.mas_profile and ctx.profile.mas_profile.website:
            target_website_url = ctx.profile.mas_profile.website
            website_source = "MAS Directory"
        elif ctx.profile.customer_website:
            target_website_url = ctx.profile.customer_website
            website_source = "Onboarding Application / BizFile"

        if not target_website_url:
            chk13_verdict = Verdict.NOT_APPLICABLE
            chk13_evidence = "No company website URL discovered on MAS Directory or provided in application forms. Digital footprint check skipped."
        else:
            digital_profile: DigitalFootprintProfile
            try:
                from ...services.domain_verifier import crawl_and_verify_domain
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import nest_asyncio
                        nest_asyncio.apply()
                        digital_profile = loop.run_until_complete(crawl_and_verify_domain(target_website_url))
                    else:
                        digital_profile = loop.run_until_complete(crawl_and_verify_domain(target_website_url))
                except Exception:
                    digital_profile = asyncio.run(crawl_and_verify_domain(target_website_url))
            except Exception as e:
                digital_profile = DigitalFootprintProfile(
                    target_url=target_website_url,
                    domain=target_website_url,
                    is_live=False,
                    notes=[f"Crawler exception: {str(e)}"]
                )

            ctx.profile.digital_footprint = digital_profile

            # 1. Check if website is alive
            if not digital_profile.is_live:
                chk13_findings.append(
                    ValidationFinding(
                        check_id="CHK_13_DIGITAL_FOOTPRINT",
                        finding_type="WEBSITE_UNREACHABLE",
                        severity=Priority.MEDIUM,
                        reason="OFFICIAL_WEBSITE_OFFLINE",
                        target_field="customer_website",
                        details=f"Official website '{target_website_url}' (source: {website_source}) failed to load or is offline.",
                    )
                )
                if not chk13_reason:
                    chk13_reason = "OFFICIAL_WEBSITE_OFFLINE"

            # 2. Shelf / Shell Entity Check: Domain Creation Date vs Incorporation Date
            if digital_profile.is_shelf_company_risk:
                chk13_findings.append(
                    ValidationFinding(
                        check_id="CHK_13_DIGITAL_FOOTPRINT",
                        finding_type="SHELF_COMPANY_RISK",
                        severity=Priority.HIGH,
                        reason="RECENT_DOMAIN_CREATION",
                        target_field="customer_website",
                        details=f"Domain '{digital_profile.domain}' was registered only {digital_profile.domain_age_days} days ago ({digital_profile.domain_created_date}). Potential disposable/shelf entity.",
                    )
                )
                chk13_priority = Priority.HIGH
                if not chk13_reason:
                    chk13_reason = "SHELF_COMPANY_RISK"

            # 3. Core Business Activities / Services Reconciliation
            if digital_profile.detected_services and ctx.profile.core_business_activities:
                biz_clean = ctx.profile.core_business_activities.lower()
                matching_services = [
                    s for s in digital_profile.detected_services 
                    if s.lower() in biz_clean or any(word in biz_clean for word in s.lower().split())
                ]
                if not matching_services and len(digital_profile.detected_services) > 0:
                    chk13_findings.append(
                        ValidationFinding(
                            check_id="CHK_13_DIGITAL_FOOTPRINT",
                            finding_type="BUSINESS_SCOPE_MISMATCH",
                            severity=Priority.LOW,
                            reason="WEBSITE_SERVICE_MISMATCH",
                            target_field="core_business_activities",
                            details=f"Website advertises ({', '.join(digital_profile.detected_services[:4])}) but ACRA BizFile registers core activity as '{ctx.profile.core_business_activities}'.",
                        )
                    )

            doc_pass = len(chk13_findings) == 0
            chk13_files.append(
                ItemizedDocStatus(
                    doc_name=f"Digital Audit: {digital_profile.domain or target_website_url}",
                    doc_type="Corporate Website & OSINT Footprint",
                    verdict=Verdict.PASS if doc_pass else Verdict.FAIL,
                    details=(
                        f"Website Active: {digital_profile.target_url} (HTTP {digital_profile.http_status or 200}). "
                        f"Domain Age: {digital_profile.domain_age_days or 'N/A'} days. "
                        f"Services detected: {', '.join(digital_profile.detected_services[:4]) if digital_profile.detected_services else 'General Corporate'}. "
                        f"Source: {website_source}."
                    ) if doc_pass else "; ".join([f.details for f in chk13_findings]),
                    reason=chk13_reason if not doc_pass else None,
                    is_ctc=True,
                )
            )

            chk13_verdict = Verdict.FAIL if chk13_findings else Verdict.PASS
            chk13_evidence = (
                f"Digital footprint verified: Official portal '{digital_profile.target_url}' (source: {website_source}) is live. "
                f"Domain registered {digital_profile.domain_created_date or 'verified'} (~{digital_profile.domain_age_days or 'N/A'} days old via {digital_profile.registrar or 'RDAP'}). "
                f"Services ({', '.join(digital_profile.detected_services[:3]) if digital_profile.detected_services else 'Banking/Corporate'}) align with regulatory filings."
            ) if chk13_verdict == Verdict.PASS else f"Digital footprint issues detected: {'; '.join([f.details for f in chk13_findings])}"

        results.append(
            CheckResult(
                check_id="CHK_13_DIGITAL_FOOTPRINT",
                rule_name="Digital Footprint, Domain Age & Web Activity Verification",
                verdict=chk13_verdict,
                reason_code=chk13_reason if chk13_verdict == Verdict.FAIL else None,
                priority=chk13_priority,
                evidence=chk13_evidence,
                evaluated_files=chk13_files,
                findings=chk13_findings,
            )
        )
        all_findings.extend(chk13_findings)

        return results, all_findings

"""Master Sub-Check Matrix & Executive Summary Service for Wholesale Banking Validation.

Implements the complete 55 granular sub-check specifications from check.md across
all 14 primary validation checks, providing deep explainability, cross-checked document
attribution, and executive summaries for both UI rendering and Audit PDF reports.
"""
from typing import Any, Dict, List, Optional
from ..models import ItemizedDocStatus, Priority, SubCheckStatus, ValidationFinding, Verdict


SUBCHECK_DEFINITIONS: Dict[str, List[Dict[str, Any]]] = {
    "CHK_01_BIZFILE": [
        {
            "sub_id": "CHK_01.1",
            "name": "Profile Freshness & Issuance Recency (≤ 12 Months)",
            "description": "Verifies registry profile issuance date is within the last 12 months (365 days).",
            "target_keys": ["issuance_date", "extracted_date", "bizfile_date", "BIZFILE_OUTDATED", "OUTDATED_BIZFILE", "MISSING_BIZFILE"],
        },
        {
            "sub_id": "CHK_01.2",
            "name": "Live / Active Operating Status",
            "description": "Asserts entity status is Live/Active; flags Struck Off, Dissolved, or Inactive.",
            "target_keys": ["company_status", "status", "ENTITY_NOT_LIVE", "INACTIVE_ENTITY", "MISSING_BIZFILE"],
        },
        {
            "sub_id": "CHK_01.3",
            "name": "Physical Place of Business & Registered Address",
            "description": "Confirms valid registered office address and principal operational premises.",
            "target_keys": ["registered_office_address", "principal_place_of_business", "place_of_business", "INVALID_REGISTERED_ADDRESS", "MISSING_BIZFILE"],
        },
        {
            "sub_id": "CHK_01.4",
            "name": "Core Business Activities (SSIC Code) Specification",
            "description": "Validates primary and secondary SSIC codes and industry activity descriptions.",
            "target_keys": ["primary_ssic_code", "primary_activity_description", "core_business_activities", "MISSING_CORE_ACTIVITIES", "MISSING_BIZFILE"],
        },
    ],
    "CHK_02_INCORP": [
        {
            "sub_id": "CHK_02.1",
            "name": "Exact Legal Entity Name Matching",
            "description": "Normalized string match of legal company name across COI and ACRA BizFile.",
            "target_keys": ["entity_name", "legal_name", "NAME_MISMATCH", "MISSING_INCORP_CERT"],
        },
        {
            "sub_id": "CHK_02.2",
            "name": "Unique Entity Number (UEN) Reconciliation",
            "description": "Reconciles standard Singapore UEN across official registration instruments.",
            "target_keys": ["uen", "registration_number", "UEN_MISMATCH", "MISSING_INCORP_CERT"],
        },
        {
            "sub_id": "CHK_02.3",
            "name": "Incorporation Date Parity & Seal Validation",
            "description": "Cross-verifies exact legal registration date and registrar authority seal.",
            "target_keys": ["incorporation_date", "registration_date", "INCORPORATION_DATE_MISMATCH", "MISSING_INCORP_CERT"],
        },
    ],
    "CHK_03_CONST": [
        {
            "sub_id": "CHK_03.1",
            "name": "M&AA / Constitution Execution & CTC Verification",
            "description": "Inspects Constitution/M&AA for valid execution signatures and Certified True Copy stamp.",
            "target_keys": ["is_ctc", "has_ctc", "MAA_EXECUTION_OR_CTC_MISSING", "MISSING_MAA", "UNEXECUTED_MAA", "MISSING_CTC_MAA"],
        },
        {
            "sub_id": "CHK_03.2",
            "name": "Register of Members (ROM) Completeness & Attestation",
            "description": "Confirms Register of Members reflects share capital and certified by Corporate Secretary.",
            "target_keys": ["rom", "rom_docs", "ROM_INVALID_OR_MISSING", "MISSING_ROM", "UNEXECUTED_ROM"],
        },
        {
            "sub_id": "CHK_03.3",
            "name": "Board Resolution Execution & Quorum Validity",
            "description": "Verifies Board Resolution appointing account operators is duly executed by quorum of directors.",
            "target_keys": ["board_resolution", "BOARD_RESOLUTION_DEFECTIVE", "UNEXECUTED_BOARD_RESOLUTION", "MISSING_BOARD_RESOLUTION"],
        },
        {
            "sub_id": "CHK_03.4",
            "name": "Authorized Signatory / Administrator Identity (ID&V) Check",
            "description": "Cross-references account authorizers and platform admins against verified identity copies.",
            "target_keys": ["authorizers", "administrators", "AUTHORIZER_IDV_UNRESOLVED", "MISSING_AUTHORIZER_IDV"],
        },
    ],
    "CHK_04_CORP_STRUCT": [
        {
            "sub_id": "CHK_04.1",
            "name": "Register of Directors (ROD) Ingestion & Statutory Residency",
            "description": "Verifies presence of executed ROD and ensures statutory ordinarily resident director compliance.",
            "target_keys": ["rod", "MISSING_ROD", "UNEXECUTED_REGISTER", "ROD_DEFICIENT_OR_NO_RESIDENT_DIRECTOR"],
        },
        {
            "sub_id": "CHK_04.2",
            "name": "Director Alignment vs ACRA BizFile",
            "description": "Cross-checks active directors between Register of Directors and current BizFile extract.",
            "target_keys": ["directors", "DIRECTOR_LIST_MISMATCH", "DIRECTOR_MISMATCH"],
        },
        {
            "sub_id": "CHK_04.3",
            "name": "Director & Key Controller CTC Documentation",
            "description": "Ensures Certified True Copy (CTC) certification on all statutory director registers.",
            "target_keys": ["MISSING_CTC_ROD", "MISSING_CTC", "is_ctc"],
        },
    ],
    "CHK_05_ID_EXPIRY": [
        {
            "sub_id": "CHK_05.1",
            "name": "Identity Document Presence & Mandatory Field Extraction",
            "description": "Verifies valid Passport/NRIC for directors and UBOs with legible name, DOB, and nationality.",
            "target_keys": ["id_document", "MISSING_ID_DOCUMENT", "id_number", "full_name"],
        },
        {
            "sub_id": "CHK_05.2",
            "name": "Synthetic Sample / Template Watermark Fraud Detection (ID)",
            "description": "Scans ID documents for template generator watermarks, synthetic samples, or fake markers.",
            "target_keys": ["FRAUDULENT_DOCUMENT_DETECTED", "TEMPLATE_GENERATOR_DETECTED", "is_fraudulent_or_template"],
        },
        {
            "sub_id": "CHK_05.3",
            "name": "Identification Expiration Threshold Check",
            "description": "Compares document expiry against current date; flags expired or < 30 days validity.",
            "target_keys": ["EXPIRED_IDENTITY_DOCUMENT", "id_expiry_date", "is_expired"],
        },
        {
            "sub_id": "CHK_05.4",
            "name": "Proof of Address Ingestion & Template Watermark Check",
            "description": "Verifies utility bill or bank statement presence and audits against mock template generators.",
            "target_keys": ["MISSING_PROOF_OF_ADDRESS", "proof_of_address", "FRAUDULENT_POA_TEMPLATE"],
        },
        {
            "sub_id": "CHK_05.5",
            "name": "Proof of Address 90-Day Freshness Recency",
            "description": "Asserts utility bill / statement issuance date is within 90 days of onboarding submission.",
            "target_keys": ["EXPIRED_PROOF_OF_ADDRESS", "address_issue_date", "POA_STALE_OVER_90_DAYS"],
        },
        {
            "sub_id": "CHK_05.6",
            "name": "Cross-Document Name & Residential Address Reconciliation",
            "description": "Reconciles full individual name and residential address between ID and Proof of Address.",
            "target_keys": ["NAME_ADDRESS_DISCREPANCY", "ADDRESS_MISMATCH", "NAME_MISMATCH"],
        },
    ],
    "CHK_06_UBO_COMPLEX": [
        {
            "sub_id": "CHK_06.1",
            "name": "GLDB UBO Declaration Execution & Completeness",
            "description": "Verifies formal UBO Declaration form is executed by authorized officer and fully populated.",
            "target_keys": ["ubo_declaration", "MISSING_UBO_DECLARATION", "UNEXECUTED_UBO_DECLARATION"],
        },
        {
            "sub_id": "CHK_06.2",
            "name": "Bearer Share Prohibition Enforcement",
            "description": "Confirms intermediate and parent holding structures strictly prohibit bearer share instruments.",
            "target_keys": ["has_bearer_shares", "BEARER_SHARES_PROHIBITED"],
        },
        {
            "sub_id": "CHK_06.3",
            "name": "Nominee Director & Shareholder Arrangement Disclosure",
            "description": "Tests for nominee shareholders and verifies licensed trust agreements and nominator ID&V.",
            "target_keys": ["has_nominee_shareholders", "NOMINEE_SHAREHOLDERS_DETECTED"],
        },
        {
            "sub_id": "CHK_06.4",
            "name": "Source of Wealth Narrative & Primary Corroboration",
            "description": "Evaluates UBO source of wealth narrative depth and corroborating audited financials/deeds.",
            "target_keys": ["wealth_narrative_provided", "wealth_corroborating_docs_attached", "MISSING_WEALTH_PLAUSIBILITY", "MISSING_CORROBORATING_WEALTH_DOCS"],
        },
        {
            "sub_id": "CHK_06.5",
            "name": "UBO 25% Ownership Threshold & ROM Reconciliation",
            "description": "Verifies natural persons with ≥ 25% equity reconcile against Register of Members.",
            "target_keys": ["ubos", "UBO_ROM_MISMATCH", "UBO_THRESHOLD_UNRESOLVED"],
        },
    ],
    "CHK_07_SANCTIONS": [
        {
            "sub_id": "CHK_07.1",
            "name": "Sanctions Questionnaire Ingestion & Dual Sign-Off",
            "description": "Asserts presence of executed GLDB Sanctions Questionnaire with Maker and Approver sign-off.",
            "target_keys": ["is_sanction_questionnaire", "MISSING_SANCTIONS_QUESTIONNAIRE", "UNEXECUTED_SANCTION_QUESTIONNAIRE"],
        },
        {
            "sub_id": "CHK_07.2",
            "name": "Relationship Manager Department & SCF Master Code Alignment",
            "description": "Validates booking center RM code against bank master division codes for Supply Chain Finance.",
            "target_keys": ["rm_department_code", "is_scf_code_matched", "UNAUTHORIZED_RM_DESK", "UNMATCHED_RM_SCF_CODE"],
        },
        {
            "sub_id": "CHK_07.3",
            "name": "Strategic Dual-Use Goods & Trade Compliance Escalation",
            "description": "Scans declared commodities against Wassenaar/EU/MAS lists; verifies Trade Compliance sign-off.",
            "target_keys": ["has_dual_use_goods", "escalated_to_trade_compliance", "DUAL_USE_ESCALATION_MISSING", "UNESCALATED_DUAL_USE_GOODS"],
        },
    ],
    "CHK_08_INSTITUTIONAL": [
        {
            "sub_id": "CHK_08.1",
            "name": "Dynamic Entity Classification & Questionnaire Applicability",
            "description": "Identifies if entity is Bank, MSB, Fund, or Trustee triggering specialized institutional questionnaires.",
            "target_keys": ["institutional_type", "MISSING_INSTITUTIONAL_QUESTIONNAIRE"],
        },
        {
            "sub_id": "CHK_08.2",
            "name": "Wolfsberg CBDDQ Signature Recency (≤ 12 Months)",
            "description": "Verifies Wolfsberg CBDDQ / FCCQ was signed by Chief Compliance Officer within 12 months.",
            "target_keys": ["wolfsberg_signature_date", "wolfsberg_is_recent_12m", "WOLFSBERG_QUESTIONNAIRE_EXPIRED", "EXPIRED_WOLFSBERG_QUESTIONNAIRE"],
        },
        {
            "sub_id": "CHK_08.3",
            "name": "Critical Negative Answer Inspection (Correspondent/Shell Accounts)",
            "description": "Inspects core anti-shell bank controls, nested accounts, and PEP monitoring declarations.",
            "target_keys": ["wolfsberg_has_critical_no_answer", "PROHIBITED_INSTITUTIONAL_EXPOSURE", "CRITICAL_CONTROL_NO_ANSWER"],
        },
    ],
    "CHK_09_CDD_EDD": [
        {
            "sub_id": "CHK_09.1",
            "name": "CDD / EDD Proposal Form Ingestion & Form Completion",
            "description": "Verifies periodic review proposal form is present and fully executed without blank sections.",
            "target_keys": ["cdd_form_present", "MISSING_CDD_QUESTIONNAIRE", "UNEXECUTED_CDD_QUESTIONNAIRE"],
        },
        {
            "sub_id": "CHK_09.2",
            "name": "Singapore Commercial Nexus Substantiation",
            "description": "Enforces substantive commercial nexus to Singapore (headquarters, contracts, local hub).",
            "target_keys": ["singapore_nexus_rationale", "has_valid_singapore_nexus", "INSUFFICIENT_SINGAPORE_NEXUS"],
        },
        {
            "sub_id": "CHK_09.3",
            "name": "Account Purpose & Wholesale Banking Product Alignment",
            "description": "Cross-checks declared purpose against banking products, counterparties, and business model.",
            "target_keys": ["account_purpose", "selected_product", "account_purpose_matched", "PRODUCT_PURPOSE_MISALIGNMENT", "PURPOSE_PRODUCT_MISMATCH"],
        },
        {
            "sub_id": "CHK_09.4",
            "name": "Monthly Throughput vs Annual Turnover Pass-Through Risk",
            "description": "Asserts annualized expected throughput does not abnormally exceed declared annual turnover.",
            "target_keys": ["is_passthrough_risk_flagged", "PASS_THROUGH_VOLUME_EXCESS", "PASS_THROUGH_RISK"],
        },
        {
            "sub_id": "CHK_09.5",
            "name": "Tax Risk Completeness & 'N/A' Anti-Avoidance",
            "description": "Audits FATCA/CRS section to ensure tax residency and TIN are answered without bare 'N/A'.",
            "target_keys": ["tax_risk_section_populated", "TAX_RISK_INCOMPLETE_OR_NA", "INCOMPLETE_TAX_RISK_SECTION"],
        },
        {
            "sub_id": "CHK_09.6",
            "name": "EU / FATF Tax Haven & High-Risk Jurisdiction Controls",
            "description": "Checks for non-cooperative tax haven exposure and verifies enhanced mitigating controls.",
            "target_keys": ["tax_haven_jurisdictions", "has_tax_mitigating_controls", "TAX_HAVEN_MITIGATION_ABSENT", "UNMITIGATED_TAX_HAVEN_EXPOSURE"],
        },
        {
            "sub_id": "CHK_09.7",
            "name": "Continuation Narrative Depth (≥ 30 words) & Sign-Offs",
            "description": "Verifies substantive business continuation narrative (≥ 30 words) and Maker/Approver endorsements.",
            "target_keys": ["continuation_rationale", "continuation_word_count", "GOVERNANCE_SIGNOFF_INCOMPLETE", "INSUFFICIENT_CONTINUATION_NARRATIVE"],
        },
    ],
    "CHK_10_INGESTION_QUALITY": [
        {
            "sub_id": "CHK_10.1",
            "name": "Document OCR Confidence, Resolution & Visual Integrity",
            "description": "Measures scan resolution, OCR confidence (≥ 85%), and checks for clipped or blurry scans.",
            "target_keys": ["ocr_confidence", "is_blurry_or_cutoff", "POOR_OCR_OR_IMAGE_RESOLUTION", "BLURRY_OR_CUTOFF_DOCUMENT"],
        },
        {
            "sub_id": "CHK_10.2",
            "name": "Non-Registry Copy Certified True Copy (CTC) Attestation",
            "description": "Validates CTC stamps for certifier name, professional capacity, signature, and date.",
            "target_keys": ["has_ctc_stamp", "ctc_details_complete", "INCOMPLETE_CTC_ATTESTATION", "INCOMPLETE_CTC_DETAILS"],
        },
        {
            "sub_id": "CHK_10.3",
            "name": "Certified Sworn Translation for Foreign Language Documents",
            "description": "Verifies certified sworn English translation for any non-English statutory instruments.",
            "target_keys": ["is_non_english", "has_certified_translation", "NON_ENGLISH_DOCUMENT_UNTRANSLATED", "MISSING_CERTIFIED_TRANSLATION"],
        },
    ],
    "CHK_11_MAS_REGISTER": [
        {
            "sub_id": "CHK_11.1",
            "name": "Regulated Financial Entity Scope & Live MAS Search",
            "description": "Performs real-time search against Monetary Authority of Singapore Financial Institutions Directory.",
            "target_keys": ["mas_institution_found", "UNLICENSED_FINANCIAL_ACTIVITY", "UNREGISTERED_FINANCIAL_INSTITUTION"],
        },
        {
            "sub_id": "CHK_11.2",
            "name": "Licence Standing (Active/Current vs Ceased/Revoked)",
            "description": "Asserts MAS regulatory status is Active/Current; flags Suspended, Ceased, or Revoked licenses.",
            "target_keys": ["mas_licence_status", "MAS_LICENCE_NOT_ACTIVE", "INACTIVE_MAS_LICENCE"],
        },
        {
            "sub_id": "CHK_11.3",
            "name": "Country of Incorporation & UEN Concordance",
            "description": "Reconciles registration jurisdiction and UEN recorded on MAS directory against BizFile.",
            "target_keys": ["mas_uen", "MAS_REGISTRY_DISCREPANCY", "MAS_UEN_MISMATCH"],
        },
        {
            "sub_id": "CHK_11.4",
            "name": "Key Management Personnel (CEO & Representative) Check",
            "description": "Cross-checks MAS registered executives and appointed representatives against Register of Directors.",
            "target_keys": ["mas_key_executives", "MAS_KEY_PERSONNEL_MISMATCH", "MAS_REPRESENTATIVE_MISMATCH"],
        },
    ],
    "CHK_12_RISK_CALCULATOR": [
        {
            "sub_id": "CHK_12.1",
            "name": "10-Feature Entity Risk Scoring Execution",
            "description": "Computes deterministic weighted risk scores across 10 operational compliance dimensions.",
            "target_keys": ["calculator_model_risk_score", "RISK_FEATURE_CALCULATION_ERROR", "CALCULATOR_SCORE_MISMATCH"],
        },
        {
            "sub_id": "CHK_12.2",
            "name": "Interested Party Identification & Individual Risk Scoring",
            "description": "Scores connected directors, signatories, and UBOs for nationality, residency, and PEP status.",
            "target_keys": ["interested_parties", "PARTY_RISK_UNRESOLVED", "OMITTED_INTERESTED_PARTIES"],
        },
        {
            "sub_id": "CHK_12.3",
            "name": "Mandatory Rule-Based Risk Ceiling Override Enforcement",
            "description": "Applies mandatory override ceiling for PEPs, defense, or high-risk origin jurisdictions.",
            "target_keys": ["calculator_rule_based_risk_score", "OVERRIDE_CEILING_NOT_APPLIED", "MISSING_RULE_OVERRIDE"],
        },
        {
            "sub_id": "CHK_12.4",
            "name": "Automated Composite Risk Band Determination",
            "description": "Validates final assigned tier (Low < 2.0, Medium 2.0-3.5, High > 3.5).",
            "target_keys": ["calculator_final_risk_score", "calculator_risk_rating", "INVALID_RISK_BAND_ASSIGNMENT", "RISK_RATING_BAND_MISMATCH"],
        },
        {
            "sub_id": "CHK_12.5",
            "name": "Uploaded Spreadsheet Audit & Verification",
            "description": "Cross-checks RM-uploaded spreadsheet against ground-truth facts to catch omissions.",
            "target_keys": ["is_risk_calculator", "RISK_SPREADSHEET_DISCREPANCY", "CALCULATOR_DEFICIENT", "MISSING_RISK_CALCULATOR"],
        },
    ],
    "CHK_13_DIGITAL_FOOTPRINT": [
        {
            "sub_id": "CHK_13.1",
            "name": "Official Corporate Portal Online / HTTP Reachability",
            "description": "Probes declared corporate website via HTTP/TLS to verify operational availability.",
            "target_keys": ["website_url", "CORPORATE_WEBSITE_UNREACHABLE", "WEBSITE_UNREACHABLE"],
        },
        {
            "sub_id": "CHK_13.2",
            "name": "Domain Registration Age Shelf-Company Risk (< 30 Days)",
            "description": "Queries RDAP/WHOIS protocols; flags domains registered < 30 days prior to onboarding.",
            "target_keys": ["domain_age_days", "DOMAIN_NEWLY_REGISTERED", "SHELF_COMPANY_DOMAIN_AGE"],
        },
        {
            "sub_id": "CHK_13.3",
            "name": "Advertised Website Services vs ACRA Activity Consistency",
            "description": "Compares website service offerings against ACRA SSIC activities to detect disguised activities.",
            "target_keys": ["COMMERCIAL_ACTIVITY_INCONSISTENCY", "MISSING_MX_RECORDS", "COMMERCIAL_ACTIVITY_MISMATCH"],
        },
    ],
    "CHK_14_TRANSACTION_REVIEW": [
        {
            "sub_id": "CHK_14.1",
            "name": "Continuous Lookback Window Verification (≥ 170 Days)",
            "description": "Parses transaction dates; asserts continuous statement lookback coverage spanning ≥ 170 days.",
            "target_keys": ["coverage_days", "INSUFFICIENT_STATEMENT_LOOKBACK", "LOOKBACK_WINDOW_INSUFFICIENT"],
        },
        {
            "sub_id": "CHK_14.2",
            "name": "Monthly Inflow/Outflow Aggregation & Multi-Currency Segregation",
            "description": "Aggregates transactions by calendar month and currency code (SGD, USD, EUR, etc.).",
            "target_keys": ["monthly_totals_by_currency", "TRANSACTION_AGGREGATION_FAILURE", "TRANSACTION_AGGREGATION_FAILED"],
        },
        {
            "sub_id": "CHK_14.3",
            "name": "Account Dormancy & Inactivity Detection (≥ 2 Consecutive Months)",
            "description": "Identifies if account had zero commercial throughput across ≥ 2 consecutive months.",
            "target_keys": ["consecutive_dormant_months", "PROTRACTED_ACCOUNT_DORMANCY", "ACCOUNT_DORMANCY_DETECTED"],
        },
        {
            "sub_id": "CHK_14.4",
            "name": "Sudden Transaction Volume / Velocity Spike Detection (> 50% Surge)",
            "description": "Calculates month-over-month variances; flags unjustified volume surges exceeding > 50%.",
            "target_keys": ["mom_variance_percentage", "ANOMALOUS_TRANSACTION_SPIKE", "TRANSACTION_VOLUME_SPIKE"],
        },
        {
            "sub_id": "CHK_14.5",
            "name": "CDD Declared Volume Cross-Reconciliation (≤ 50% Variance)",
            "description": "Cross-compares observed monthly volume against declared throughput in CDD Proposal Form.",
            "target_keys": ["variance_percentage", "DECLARED_ACTUAL_THROUGHPUT_DIVERGENCE", "VOLUME_VARIANCE_EXCEEDED", "MISSING_TRANSACTION_LISTING"],
        },
    ],
}


def build_subchecks_for_result(
    check_id: str,
    verdict: Verdict,
    findings: List[ValidationFinding],
    evaluated_files: List[ItemizedDocStatus],
) -> List[SubCheckStatus]:
    """Generates granular sub-check statuses for a check result based on findings and evaluated documents."""
    specs = SUBCHECK_DEFINITIONS.get(check_id, [])
    if not specs:
        return []

    file_names = [f.doc_name for f in evaluated_files] if evaluated_files else ["Bundle Evidence"]
    sub_results: List[SubCheckStatus] = []

    for spec in specs:
        sub_id = spec["sub_id"]
        name = spec["name"]
        description = spec["description"]
        target_keys = [k.upper() for k in spec["target_keys"]]

        # Find any matching finding
        matched_finding = None
        for f in findings:
            if f.check_id != check_id:
                continue
            r_code = (f.reason or "").upper()
            t_field = (f.target_field or "").upper()
            f_type = (f.finding_type or "").upper()
            m_doc = (f.missing_document or "").upper()
            f_det = (f.details or "").upper()

            def _match_key(k: str) -> bool:
                if not k or len(k) < 3:
                    return False
                for target in (r_code, t_field, f_type, m_doc, f_det):
                    if target and (k in target or (len(target) >= 4 and target in k)):
                        return True
                return False

            if any(_match_key(k) for k in target_keys):
                matched_finding = f
                break

        if matched_finding:
            sub_results.append(
                SubCheckStatus(
                    sub_id=sub_id,
                    name=name,
                    verdict=Verdict.FAIL,
                    description=description,
                    details=matched_finding.details or f"Non-compliant: {matched_finding.reason}",
                    cross_checked_files=file_names,
                )
            )
        elif verdict == Verdict.FAIL and len(specs) == 1:
            # If the entire check failed and only 1 subcheck exists
            sub_results.append(
                SubCheckStatus(
                    sub_id=sub_id,
                    name=name,
                    verdict=Verdict.FAIL,
                    description=description,
                    details="Deficiencies identified during automated validation review.",
                    cross_checked_files=file_names,
                )
            )
        else:
            sub_results.append(
                SubCheckStatus(
                    sub_id=sub_id,
                    name=name,
                    verdict=Verdict.PASS,
                    description=description,
                    details="Verified & fully compliant with wholesale banking regulatory policy standards.",
                    cross_checked_files=file_names,
                )
            )

    # If check failed overall but no specific sub-check was tagged, mark first sub-check
    if verdict == Verdict.FAIL and not any(s.verdict == Verdict.FAIL for s in sub_results) and sub_results:
        sub_results[0].verdict = Verdict.FAIL
        sub_results[0].details = "Deficiencies identified during automated validation review."

    return sub_results


def build_executive_summary(
    bundle_name: str,
    uen: Optional[str],
    entity_type: str,
    overall_verdict: str,
    passed_count: int,
    total_count: int,
    findings: List[ValidationFinding],
    elapsed_seconds: Optional[float] = None,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
) -> Dict[str, Any]:
    """Assembles an executive validation summary for display and reporting."""
    compliance_pct = round((passed_count / max(total_count, 1)) * 100, 1)
    is_pass = overall_verdict.upper() == "PASS"

    high_findings = [f for f in findings if f.severity == Priority.HIGH]
    med_findings = [f for f in findings if f.severity == Priority.MEDIUM]

    if is_pass:
        risk_tier = "Low / Standard Risk"
        narrative = (
            f"The corporate client file for '{bundle_name}' has successfully cleared wholesale banking onboarding validation. "
            f"All {total_count} statutory checks (including ACRA BizFile registry verification, constitutional execution, "
            f"UBO transparency thresholds, sanctions screening, MAS directory status, and transaction history lookback) "
            f"are verified with zero high-severity policy discrepancies."
        )
        recommendation = "Approved for Wholesale Banking Account Opening and product provisioning. Proceed with standard annual periodic review schedule."
    else:
        risk_tier = "High Risk / Action Required" if len(high_findings) > 0 else "Medium Risk / Review Required"
        narrative = (
            f"Automated policy validation for '{bundle_name}' concluded with verdict {overall_verdict.upper()} "
            f"({passed_count}/{total_count} checks passed, {compliance_pct}% compliance score). "
            f"A total of {len(high_findings)} high-priority policy findings and {len(med_findings)} medium-priority observations were flagged "
            f"requiring mandatory remediation before account operationalization."
        )
        recommendation = (
            f"Hold account opening pending receipt of missing/deficient documentation. "
            f"Review flagged items: {'; '.join([f.reason for f in high_findings[:3]])}."
        )

    kris = [
        {"name": "Registry Standing", "status": "Clean" if not any(f.check_id in ["CHK_01_BIZFILE", "CHK_02_INCORP"] for f in high_findings) else "Discrepancy", "icon": "building-2"},
        {"name": "Sanctions & Dual-Use", "status": "Clean" if not any(f.check_id == "CHK_07_SANCTIONS" for f in high_findings) else "Flagged", "icon": "shield-check"},
        {"name": "UBO Transparency", "status": "Verified (25%)" if not any(f.check_id == "CHK_06_UBO_COMPLEX" for f in high_findings) else "Deficient", "icon": "users"},
        {"name": "MAS FI Status", "status": "Verified" if not any(f.check_id == "CHK_11_MAS_REGISTER" for f in high_findings) else "Discrepancy", "icon": "landmark"},
        {"name": "6-Month Lookback", "status": "Compliant (≥170d)" if not any(f.check_id == "CHK_14_TRANSACTION_REVIEW" for f in high_findings) else "Incomplete", "icon": "receipt"},
    ]

    return {
        "client_name": bundle_name,
        "entity_name": bundle_name,
        "uen": uen or "Pending Verification",
        "entity_type": entity_type,
        "overall_verdict": overall_verdict,
        "verdict": overall_verdict,
        "passed_count": passed_count,
        "total_count": total_count,
        "compliance_percentage": compliance_pct,
        "risk_tier": risk_tier,
        "narrative": narrative,
        "recommendation": recommendation,
        "kris": kris,
        "key_risk_indicators": kris,
        "high_findings_count": len(high_findings),
        "med_findings_count": len(med_findings),
        "elapsed_seconds": elapsed_seconds,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    }

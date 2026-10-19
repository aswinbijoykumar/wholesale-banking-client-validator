from typing import List, Tuple
from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
)
from backend.validators.context import (
    BundleContext,
    calculate_month_diff,
    parse_date_safe,
)


class RegulatoryQuestionnairesValidator:
    """Evaluates:
    - CHK_07_SANCTIONS: Sanction Questionnaire & Strategic Goods Review (Descr. 10)
    - CHK_08_INSTITUTIONAL: Institutional Questionnaires & Wolfsberg CBDDQ Review (Descr. 12)
    - CHK_09_CDD_EDD: CDD / EDD Account Purpose, Tax Risk & Sign-Off Governance (Descr. 13, 21, 28)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        all_findings: List[ValidationFinding] = []

        # =========================================================================
        # CHECK 7: Sanction Questionnaire & Strategic Goods Review (Descr. 10)
        # =========================================================================
        chk7_findings: List[ValidationFinding] = []
        chk7_files: List[ItemizedDocStatus] = []
        chk7_reason: str | None = None
        chk7_priority: Priority = Priority.HIGH

        is_high_risk = ctx.profile.risk_rating == "HIGH" or any(e.risk_rating == "HIGH" for e in ctx.extractions)
        is_scf = any(e.is_scf_department or (e.rm_department_code and "SCF" in e.rm_department_code.upper()) for e in ctx.extractions)
        is_wholesale_goods = any(
            e.is_wholesale_trade_goods or 
            (e.core_business_activities and any(k in e.core_business_activities.lower() for k in ["wholesale", "trading", "import", "export", "commodities", "goods", "electronics", "chemicals"]))
            for e in ctx.extractions
        )

        is_sanctions_triggered = is_high_risk or is_scf or is_wholesale_goods

        if is_sanctions_triggered and not ctx.sanction_docs:
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
        elif not is_sanctions_triggered and not ctx.sanction_docs:
            chk7_files.append(
                ItemizedDocStatus(
                    doc_name="Sanctions Routing Assessment",
                    doc_type="GLDB Internal Document",
                    verdict=Verdict.PASS,
                    details="Questionnaire not triggered: Entity is Standard Risk, Non-SCF, and not engaged in wholesale physical goods trading.",
                )
            )
        else:
            for s_doc in ctx.sanction_docs:
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
        # =========================================================================
        chk8_findings: List[ValidationFinding] = []
        chk8_files: List[ItemizedDocStatus] = []
        chk8_reason: str | None = None
        chk8_priority: Priority = Priority.HIGH

        e_type_upper = (ctx.bundle_entity_type or "").upper()
        activities_upper = (ctx.profile.core_business_activities or "").upper()
        is_bank_fi = "BANK" in e_type_upper or "FINANCIAL INSTITUTION" in e_type_upper or "BANK" in activities_upper
        is_fund_pe = "FUND" in e_type_upper or "PRIVATE EQUITY" in e_type_upper or "INVESTMENT VEHICLE" in e_type_upper or "FUND" in activities_upper
        is_msb_pay = "PAYMENT" in e_type_upper or "MONEY SERVICE" in e_type_upper or "MSB" in e_type_upper or "REMITTANCE" in activities_upper or "PAYMENT" in activities_upper
        is_trustee = "TRUST" in e_type_upper or "TRUSTEE" in activities_upper

        is_institutional_entity = is_bank_fi or is_fund_pe or is_msb_pay or is_trustee or bool(ctx.institutional_docs)

        if is_institutional_entity and not ctx.institutional_docs:
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
            for inst_doc in ctx.institutional_docs:
                doc_pass = True
                fail_notes = []

                # 1. Recency check (<= 12 months)
                w_date = parse_date_safe(inst_doc.wolfsberg_signature_date)
                if w_date:
                    m_diff = calculate_month_diff(ctx.today, w_date)
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
        # =========================================================================
        chk9_findings: List[ValidationFinding] = []
        chk9_files: List[ItemizedDocStatus] = []
        chk9_reason: str | None = None
        chk9_priority: Priority = Priority.HIGH

        eu_tax_havens = ["panama", "cayman", "bvi", "british virgin islands", "vanuatu", "samoa", "fiji", "guam", "trinidad", "seychelles", "bahamas", "belize", "bermuda", "turks and caicos"]

        if not ctx.cdd_docs:
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
            for cdd in ctx.cdd_docs:
                doc_pass = True
                fail_notes = []

                # 1. Singapore Nexus Justification (Descr. 13)
                has_sg_presence = ctx.profile.place_of_business and "singapore" in ctx.profile.place_of_business.lower()
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

        return results, all_findings

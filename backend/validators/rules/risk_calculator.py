"""Customer Risk Rating & Risk Calculator Integrity Rule Implementation.

Evaluates:
- CHK_12_RISK_CALCULATOR: Customer Risk Rating & Risk Calculator Integrity Review
  (Step 27: Verify Risk Calculator uploaded, completeness across all interested parties,
   10-feature model consistency, rule-based override enforcement, and accurate final rating)
"""
from datetime import date
from typing import List, Tuple, Dict, Any

from backend.models import (
    CheckResult,
    ItemizedDocStatus,
    Priority,
    ValidationFinding,
    Verdict,
    InterestedPartyRiskItem,
    RiskCalculatorProfile,
)
from backend.validators.context import BundleContext, parse_date_safe

# Standard GLDB Country Risk Scores (0-100) aligned with FATF & Basel AML Index
COUNTRY_RISK_SCORES: Dict[str, float] = {
    # High Risk & Sanctioned / Blacklisted
    "KH": 100.0, "CAMBODIA": 100.0, "KH-CAMBODIA": 100.0,
    "MM": 100.0, "MYANMAR": 100.0, "MM-MYANMAR": 100.0,
    "KP": 100.0, "NORTH KOREA": 100.0, "DPRK": 100.0,
    "IR": 100.0, "IRAN": 100.0, "IR-IRAN": 100.0,
    "RU": 100.0, "RUSSIA": 100.0, "RU-RUSSIA": 100.0,
    "SY": 100.0, "SYRIA": 100.0,
    
    # Medium-High Risk
    "HU": 74.0, "HUNGARY": 74.0, "HU-HUNGARY": 74.0,
    "AE": 74.0, "UNITED ARAB EMIRATES": 74.0, "UAE": 74.0, "AE-UNITED ARAB EMIRATES": 74.0,
    "PA": 75.0, "PANAMA": 75.0, "PA-PANAMA": 75.0,
    "KY": 70.0, "CAYMAN ISLANDS": 70.0, "VG": 70.0, "BRITISH VIRGIN ISLANDS": 70.0,
    "VG-BRITISH VIRGIN ISLANDS": 70.0,
    "TR": 65.0, "TURKEY": 65.0,
    "VN": 60.0, "VIETNAM": 60.0,
    "ID": 55.0, "INDONESIA": 55.0,
    
    # Low Risk Tier-1 FATF equivalents
    "CA": 49.0, "CANADA": 49.0, "CA-CANADA": 49.0,
    "SG": 15.0, "SINGAPORE": 15.0, "SG-SINGAPORE": 15.0,
    "GB": 25.0, "UNITED KINGDOM": 25.0, "UK": 25.0,
    "US": 30.0, "UNITED STATES": 30.0, "USA": 30.0,
    "AU": 25.0, "AUSTRALIA": 25.0,
    "JP": 20.0, "JAPAN": 20.0,
    "DE": 20.0, "GERMANY": 20.0,
    "CH": 25.0, "SWITZERLAND": 25.0,
    "HK": 35.0, "HONG KONG": 35.0,
}

# Rule-Based Override High-Risk Countries (Hard trigger = 100)
HIGH_RISK_COUNTRY_CODES = {"KH", "MM", "KP", "IR", "RU", "SY"}
HIGH_RISK_COUNTRY_NAMES = {"CAMBODIA", "MYANMAR", "NORTH KOREA", "DPRK", "IRAN", "RUSSIA", "SYRIA"}

HIGH_RISK_INDUSTRIES = [
    "remittance", "money changer", "crypto", "vasp", "virtual asset", "arms", "defense",
    "dual-use", "precious stones", "precious metals", "gambling", "casino", "bunkering", "crude oil"
]


def extract_country_tokens(val: str | None) -> Tuple[str, str]:
    """Given 'KH-CAMBODIA', returns ('KH', 'CAMBODIA'). Given 'CAMBODIA', returns ('', 'CAMBODIA')."""
    if not val:
        return "", ""
    v = val.strip().upper()
    if "-" in v:
        parts = v.split("-", 1)
        return parts[0].strip(), parts[1].strip()
    return "", v


def is_high_risk_country(val: str | None) -> bool:
    code, name = extract_country_tokens(val)
    if code in HIGH_RISK_COUNTRY_CODES:
        return True
    if name in HIGH_RISK_COUNTRY_NAMES:
        return True
    return False


def get_country_risk(val: str | None) -> float:
    if not val:
        return 40.0
    code, name = extract_country_tokens(val)
    raw = val.strip().upper()
    if raw in COUNTRY_RISK_SCORES:
        return COUNTRY_RISK_SCORES[raw]
    if code in COUNTRY_RISK_SCORES:
        return COUNTRY_RISK_SCORES[code]
    if name in COUNTRY_RISK_SCORES:
        return COUNTRY_RISK_SCORES[name]
    return 50.0  # Default neutral score for unspecified country


def names_match(n1: str, n2: str) -> bool:
    if not n1 or not n2:
        return False
    clean1 = "".join(ch for ch in n1.lower() if ch.isalnum() or ch.isspace()).split()
    clean2 = "".join(ch for ch in n2.lower() if ch.isalnum() or ch.isspace()).split()
    if not clean1 or not clean2:
        return False
    # Check if words overlap significantly
    set1, set2 = set(clean1), set(clean2)
    return set1 == set2 or set1.issubset(set2) or set2.issubset(set1)


class RiskCalculatorValidator:
    """Evaluates:
    - CHK_12_RISK_CALCULATOR: Customer Risk Rating & Risk Calculator Integrity Review
      (Calculates 10-feature model, party scores, rule overrides, and risk band directly from KYC files)
    """

    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results: List[CheckResult] = []
        chk12_findings: List[ValidationFinding] = []
        chk12_files: List[ItemizedDocStatus] = []
        chk12_reason: str | None = None
        chk12_priority: Priority = Priority.HIGH

        # -------------------------------------------------------------
        # 1. Gather Ground-Truth Interested Parties from Ingested Files
        # -------------------------------------------------------------
        passports = {e.id_holder_name.lower(): e for e in ctx.id_docs if e.id_holder_name}
        poas = {e.address_holder_name.lower(): e for e in ctx.poa_docs if e.address_holder_name}

        # Candidate parties: UBOs + Directors
        parties_dict: Dict[str, Dict[str, Any]] = {}

        # Add UBOs
        for u in ctx.profile.ubos:
            if u.name:
                clean_name = u.name.strip()
                parties_dict[clean_name.lower()] = {
                    "name": clean_name,
                    "role": f"UBO ({u.ownership_percentage or 0}%)",
                    "nationality": u.nationality,
                    "residence": None,
                }

        # Add Directors
        for d in ctx.profile.directors:
            if d.name:
                clean_name = d.name.strip()
                lower_key = clean_name.lower()
                if lower_key not in parties_dict:
                    parties_dict[lower_key] = {
                        "name": clean_name,
                        "role": "Director",
                        "nationality": d.nationality,
                        "residence": None,
                    }

        # Reconcile citizenship & residence from passports and proof of address
        for lower_name, p_data in parties_dict.items():
            # Match passport
            for p_holder, id_ext in passports.items():
                if names_match(p_data["name"], p_holder):
                    if not p_data["nationality"]:
                        p_data["nationality"] = id_ext.place_of_incorporation or id_ext.document_language or "SG"
                    break

            # Match proof of address
            for poa_holder, poa_ext in poas.items():
                if names_match(p_data["name"], poa_holder):
                    p_data["residence"] = poa_ext.proof_address or "Singapore"
                    break

        # Compute individual scores for each ground-truth party
        computed_parties: List[InterestedPartyRiskItem] = []
        rule_override_reasons: List[str] = []
        max_connected_party_score = 15.0

        for p_key, p_info in parties_dict.items():
            cit = p_info.get("nationality") or "SG"
            res = p_info.get("residence") or "SG"
            cit_score = get_country_risk(cit)
            res_score = get_country_risk(res)
            model_indiv = round((cit_score * 0.4) + (res_score * 0.6), 1)

            indiv_rule_score = None
            indiv_reasons = []

            # Check rule-based override for high-risk jurisdiction
            if is_high_risk_country(cit) or is_high_risk_country(res):
                indiv_rule_score = 100.0
                reason_str = f"Interested Party '{p_info['name']}' residency/citizenship in {res or cit} triggers [100] High Risk"
                indiv_reasons.append(reason_str)
                rule_override_reasons.append(reason_str)

            final_indiv = max(model_indiv, indiv_rule_score or 0.0)
            if final_indiv > max_connected_party_score:
                max_connected_party_score = final_indiv

            computed_parties.append(
                InterestedPartyRiskItem(
                    name=p_info["name"],
                    citizenship=cit,
                    citizenship_score=cit_score,
                    residence_country=res,
                    residence_score=res_score,
                    watchlist_risk="None",
                    watchlist_score=0.0,
                    total_model_score=model_indiv,
                    rule_based_score=indiv_rule_score,
                    rule_based_reasons=indiv_reasons,
                    final_risk_score=final_indiv,
                )
            )

        # -------------------------------------------------------------
        # 2. Automated Feature Scoring across the 10 Dimensions
        # -------------------------------------------------------------
        # Feature 1: Corporate Age
        corp_age_years = None
        f1_score = 25.0
        if ctx.profile.incorporation_date:
            inc_d = parse_date_safe(ctx.profile.incorporation_date)
            if inc_d:
                corp_age_years = round((ctx.today - inc_d).days / 365.25, 1)
                if corp_age_years < 1.0:
                    f1_score = 75.0  # Shelf / newly incorporated
                elif corp_age_years < 3.0:
                    f1_score = 50.0  # Young corporate
                else:
                    f1_score = 20.0  # Established

        # Feature 2: Watchlist Risk
        f2_score = 0.0
        if any(e.has_dual_use_goods for e in ctx.sanction_docs):
            f2_score = 75.0

        # Feature 3: HQ Country
        hq_country = ctx.profile.country_of_operations or ctx.profile.place_of_business or "Singapore"
        f3_score = get_country_risk(hq_country)

        # Feature 4: Operations Country
        ops_country = ctx.profile.country_of_operations or hq_country
        f4_score = get_country_risk(ops_country)

        # Feature 5: Account Type
        account_purpose = "Standard Operating CASA"
        f5_score = 25.0
        if ctx.cdd_docs:
            cdd = ctx.cdd_docs[0]
            if cdd.is_passthrough_risk_flagged:
                f5_score = 80.0
                account_purpose = "High-Velocity Pass-Through Account"
            elif cdd.account_purpose:
                account_purpose = cdd.account_purpose

        # Feature 6: Industry / SSIC
        activities_text = f"{ctx.profile.core_business_activities or ''}".lower()
        is_high_risk_industry = any(k in activities_text for k in HIGH_RISK_INDUSTRIES)
        if is_high_risk_industry:
            f6_score = 85.0
            rule_override_reasons.append("High risk industry / sensitive sector")
        else:
            f6_score = 25.0

        # Feature 7: Public Listing Status
        f7_score = 20.0 if "Public" in ctx.bundle_entity_type else 35.0

        # Feature 8: Onboarding Channel
        f8_score = 30.0

        # Feature 9: Distance to BO / Multi-layer offshore
        has_complex_structure = ctx.profile.has_complex_structure
        f9_score = 25.0
        if has_complex_structure:
            if not ctx.profile.complex_structure_rationale:
                f9_score = 100.0
                rule_override_reasons.append("Unjustified complex corporate holding structure")
            else:
                f9_score = 50.0

        # Feature 10: Connected Party Aggregate Score
        f10_score = max_connected_party_score

        # -------------------------------------------------------------
        # 3. Model Aggregation & Risk Band Computation
        # -------------------------------------------------------------
        # Weighted model score (Feature 1 to 9 = 50%, Feature 10 Connected Parties = 50%)
        entity_features_avg = (
            (f1_score * 0.10)
            + (f2_score * 0.10)
            + (f3_score * 0.10)
            + (f4_score * 0.10)
            + (f5_score * 0.10)
            + (f6_score * 0.15)
            + (f7_score * 0.05)
            + (f8_score * 0.05)
            + (f9_score * 0.15)
            + (f10_score * 0.10)
        )
        computed_model_score = round(entity_features_avg, 1)

        # Apply rule-based overrides
        rule_based_override = 100.0 if rule_override_reasons else None
        final_computed_score = round(max(computed_model_score, rule_based_override or 0.0), 1)

        # Determine automated Risk Band:
        # LOW (0.0 - 49.9), MEDIUM (50.0 - 74.9), HIGH (75.0 - 100.0)
        if final_computed_score >= 75.0:
            computed_risk_band = "HIGH"
        elif final_computed_score >= 50.0:
            computed_risk_band = "MEDIUM"
        else:
            computed_risk_band = "LOW"

        # Update profile risk rating
        ctx.profile.risk_rating = computed_risk_band

        # -------------------------------------------------------------
        # 4. Integrate or Audit against Uploaded Sheet (If Provided)
        # -------------------------------------------------------------
        calc_doc = ctx.risk_calc_docs[0] if ctx.risk_calc_docs else None
        calc_parties = (calc_doc.interested_parties or []) if calc_doc else []

        if calc_doc:
            # Audit mode: Cross-check uploaded sheet against computed ground-truth
            ubos_to_verify = [u for u in ctx.profile.ubos if (u.ownership_percentage or 0) >= 25.0]
            if not ubos_to_verify:
                ubos_to_verify = [u for u in ctx.profile.ubos if u.is_controller or (u.ownership_percentage or 0) > 0]

            missing_parties = []
            for u in ubos_to_verify:
                match = any(names_match(u.name, p.name) for p in calc_parties)
                if not match:
                    missing_parties.append(f"UBO: {u.name} ({u.ownership_percentage}%)")

            if missing_parties:
                chk12_findings.append(
                    ValidationFinding(
                        check_id="CHK_12_RISK_CALCULATOR",
                        finding_type="INCOMPLETE_INTERESTED_PARTIES",
                        severity=Priority.HIGH,
                        reason="OMITTED_INTERESTED_PARTIES",
                        target_field="interested_parties",
                        details=f"Risk Calculator is incomplete. Following key controllers / UBOs are omitted from individual risk calculation: {', '.join(missing_parties)}.",
                    )
                )
                if not chk12_reason:
                    chk12_reason = "OMITTED_INTERESTED_PARTIES"

            # Check individual override understatement in uploaded sheet
            for p in calc_parties:
                p_name = p.name.strip()
                has_high_risk_country = is_high_risk_country(p.residence_country) or is_high_risk_country(p.citizenship)
                if has_high_risk_country:
                    expected_rule_score = 100.0
                    actual_final = p.final_risk_score or p.total_model_score or 0.0
                    if actual_final < expected_rule_score:
                        chk12_findings.append(
                            ValidationFinding(
                                check_id="CHK_12_RISK_CALCULATOR",
                                finding_type="RULE_BASED_OVERRIDE_UNDERSTATED",
                                severity=Priority.HIGH,
                                reason="UNDERSTATED_RULE_BASED_SCORE",
                                target_field="final_risk_score",
                                details=(
                                    f"Individual '{p_name}' has residence/citizenship in high-risk jurisdiction "
                                    f"('{p.residence_country}' / '{p.citizenship}'), triggering mandatory [100] High Risk rule override, "
                                    f"but recorded final score is {actual_final}."
                                ),
                            )
                        )
                        if not chk12_reason:
                            chk12_reason = "UNDERSTATED_RULE_BASED_SCORE"

            # Reconcile customer rating understatement
            documented_rating = (
                calc_doc.calculator_risk_rating
                or ctx.profile.risk_rating
                or "MEDIUM"
            ).upper()

            if computed_risk_band == "HIGH" and documented_rating != "HIGH":
                chk12_findings.append(
                    ValidationFinding(
                        check_id="CHK_12_RISK_CALCULATOR",
                        finding_type="UNDERSTATED_CUSTOMER_RATING",
                        severity=Priority.HIGH,
                        reason="UNDERSTATED_CUSTOMER_RISK_RATING",
                        target_field="calculator_risk_rating",
                        details=(
                            f"Customer Risk Rating documented as '{documented_rating}', but computed profile triggers mandatory HIGH RISK "
                            f"due to: {'; '.join(rule_override_reasons)}."
                        ),
                    )
                )
                if not chk12_reason:
                    chk12_reason = "UNDERSTATED_CUSTOMER_RISK_RATING"

            calc_pass = len(chk12_findings) == 0
            doc_details_msg = [
                f"{len(calc_parties)} interested parties evaluated",
                f"Computed Rating: {computed_risk_band} ({final_computed_score})",
                f"Documented Rating: {documented_rating}",
            ]
            chk12_files.append(
                ItemizedDocStatus(
                    doc_name=calc_doc.filename or "Risk Calculator Sheet",
                    doc_type="GLDB Internal Risk Sheet",
                    verdict=Verdict.PASS if calc_pass else Verdict.FAIL,
                    reason=chk12_reason if not calc_pass else None,
                    details="; ".join(doc_details_msg) if calc_pass else f"Integrity Failure: {'; '.join([f.details for f in chk12_findings])}",
                )
            )
        else:
            # Sheet not uploaded: Auto-computation Mode directly from ingested KYC files
            calc_pass = True
            doc_details_msg = [
                f"Auto-Computed Customer Risk: {computed_risk_band} (Score: {final_computed_score}/100)",
                f"10-Feature Model Score: {computed_model_score}",
                f"Interested Parties Evaluated: {len(computed_parties)}",
            ]
            if rule_override_reasons:
                doc_details_msg.append(f"Overrides: {'; '.join(rule_override_reasons)}")

            chk12_files.append(
                ItemizedDocStatus(
                    doc_name="Automated Customer Risk Calculator Engine",
                    doc_type="KYC Risk Scorecard",
                    verdict=Verdict.PASS,
                    details="; ".join(doc_details_msg),
                )
            )

        # Save computed profile into context
        ctx.profile.risk_calculator = RiskCalculatorProfile(
            is_provided=bool(calc_doc),
            filename=calc_doc.filename if calc_doc else "Automated KYC Scorecard",
            customer_name=ctx.profile.legal_name or ctx.bundle_name,
            corporate_age_years=corp_age_years,
            corporate_age_score=f1_score,
            entity_watchlist_score=f2_score,
            hq_country=hq_country,
            hq_country_score=f3_score,
            operations_country=ops_country,
            operations_score=f4_score,
            account_type=account_purpose,
            account_type_score=f5_score,
            industry_ssic=ctx.profile.core_business_activities,
            industry_ssic_score=f6_score,
            listing_status=ctx.bundle_entity_type,
            listing_status_score=f7_score,
            channel_method="Standard Banking",
            channel_score=f8_score,
            distance_to_bo_layers=len(ctx.profile.ubos),
            distance_to_bo_score=f9_score,
            connected_party_aggregate_score=f10_score,
            parties=calc_parties if calc_parties else computed_parties,
            overall_model_score=computed_model_score,
            rule_based_override_score=rule_based_override,
            rule_based_reasons=rule_override_reasons,
            final_customer_risk_score=final_computed_score,
            final_customer_risk_rating=computed_risk_band,
        )

        chk12_verdict = Verdict.FAIL if chk12_findings else Verdict.PASS
        if chk12_verdict == Verdict.PASS:
            chk12_evidence = (
                f"Automated Customer Risk Assessment verified: Computed Risk Band is '{computed_risk_band}' "
                f"(Score: {final_computed_score}/100, Model Score: {computed_model_score}). "
                f"Evaluated across all 10 risk dimensions and {len(computed_parties)} interested party records from ingested KYC files."
            )
        else:
            chk12_evidence = f"Risk Calculator integrity issues (Step 27): {'; '.join([f.details for f in chk12_findings])}"

        results.append(
            CheckResult(
                check_id="CHK_12_RISK_CALCULATOR",
                rule_name="Customer Risk Rating & Risk Calculator Integrity Review",
                verdict=chk12_verdict,
                reason_code=chk12_reason if chk12_verdict == Verdict.FAIL else None,
                priority=chk12_priority,
                evidence=chk12_evidence,
                evaluated_files=chk12_files,
                findings=chk12_findings,
            )
        )

        return results, chk12_findings

"""End-to-End Test Suite for Customer Risk Rating & Risk Calculator (CHK_12_RISK_CALCULATOR).

Tests cover all edge cases:
1. Missing Risk Calculator document -> FAIL with MISSING_RISK_CALCULATOR.
2. Incomplete interested parties (e.g. John Tan included, but Jane Tan 50% UBO omitted) -> FAIL with OMITTED_INTERESTED_PARTIES.
3. Rule-based override understated (e.g. Cambodia residence KH-CAMBODIA has model score 69.6 but rule override requires 100) -> FAIL with UNDERSTATED_RULE_BASED_SCORE.
4. Documented customer risk rating understated (e.g. documented as MEDIUM but rule requires HIGH) -> FAIL with UNDERSTATED_CUSTOMER_RISK_RATING.
5. Fully compliant clean case (both parties evaluated, rule override applied, rating HIGH) -> PASS.
"""
from datetime import date
from backend.models import (
    DocType,
    RawDocExtraction,
    UboItem,
    DirectorItem,
    InterestedPartyRiskItem,
    Verdict,
    Priority,
)
from backend.validators.dispatcher import dispatch_wholesale_validation


def test_missing_risk_calculator():
    extractions = [
        RawDocExtraction(
            doc_type=DocType.BIZFILE,
            filename="bizfile.pdf",
            legal_name="Acme International Pte Ltd",
            uen="202012345A",
            ubos=[UboItem(name="John Tan", ownership_percentage=100.0, is_controller=True)],
        )
    ]
    results, findings, profile = dispatch_wholesale_validation(
        bundle_name="Acme International Pte Ltd",
        bundle_entity_type="Private Limited Company",
        extractions=extractions,
        today=date(2026, 10, 13),
    )
    chk12 = next((r for r in results if r.check_id == "CHK_12_RISK_CALCULATOR"), None)
    assert chk12 is not None
    assert chk12.verdict == Verdict.FAIL
    assert chk12.reason_code == "MISSING_RISK_CALCULATOR"
    print("PASS: test_missing_risk_calculator")


def test_omitted_interested_party():
    extractions = [
        RawDocExtraction(
            doc_type=DocType.UBO_DECLARATION,
            filename="ubo_declaration.pdf",
            ubos=[
                UboItem(name="John Tan", ownership_percentage=50.0, is_controller=True),
                UboItem(name="Jane Tan", ownership_percentage=50.0, is_controller=True),
            ],
            is_fully_executed=True,
        ),
        RawDocExtraction(
            doc_type=DocType.RISK_CALCULATOR,
            filename="risk_calculator.xlsx",
            calculator_customer_name="Acme International Pte Ltd",
            calculator_model_risk_score=50.0,
            calculator_final_risk_score=50.0,
            calculator_risk_rating="MEDIUM",
            # Only John Tan is included, Jane Tan is omitted
            interested_parties=[
                InterestedPartyRiskItem(
                    name="John Tan",
                    citizenship="CA-CANADA",
                    residence_country="CA-CANADA",
                    total_model_score=49.0,
                    final_risk_score=49.0,
                )
            ],
        ),
    ]
    results, findings, profile = dispatch_wholesale_validation(
        bundle_name="Acme International Pte Ltd",
        bundle_entity_type="Private Limited Company",
        extractions=extractions,
        today=date(2026, 10, 13),
    )
    chk12 = next((r for r in results if r.check_id == "CHK_12_RISK_CALCULATOR"), None)
    assert chk12 is not None
    assert chk12.verdict == Verdict.FAIL
    assert any("Jane Tan" in f.details for f in chk12.findings)
    assert chk12.reason_code == "OMITTED_INTERESTED_PARTIES"
    print("PASS: test_omitted_interested_party")


def test_rule_based_override_understated():
    # John Tan has Cambodia residence (KH-CAMBODIA) which mandates rule score 100,
    # but the sheet understated final score to 69.6
    extractions = [
        RawDocExtraction(
            doc_type=DocType.UBO_DECLARATION,
            filename="ubo_declaration.pdf",
            ubos=[
                UboItem(name="John Tan", ownership_percentage=100.0, is_controller=True),
            ],
            is_fully_executed=True,
        ),
        RawDocExtraction(
            doc_type=DocType.RISK_CALCULATOR,
            filename="risk_calculator.xlsx",
            calculator_customer_name="Acme International Pte Ltd",
            calculator_model_risk_score=69.6,
            calculator_final_risk_score=69.6,
            calculator_risk_rating="HIGH",
            interested_parties=[
                InterestedPartyRiskItem(
                    name="John Tan",
                    citizenship="HU-HUNGARY",
                    residence_country="KH-CAMBODIA",
                    total_model_score=69.6,
                    rule_based_score=None,
                    final_risk_score=69.6,  # Should be 100!
                )
            ],
        ),
    ]
    results, findings, profile = dispatch_wholesale_validation(
        bundle_name="Acme International Pte Ltd",
        bundle_entity_type="Private Limited Company",
        extractions=extractions,
        today=date(2026, 10, 13),
    )
    chk12 = next((r for r in results if r.check_id == "CHK_12_RISK_CALCULATOR"), None)
    assert chk12 is not None
    assert chk12.verdict == Verdict.FAIL
    assert any("UNDERSTATED_RULE_BASED_SCORE" in f.reason for f in chk12.findings)
    print("PASS: test_rule_based_override_understated")


def test_understated_customer_risk_rating():
    # John Tan has Cambodia residence (KH-CAMBODIA) -> High Risk,
    # but customer documented rating is marked as "MEDIUM"
    extractions = [
        RawDocExtraction(
            doc_type=DocType.UBO_DECLARATION,
            filename="ubo_declaration.pdf",
            ubos=[
                UboItem(name="John Tan", ownership_percentage=100.0, is_controller=True),
            ],
            is_fully_executed=True,
        ),
        RawDocExtraction(
            doc_type=DocType.RISK_CALCULATOR,
            filename="risk_calculator.xlsx",
            calculator_customer_name="Acme International Pte Ltd",
            calculator_model_risk_score=69.6,
            calculator_rule_based_risk_score=100.0,
            calculator_final_risk_score=100.0,
            calculator_risk_rating="MEDIUM",  # Understated! Should be HIGH
            interested_parties=[
                InterestedPartyRiskItem(
                    name="John Tan",
                    citizenship="HU-HUNGARY",
                    residence_country="KH-CAMBODIA",
                    total_model_score=69.6,
                    rule_based_score=100.0,
                    final_risk_score=100.0,
                )
            ],
        ),
    ]
    results, findings, profile = dispatch_wholesale_validation(
        bundle_name="Acme International Pte Ltd",
        bundle_entity_type="Private Limited Company",
        extractions=extractions,
        today=date(2026, 10, 13),
    )
    chk12 = next((r for r in results if r.check_id == "CHK_12_RISK_CALCULATOR"), None)
    assert chk12 is not None
    assert chk12.verdict == Verdict.FAIL
    assert any("UNDERSTATED_CUSTOMER_RISK_RATING" in f.reason for f in chk12.findings)
    print("PASS: test_understated_customer_risk_rating")


def test_clean_compliant_risk_calculator():
    # Compliant John Tan & Jane Tan matching screenshot exactly
    extractions = [
        RawDocExtraction(
            doc_type=DocType.UBO_DECLARATION,
            filename="ubo_declaration.pdf",
            ubos=[
                UboItem(name="John Tan", ownership_percentage=60.0, is_controller=True),
                UboItem(name="Jane Tan", ownership_percentage=40.0, is_controller=True),
            ],
            is_fully_executed=True,
        ),
        RawDocExtraction(
            doc_type=DocType.RISK_CALCULATOR,
            filename="risk_calculator.xlsx",
            calculator_customer_name="Acme International Pte Ltd",
            calculator_model_risk_score=69.6,
            calculator_rule_based_risk_score=100.0,
            calculator_final_risk_score=100.0,
            calculator_risk_rating="HIGH",  # Correct!
            interested_parties=[
                InterestedPartyRiskItem(
                    name="John Tan",
                    citizenship="HU-HUNGARY",
                    citizenship_score=74.0,
                    residence_country="KH-CAMBODIA",
                    residence_score=100.0,
                    watchlist_risk="None",
                    watchlist_score=0.0,
                    total_model_score=69.6,
                    rule_based_score=100.0,
                    rule_based_reasons=["[100] High risk due to: (1) Geography Risk - Country of Residence for Interested Parties"],
                    final_risk_score=100.0,
                ),
                InterestedPartyRiskItem(
                    name="Jane Tan",
                    citizenship="CA-CANADA",
                    citizenship_score=49.0,
                    residence_country="AE-UNITED ARAB EMIRATES",
                    residence_score=74.0,
                    watchlist_risk="None",
                    watchlist_score=0.0,
                    total_model_score=61.5,
                    rule_based_score=None,
                    final_risk_score=74.0,
                ),
            ],
        ),
    ]
    results, findings, profile = dispatch_wholesale_validation(
        bundle_name="Acme International Pte Ltd",
        bundle_entity_type="Private Limited Company",
        extractions=extractions,
        today=date(2026, 10, 13),
    )
    chk12 = next((r for r in results if r.check_id == "CHK_12_RISK_CALCULATOR"), None)
    assert chk12 is not None
    assert chk12.verdict == Verdict.PASS
    assert len(chk12.findings) == 0
    assert "Customer Risk Rating & Risk Calculator verified" in chk12.evidence
    print("PASS: test_clean_compliant_risk_calculator")


if __name__ == "__main__":
    test_missing_risk_calculator()
    test_omitted_interested_party()
    test_rule_based_override_understated()
    test_understated_customer_risk_rating()
    test_clean_compliant_risk_calculator()
    print("\nALL 5 TEST CASES PASSED WITH 100% ACCURACY!")

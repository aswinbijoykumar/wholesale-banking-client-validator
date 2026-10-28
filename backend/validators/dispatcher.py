"""Master Orchestrator / Dispatcher for Wholesale Banking Policies.

Implements Option B (Context Aggregator + Strategy Pattern) from breakdown.md:
  1. Aggregates and pre-filters documents into an immutable BundleContext.
  2. Runs modular domain sub-validators in logical sequence.
  3. Merges and returns (CheckResults, ValidationFindings, NormalizedCompanyProfile).
"""
from datetime import date
from typing import List, Tuple

from backend.models import (
    CheckResult,
    NormalizedCompanyProfile,
    RawDocExtraction,
    ValidationFinding,
)
from .context import BundleContext
from .rules import (
    RegistryAndFormationValidator,
    ConstitutionalAndMandateValidator,
    CorporateStructureValidator,
    IdentityAndAddressValidator,
    UboTransparencyValidator,
    RegulatoryQuestionnairesValidator,
    IngestionQualityValidator,
    MasRegulatoryValidator,
    RiskCalculatorValidator,
    DigitalFootprintValidator,
    TransactionReviewValidator,
)

CHECK_ORDER = [
    "CHK_01_BIZFILE",
    "CHK_02_INCORP",
    "CHK_03_CONST",
    "CHK_04_CORP_STRUCT",
    "CHK_05_ID_EXPIRY",
    "CHK_06_UBO_COMPLEX",
    "CHK_07_SANCTIONS",
    "CHK_08_INSTITUTIONAL",
    "CHK_09_CDD_EDD",
    "CHK_10_INGESTION_QUALITY",
    "CHK_11_MAS_REGISTER",
    "CHK_12_RISK_CALCULATOR",
    "CHK_13_DIGITAL_FOOTPRINT",
    "CHK_14_TRANSACTION_REVIEW",
]


def dispatch_wholesale_validation(
    bundle_name: str,
    bundle_entity_type: str,
    extractions: List[RawDocExtraction],
    today: date | None = None,
) -> Tuple[List[CheckResult], List[ValidationFinding], NormalizedCompanyProfile]:
    """Execute all modular sub-validators over the bundle and aggregate results."""
    if today is None:
        today = date.today()

    ctx = BundleContext(
        bundle_name=bundle_name,
        bundle_entity_type=bundle_entity_type,
        extractions=extractions,
        today=today,
    )

    all_results: List[CheckResult] = []
    all_findings: List[ValidationFinding] = []

    sub_validators = [
        RegistryAndFormationValidator,       # CHK_01_BIZFILE, CHK_02_INCORP
        ConstitutionalAndMandateValidator,    # CHK_03_CONST
        CorporateStructureValidator,          # CHK_04_CORP_STRUCT
        IdentityAndAddressValidator,          # CHK_05_ID_EXPIRY
        UboTransparencyValidator,             # CHK_06_UBO_COMPLEX
        RegulatoryQuestionnairesValidator,    # CHK_07_SANCTIONS, CHK_08_INSTITUTIONAL, CHK_09_CDD_EDD
        IngestionQualityValidator,            # CHK_10_INGESTION_QUALITY
        MasRegulatoryValidator,               # CHK_11_MAS_REGISTER
        RiskCalculatorValidator,              # CHK_12_RISK_CALCULATOR
        DigitalFootprintValidator,            # CHK_13_DIGITAL_FOOTPRINT
        TransactionReviewValidator,           # CHK_14_TRANSACTION_REVIEW
    ]

    for validator in sub_validators:
        res, fin = validator.validate(ctx)
        all_results.extend(res)
        all_findings.extend(fin)

    # Sort results and findings strictly by canonical check order
    order_map = {cid: idx for idx, cid in enumerate(CHECK_ORDER)}
    all_results.sort(key=lambda r: order_map.get(r.check_id, 999))
    all_findings.sort(key=lambda f: order_map.get(f.check_id, 999))

    return all_results, all_findings, ctx.profile

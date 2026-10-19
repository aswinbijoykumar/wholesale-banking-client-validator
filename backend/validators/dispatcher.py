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
    OwnershipAndStructureValidator,
    IdentityAndAddressValidator,
    RegulatoryQuestionnairesValidator,
    IngestionQualityValidator,
    MasRegulatoryValidator,
    RiskCalculatorValidator,
)


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
        OwnershipAndStructureValidator,       # CHK_04_CORP_STRUCT, CHK_06_UBO_COMPLEX
        IdentityAndAddressValidator,          # CHK_05_ID_EXPIRY
        RegulatoryQuestionnairesValidator,    # CHK_07_SANCTIONS, CHK_08_INSTITUTIONAL, CHK_09_CDD_EDD
        IngestionQualityValidator,            # CHK_10_INGESTION_QUALITY
        MasRegulatoryValidator,               # CHK_11_MAS_REGISTER
        RiskCalculatorValidator,              # CHK_12_RISK_CALCULATOR
    ]

    for validator in sub_validators:
        res, fin = validator.validate(ctx)
        all_results.extend(res)
        all_findings.extend(fin)

    return all_results, all_findings, ctx.profile

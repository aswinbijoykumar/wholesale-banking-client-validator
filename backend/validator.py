"""Deterministic Validation Engine for Wholesale Bank Policies.

Refactored to Option B (Context Aggregator + Strategy Pattern) as planned in `breakdown.md`.
This file preserves 100% backward-compatibility for callers (e.g. `backend/verifier.py`),
delegating to the modular `backend.validators` package.
"""
from datetime import date
from typing import List, Tuple

from .models import (
    CheckResult,
    NormalizedCompanyProfile,
    RawDocExtraction,
    ValidationFinding,
)
from .validators import (
    dispatch_wholesale_validation,
    parse_date_safe as _parse_date_safe,
    calculate_month_diff as _calculate_month_diff,
)


def validate_wholesale_bundle(
    bundle_name: str,
    bundle_entity_type: str,
    extractions: List[RawDocExtraction],
    today: date | None = None,
) -> Tuple[List[CheckResult], List[ValidationFinding], NormalizedCompanyProfile]:
    """Execute all wholesale banking validation checks over customer bundle.

    100% drop-in replacement maintaining exact signature and outputs.
    """
    return dispatch_wholesale_validation(
        bundle_name=bundle_name,
        bundle_entity_type=bundle_entity_type,
        extractions=extractions,
        today=today,
    )

# Architectural Breakdown & Refactoring Strategy for `validator.py`

## 1. Problem Statement
The current [`backend/validator.py`](file:///c:/Works/GLDB_Singapore/wholesale-banking-client-validator/backend/validator.py) is a single monolithic file of over **1,700 lines of code**. 

### Pain Points of the Current Structure:
1. **High Cognitive Load**: All 10 banking checks, cross-entity matching algorithms, text sanitizers, and profile normalization logic exist within a single procedural function (`validate_wholesale_bundle`).
2. **Merge Conflicts & Fragile Changes**: Multiple developers working on different compliance rules (e.g., someone modifying Sanctions while another updates UBO logic) touch the exact same lines of code.
3. **Hard to Unit Test in Isolation**: Testing a single rule (e.g., utility bill 90-day expiry in `CHK_05`) requires feeding a full bundle through 1,700 lines of unrelated rule logic.
4. **Duplicate Document Parsing**: Multiple checks repeatedly filter through the document extractions list for the same documents.

---

## 2. Refactoring Approaches & Architectural Suggestions

### Option A (User's Idea): Grouping by Shared Documents
Group rules together based on the primary documents they inspect:

| Modular Domain | Shared Input Documents | Covered Checks |
| :--- | :--- | :--- |
| **Registry & Formation** | ACRA BizFile, Certificate of Incorporation | `CHK_01_BIZFILE`, `CHK_02_INCORP` |
| **Constitutional Governance** | M&AA / Constitution, Register of Members (ROM), Board Resolution | `CHK_03_CONST` |
| **Ownership & Structure** | Register of Directors (ROD), ROM, GLDB UBO Declaration | `CHK_04_CORP_STRUCT`, `CHK_06_UBO_COMPLEX` |
| **Identity & Address (KYC)** | Passports, NRIC / National IDs, Proof of Address (Utility Bills) | `CHK_05_ID_EXPIRY` |
| **Regulatory & Questionnaires**| Sanctions Questionnaire, Wolfsberg CBDDQ, CDD/EDD Form | `CHK_07_SANCTIONS`, `CHK_08_INSTITUTIONAL`, `CHK_09_CDD_EDD` |
| **Ingestion Quality** | All submitted documents & translation certificates | `CHK_10_INGESTION_QUALITY` |

* **Pros**: Natural alignment with document upload streams; prevents re-reading and re-iterating over the same files multiple times.
* **Cons**: Some cross-cutting checks (e.g., comparing names on IDs with names in the BizFile or Board Resolution) span across document boundaries.

---

### Option B (Recommended Best Practice): "Context Aggregator + Strategy Pattern"
The cleanest, most maintainable software pattern for regulatory rule engines is the **Context Aggregator with Rule Strategies**:

```
                       ┌───────────────────────────────┐
                       │   Raw Extracted Documents    │
                       └──────────────┬────────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────────┐
                       │  BundleContext & Normalizer   │
                       │  - Pre-categorized doc lists  │
                       │  - Consolidated CompanyProfile│
                       └──────────────┬────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
      ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
      │   Registry    │       │   Ownership   │       │  Identity &   │
      │   Validator   │       │   Validator   │       │   KYC Rule    │
      └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      ▼
                       ┌───────────────────────────────┐
                       │   Aggregator & Dispatcher     │
                       │  - Combines all CheckResults  │
                       │  - Gathers ValidationFindings │
                       │  - Computes bundle roll-up    │
                       └───────────────────────────────┘
```

#### Why Option B is Better:
1. **Passes a Single Immutable `BundleContext`**: Pre-filters documents once (`ctx.bizfile_docs`, `ctx.id_docs`, `ctx.ubo_decl_docs`) and creates the canonical `NormalizedCompanyProfile`.
2. **Pluggable & Independent Rule Engines**: Each sub-validator implements a clean interface `validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]`.
3. **Zero Risk to Callers**: The external function signature `validate_wholesale_bundle(bundle_name, bundle_entity_type, extractions, today)` in [`backend/verifier.py`](file:///c:/Works/GLDB_Singapore/wholesale-banking-client-validator/backend/verifier.py) remains 100% untouched.

---

## 3. Proposed Package Directory Structure

Instead of one 1,700-line `backend/validator.py`, the validator becomes a clean Python package:

```
backend/
├── validator/                      # New modular package directory
│   ├── __init__.py                 # Re-exports validate_wholesale_bundle (drop-in compatible)
│   ├── context.py                  # BundleContext & NormalizedCompanyProfile builders
│   ├── base.py                     # Base Rule Validator abstract interface & common helpers
│   ├── rules/
│   │   ├── registry.py             # CHK_01 (BizFile) & CHK_02 (Incorp)
│   │   ├── constitutional.py       # CHK_03 (M&AA, ROM, Board Resolution, ID&V)
│   │   ├── structure.py            # CHK_04 (ROD/Controllers) & CHK_06 (UBO/Bearer Shares)
│   │   ├── identity.py             # CHK_05 (Passports, Utility Bills, Expiry, Fraud)
│   │   ├── questionnaires.py       # CHK_07 (Sanctions), CHK_08 (Wolfsberg), CHK_09 (CDD/EDD)
│   │   └── quality.py              # CHK_10 (OCR >=85%, DPI >=200, Translations, CTC)
│   └── dispatcher.py               # Loops over validators, merges findings, returns tuple
```

---

## 4. Writeup of `validator_breakdown.py` (Architecture Blueprint)

Below is the design and writeup of the proposed modular breakdown script. It illustrates how the classes and dispatcher cleanly separate concerns while maintaining 100% backward compatibility:

```python
"""Modular Architecture Blueprint for validator_breakdown.py

Demonstrates how to split validator.py into modular domain classes
grouped by shared document types and compliance scopes.
"""
from datetime import date
from typing import List, Tuple
from dateutil import parser as date_parser

from .models import (
    CheckResult,
    DocType,
    EntityType,
    ItemizedDocStatus,
    NormalizedCompanyProfile,
    Priority,
    RawDocExtraction,
    ValidationFinding,
    Verdict,
)

# -------------------------------------------------------------------------
# 1. SHARED CONTEXT & HELPERS
# -------------------------------------------------------------------------
class BundleContext:
    """Pre-segments documents once so individual rules do not duplicate filtering loops."""
    def __init__(self, bundle_name: str, bundle_entity_type: str, extractions: List[RawDocExtraction], today: date):
        self.bundle_name = bundle_name
        self.bundle_entity_type = bundle_entity_type
        self.extractions = extractions
        self.today = today

        # Document grouping by shared types
        self.bizfile_docs = [e for e in extractions if e.doc_type == DocType.BIZFILE]
        self.incorp_docs = [e for e in extractions if e.doc_type == DocType.CERT_INCORPORATION]
        self.maa_docs = [e for e in extractions if e.doc_type == DocType.MAA]
        self.rom_docs = [e for e in extractions if e.doc_type == DocType.ROM]
        self.rod_docs = [e for e in extractions if e.doc_type == DocType.ROD]
        self.board_docs = [e for e in extractions if e.doc_type == DocType.BOARD_RESOLUTION]
        self.ubo_decl_docs = [e for e in extractions if e.doc_type == DocType.UBO_DECLARATION]
        self.id_docs = [e for e in extractions if e.doc_type == DocType.ID_DOCUMENT]
        self.poa_docs = [e for e in extractions if e.doc_type == DocType.PROOF_OF_ADDRESS]
        self.sanction_docs = [e for e in extractions if e.doc_type == DocType.SANCTION_QUESTIONNAIRE]
        self.institutional_docs = [e for e in extractions if e.doc_type == DocType.INSTITUTIONAL_QUESTIONNAIRE]
        self.cdd_docs = [e for e in extractions if e.doc_type == DocType.CDD_EDD_QUESTIONNAIRE]

        # Canonical Profile
        self.profile = NormalizedCompanyProfile(entity_type=bundle_entity_type or EntityType.PVT_LTD.value)
        self._populate_profile()

    def _populate_profile(self):
        # Extracts legal_name, uen, directors, ubos, etc. into canonical self.profile
        ...


# -------------------------------------------------------------------------
# 2. DOMAIN SUB-VALIDATOR 1: Registry & Formation (BizFile + Incorp Docs)
# -------------------------------------------------------------------------
class RegistryAndFormationValidator:
    """Evaluates:
       - CHK_01_BIZFILE: Freshness (<=12 months), Live/Active company status, operating address.
       - CHK_02_INCORP: Certificate of Incorporation, Legal Name, UEN, Incorporation Date.
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Evaluates ctx.bizfile_docs and ctx.incorp_docs
        # Appends CHK_01 and CHK_02 results & findings
        return results, findings


# -------------------------------------------------------------------------
# 3. DOMAIN SUB-VALIDATOR 2: Constitutional Governance (M&AA + ROM + Board)
# -------------------------------------------------------------------------
class ConstitutionalGovernanceValidator:
    """Evaluates:
       - CHK_03_CONST: Certified True Copy (CTC) stamps on M&AA and ROM,
         proper execution of Board Resolutions, and Signatory Mandate ID&V.
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Evaluates ctx.maa_docs, ctx.rom_docs, ctx.board_docs
        return results, findings


# -------------------------------------------------------------------------
# 4. DOMAIN SUB-VALIDATOR 3: Ownership Structure (ROD + ROM + UBO Declaration)
# -------------------------------------------------------------------------
class OwnershipStructureValidator:
    """Evaluates:
       - CHK_04_CORP_STRUCT: Directorship additions/removals via ROD, key controllers.
       - CHK_06_UBO_COMPLEX: GLDB UBO Form execution, >=25% equity verification,
         undisclosed nominee/bearer share detection, and source of wealth plausibility.
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Evaluates ctx.rod_docs, ctx.ubo_decl_docs, ctx.rom_docs
        return results, findings


# -------------------------------------------------------------------------
# 5. DOMAIN SUB-VALIDATOR 4: Identity & Proof of Address (Passports + Bills)
# -------------------------------------------------------------------------
class IdentityAndAddressValidator:
    """Evaluates:
       - CHK_05_ID_EXPIRY: ID document expiry vs today, 90-day utility bill recency,
         exact name/address matching between ID & bill, and fraudulent template watermarks.
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Evaluates ctx.id_docs and ctx.poa_docs
        return results, findings


# -------------------------------------------------------------------------
# 6. DOMAIN SUB-VALIDATOR 5: Regulatory Questionnaires (Sanctions + Wolfsberg + CDD)
# -------------------------------------------------------------------------
class RegulatoryQuestionnairesValidator:
    """Evaluates:
       - CHK_07_SANCTIONS: SCF department code matching and strategic dual-use goods screening.
       - CHK_08_INSTITUTIONAL: Wolfsberg CBDDQ recency (<=12m) and critical AML answer inspection.
       - CHK_09_CDD_EDD: Singapore Nexus, tax havens/CRS, continuation rationale (>=30 words),
         and 100% 3-tier governance sign-offs (RM Maker, KYC Approver, Senior Approver).
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Evaluates ctx.sanction_docs, ctx.institutional_docs, ctx.cdd_docs
        return results, findings


# -------------------------------------------------------------------------
# 7. DOMAIN SUB-VALIDATOR 6: Ingestion Quality & Translations
# -------------------------------------------------------------------------
class IngestionQualityValidator:
    """Evaluates:
       - CHK_10_INGESTION_QUALITY: Image DPI (>=200), OCR confidence (>=85%),
         CTC professional attestation details, and certified sworn translations.
    """
    @staticmethod
    def validate(ctx: BundleContext) -> Tuple[List[CheckResult], List[ValidationFinding]]:
        results, findings = [], []
        # Inspects ctx.extractions across all submitted files
        return results, findings


# -------------------------------------------------------------------------
# 8. MASTER DISPATCHER: Seamless Drop-in Replacement
# -------------------------------------------------------------------------
def validate_wholesale_bundle(
    bundle_name: str,
    bundle_entity_type: str,
    extractions: List[RawDocExtraction],
    today: date | None = None,
) -> Tuple[List[CheckResult], List[ValidationFinding], NormalizedCompanyProfile]:
    """Preserves the exact existing signature so backend/verifier.py requires NO modifications."""
    if today is None:
        today = date.today()

    ctx = BundleContext(bundle_name, bundle_entity_type, extractions, today)

    sub_validators = [
        RegistryAndFormationValidator,
        ConstitutionalGovernanceValidator,
        OwnershipStructureValidator,
        IdentityAndAddressValidator,
        RegulatoryQuestionnairesValidator,
        IngestionQualityValidator,
    ]

    all_results: List[CheckResult] = []
    all_findings: List[ValidationFinding] = []

    for validator in sub_validators:
        r, f = validator.validate(ctx)
        all_results.extend(r)
        all_findings.extend(f)

    return all_results, all_findings, ctx.profile
```

---

## 5. How This Breakdown Solves Your Requirements

1. **Shared Document Grouping**:
   - `CHK_01` and `CHK_02` share ACRA BizFiles & Incorporation documents $\rightarrow$ handled in one module.
   - `CHK_04` and `CHK_06` share ROD, ROM, and UBO declarations $\rightarrow$ handled in one module.
   - `CHK_05` handles passports and proof of address bills $\rightarrow$ isolated in one module.
   - `CHK_07`, `CHK_08`, and `CHK_09` handle regulatory questionnaires $\rightarrow$ isolated in one module.
2. **Maintains 100% Intact Logic**:
   - The orchestrator in [`backend/verifier.py`](file:///c:/Works/GLDB_Singapore/wholesale-banking-client-validator/backend/verifier.py) continues calling `validate_wholesale_bundle(...)` with the exact same inputs and outputs.
3. **Drastic Code Reduction**:
   - Instead of reading 1,732 continuous lines, each file is ~150–250 lines with dedicated single responsibilities.
4. **Isolated Testability**:
   - Unit tests can mock just a `BundleContext` with 2 documents to test `IdentityAndAddressValidator` without executing 9 other unrelated checks.

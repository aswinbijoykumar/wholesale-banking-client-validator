"""Wholesale Banking Policy Verification Rules Definitions.

Covers Descriptions 1, 2, 3, 4, 5, and 6:
- CHK_01_BIZFILE    : Latest Official Registry Extract (ACRA BizFile / COI)
- CHK_02_INCORP     : Relevant Incorporation Documentation
- CHK_03_CONST      : Constitutional Documentation & Certified True Copy (CTC)
- CHK_04_CORP_STRUCT: Corporate Structure, Directorship & UBO Changes + ID CTC Verification
- CHK_05_ID_EXPIRY  : Expiry Verification of Identity Documents & Proof of Address
- CHK_06_UBO_COMPLEX: Nominee Arrangements, Bearer Shares & Complex Structure Risk Evaluation
"""

RULES = [
    {
        "id": "CHK_01_BIZFILE",
        "flag": "Official Registry Extract Validity",
        "process_step": "Registry Validation",
        "severity": "High",
        "applies_to": ["bizfile"],
        "description": "Confirm latest official registry extract (ACRA BizFile) confirms current ownership, directorship, status, and is within 12 months.",
        "fail_when": (
            "BizFile is missing, older than 12 months from today, company status is inactive/struck off, "
            "or directorship/ownership cannot be verified."
        ),
    },
    {
        "id": "CHK_02_INCORP",
        "flag": "Incorporation Documentation Review",
        "process_step": "Legal Identity Review",
        "severity": "High",
        "applies_to": ["cert_incorporation", "bizfile"],
        "description": "Confirm relevant incorporation documentation is on file with full legal name, former names, UEN, inc date, and country of operations.",
        "fail_when": (
            "Incorporation doc is missing, or UEN / incorporation date / legal name is missing or inconsistent."
        ),
    },
    {
        "id": "CHK_03_CONST",
        "flag": "Constitutional Documentation & CTC Review",
        "process_step": "Constitutional Governance",
        "severity": "High",
        "applies_to": ["maa", "rom", "board_resolution"],
        "description": "Confirm M&AA, Register of Members (ROM), and Board Resolution are on file and verified as Certified True Copies (CTC).",
        "fail_when": (
            "M&AA or ROM is missing, board resolution missing/unexecuted where applicable, or documents lack Certified True Copy (CTC) stamps."
        ),
    },
    {
        "id": "CHK_04_CORP_STRUCT",
        "flag": "Corporate Structure & Key Controllers Review",
        "process_step": "Structure & Ownership Verification",
        "severity": "High",
        "applies_to": ["rod", "rom", "bizfile", "id_document"],
        "description": "Identify additions/removals to directorship & beneficial ownership via Register of Directors (ROD), confirm UBO percentages & key controllers, and verify ID documents are Certified True Copies (CTC).",
        "fail_when": (
            "Register of Directors (ROD) is missing, unverified UBOs or controllers without shareholding breakdown, structure changes unverified, or director/UBO IDs lack Certified True Copy (CTC) verification."
        ),
    },
    {
        "id": "CHK_05_ID_EXPIRY",
        "flag": "ID & Proof of Address Validity Review",
        "process_step": "Identity Expiry Verification",
        "severity": "High",
        "applies_to": ["id_document", "proof_of_address"],
        "description": "Ensure all identification documents (passports, national IDs) and proof of address are not expired (or have approved exception on file).",
        "fail_when": (
            "Any identification document or proof of address is expired without verified exceptional approval on file."
        ),
    },
    {
        "id": "CHK_06_UBO_COMPLEX",
        "flag": "Nominee, Bearer Share & Complex Structure Risk Review",
        "process_step": "UBO Declaration & Risk Governance",
        "severity": "High",
        "applies_to": ["ubo_declaration", "rom", "bizfile"],
        "description": "Confirm if nominee / bearer share arrangements or complex multi-layered ownership structures exist via UBO Declaration (e.g. GLDB Declaration), align ownership with company files, and rate complex structures as High Risk with stated rationale.",
        "fail_when": (
            "GLDB UBO Declaration is missing, ownership structure is misaligned across files, bearer shares or nominee arrangements are unclarified, or complex multi-layer structure lacks documented legitimate business purpose (defaulted to High Risk)."
        ),
    },
]

RULES_BY_ID = {r["id"]: r for r in RULES}

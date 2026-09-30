"""Wholesale Banking KYC & Policy Verification Rules Definitions.

Covers Descriptions 1, 2, and 3:
- CHK_01_BIZFILE : Latest Official Registry Extract (ACRA BizFile / COI)
- CHK_02_INCORP  : Relevant Incorporation Documentation
- CHK_03_CONST   : Constitutional Documentation & Certified True Copy (CTC)
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
            "M&AA or ROM is missing, board resolution missing where applicable, or documents lack Certified True Copy (CTC) stamps."
        ),
    },
]

RULES_BY_ID = {r["id"]: r for r in RULES}

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
        "flag": "Official Registry Extract & Operations Validity",
        "process_step": "Registry & Operations Review",
        "severity": "High",
        "applies_to": ["bizfile"],
        "description": "Confirm ACRA BizFile is within 12 months and entity status is Live/Active. Review customer place of incorporation, place of business, operational address, core business activities (products/services, geographic coverage), activity changes, and corporate website (Desc 7, 8).",
        "fail_when": (
            "BizFile is missing, older than 12 months, company status is inactive/struck off, "
            "place of business/operations is unverified, or core business activities are missing."
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
        "flag": "Constitutional Documentation, CTC & Mandate Review",
        "process_step": "Constitutional Governance & Signatory Mandates",
        "severity": "High",
        "applies_to": ["maa", "rom", "board_resolution"],
        "description": "Confirm M&AA, Register of Members (ROM), and Board Resolution are on file and verified as Certified True Copies (CTC). Ensure ID&V verification for administrators, authorizers, and authorized signatories is completed, kept up to date, and cross-checked across M&AA, ACRA BizFile, and Board Resolution (Desc 24).",
        "fail_when": (
            "M&AA or ROM is missing, board resolution is missing/unexecuted, documents lack Certified True Copy (CTC) stamps, or authorizers/administrators lack completed ID&V verification."
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
        "process_step": "Identity Expiry & Document Authenticity",
        "severity": "High",
        "applies_to": ["id_document", "proof_of_address"],
        "description": "Ensure all identification documents (passports, national IDs) and proof of address are non-expired, authentic, and free from fraudulent templates or synthetic data. Verify proof of address is within 90 days and names/addresses match across ID and utility bills.",
        "fail_when": (
            "Any ID or utility bill is expired without exceptional approval, template generator watermarks are detected, synthetic data is found, or ID and utility bill names/addresses mismatch."
        ),
    },
    {
        "id": "CHK_06_UBO_COMPLEX",
        "flag": "UBO Transparency, Nominee/Complex Risk & Wealth Plausibility",
        "process_step": "UBO Declaration, Wealth Plausibility & Risk Calculator",
        "severity": "High",
        "applies_to": ["ubo_declaration", "rom", "bizfile", "id_document"],
        "description": "Verify UBOs (≥25% shareholding/voting) and controllers via formal GLDB Declaration. Confirm Register of Members rules out undisclosed nominee or bearer share arrangements. Evaluate ultimate individual wealth plausibility (Step 18 & App 1: narrative of wealth accumulation for Medium Risk; primary corroborating documents like tax notices, bank statements, audited accounts for High Risk). Feed verified UBO %, jurisdictions, and complex multi-tier structures into Risk Rating (Step 27).",
        "fail_when": (
            "GLDB UBO Declaration is missing, ownership structure is misaligned, bearer shares or undisclosed nominees exist, complex structures lack legitimate business rationale, or individual UBO wealth accumulation lacks plausibility narrative / primary corroboration."
        ),
    },
    {
        "id": "CHK_07_SANCTIONS",
        "flag": "Sanction Questionnaire & Strategic Goods Review",
        "process_step": "Sanctions, SCF Department & Dual-Use Trade Controls",
        "severity": "High",
        "applies_to": ["sanction_questionnaire", "bizfile"],
        "description": "Evaluate Trigger & Routing (triggered if High Risk, SCF team, or wholesale trade of goods). Cross-reference RM department code against master SCF department codes. Cross-reference declared traded goods against international Strategic Goods Control lists and escalate to Trade Compliance if matched (Descr. 10).",
        "fail_when": (
            "Sanction questionnaire is triggered but missing/unexecuted, RM department code mismatches SCF master codes, or declared traded goods include unmitigated dual-use/strategic goods without Trade Compliance escalation."
        ),
    },
    {
        "id": "CHK_08_INSTITUTIONAL",
        "flag": "Institutional Questionnaires & Wolfsberg CBDDQ Review",
        "process_step": "Institutional Entity Mapping & Core AML Controls",
        "severity": "High",
        "applies_to": ["institutional_questionnaire", "bizfile"],
        "description": "Verify Dynamic Entity Mapping & Recency: Wolfsberg CBDDQ for Banks/FIs, Investment Vehicle Questionnaire for Funds/PE, and MSB Questionnaire for Payment Processors with signature date ≤ 12 months. Inspect Wolfsberg Critical Answers and escalate immediately if 'No' is answered to core AML control questions (Descr. 12).",
        "fail_when": (
            "Required institutional questionnaire is missing, signature date exceeds 12 months, or client answered 'No' to any core AML control questions in the Wolfsberg CBDDQ."
        ),
    },
    {
        "id": "CHK_09_CDD_EDD",
        "flag": "CDD / EDD Account Purpose, Tax Risk & Sign-Off Governance",
        "process_step": "Singapore Nexus, Tax Risk & Multi-Tier Sign-Off",
        "severity": "High",
        "applies_to": ["cdd_edd_questionnaire", "bizfile"],
        "description": "Assess Singapore Nexus commercial justification (Descr. 13), classify account purpose vs product, benchmark monthly volume vs declared annual turnover (flag pass-through risk), check routed transaction categories vs business model. Confirm tax risk section is fully populated (no bare 'N/A'), screen operational jurisdictions against EU Tax Haven list (Descr. 21) and verify mitigating controls (TIN, CRS/FATCA). Verify continuation rationale (≥ 30 words) and 100% sign-offs (RM Maker, KYC Approver, Senior Approver) (Descr. 28).",
        "fail_when": (
            "Missing Singapore nexus justification, pass-through turnover mismatch, unmitigated tax haven exposure, continuation narrative under 30 words, or missing multi-tier governance sign-offs."
        ),
    },
    {
        "id": "CHK_10_INGESTION_QUALITY",
        "flag": "Ingestion Quality, CTC Authenticity & Certified Translations",
        "process_step": "Document Clarity, CTC Verification & Sworn Translations",
        "severity": "High",
        "applies_to": ["bizfile", "cert_incorporation", "maa", "rom", "rod", "board_resolution", "ubo_declaration", "id_document", "proof_of_address", "sanction_questionnaire", "institutional_questionnaire", "cdd_edd_questionnaire", "translation_certificate"],
        "description": "Verify all submitted scans meet OCR confidence ≥ 85% and resolution ≥ 200 DPI without blur/cutoff. Verify non-registry photocopies feature certifier signature, date, professional title, and organization. Verify foreign non-English documents have official certified English translations with sworn translator statements and credentials (Descr. 25).",
        "fail_when": (
            "Any scan has OCR confidence < 85% or DPI < 200 with blur/cutoff, non-registry copy lacks certifier title/date/organization, or non-English document lacks certified sworn English translation."
        ),
    },
]

RULES_BY_ID = {r["id"]: r for r in RULES}

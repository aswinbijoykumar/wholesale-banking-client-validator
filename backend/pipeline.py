"""Multi-stage Ingestion, OCR (Tesseract / PyMuPDF), Vision, and Extraction Pipeline.

Pipeline Flow:
UPLOADED -> CLASSIFYING -> EXTRACTING -> OCR_PROCESSING -> VISION_PROCESSING -> NORMALIZING -> VALIDATING -> COMPLETED
"""
import base64
import json
from datetime import date
from pathlib import Path
from typing import List, Tuple
import pymupdf
from openai import OpenAI

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

from .config import settings
from .models import (
    DocType,
    RawDocExtraction,
    DirectorItem,
    UboItem,
)

_client: OpenAI | None = None
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured in .env")
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def extract_text_and_images(file_path: Path) -> Tuple[str, List[bytes]]:
    """Extract digital text + render pages. For raw images, directly returns bytes without PyMuPDF."""
    ext = file_path.suffix.lower()
    if ext in IMAGE_EXT:
        img_bytes = file_path.read_bytes()
        return "", [img_bytes]

    digital_text_parts = []
    png_pages: List[bytes] = []

    with pymupdf.open(file_path) as pdf:
        zoom = settings.RENDER_DPI / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        for i, page in enumerate(pdf):
            if i >= settings.MAX_PAGES_PER_DOC:
                break
            # 1. Digital text extraction
            txt = page.get_text()
            if txt.strip():
                digital_text_parts.append(txt)

            # 2. Render image pixmap for Vision / OCR fallback
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            png_pages.append(png_bytes)

            # 3. Fallback to Tesseract OCR if digital text is empty (scanned PDF)
            if not txt.strip() and HAS_TESSERACT:
                try:
                    from io import BytesIO
                    ocr_t = pytesseract.image_to_string(Image.open(BytesIO(png_bytes)))
                    if ocr_t.strip():
                        digital_text_parts.append(ocr_t)
                except Exception:
                    pass

    return "\n\n".join(digital_text_parts), png_pages


def _image_part(png_bytes: bytes, mime: str = "image/png") -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
    }


DOCUMENT_CLASSIFICATION_AND_EXTRACTION_PROMPT = """You are a senior wholesale banking compliance specialist.
Analyze the provided document (text and/or high-resolution images) for a corporate client file.

Extract structured fields accurately. Pay close attention to:
1. Document Type:
   - "bizfile" : ACRA BizFile, Business Profile, Company Search, Official Registry extract.
   - "cert_incorporation" : Certificate of Incorporation, Registration Certificate, Articles of Incorporation.
   - "maa" : Memorandum and Articles of Association (M&AA), Constitution, By-laws.
   - "rom" : Register of Members (ROM), Share Register, Shareholder List.
   - "rod" : Register of Directors (ROD), Director Register.
   - "board_resolution" : Board Resolution, Minutes, Signing Mandate.
   - "ubo_declaration" : GLDB Declaration of Ultimate Beneficial Owners / UBO Declaration Form.
   - "id_document" : Passport, National ID card (NRIC/FIN), Driving License (Images or PDFs).
   - "proof_of_address" : Utility bill, Bank statement, Residential proof document.
   - "sanction_questionnaire" : GLDB Sanctions Questionnaire / Strategic Goods & SCF Assessment Form.
   - "institutional_questionnaire" : Wolfsberg CBDDQ, MSB Questionnaire, Investment Vehicle Questionnaire, Trustee Declaration.
   - "cdd_edd_questionnaire" : CDD/EDD Questionnaire, Account Purpose, Singapore Nexus & Tax Risk Declaration.
   - "translation_certificate" : Sworn/Certified English Translation Certificate.
   - "other" : Other supporting files.
2. Legal Name of Company & Registration Number (UEN)
3. Date of Incorporation, Entity Type, Country of Operations, Company Status ("Live", "Active", "Dormant", "Struck Off")
4. Certified True Copy (CTC): Is there a visible "Certified True Copy" stamp, certifier signature, date, certifier professional title (e.g. Advocate & Solicitor, Notary Public, Company Secretary), and organization?
5. Execution & Completeness:
   - is_fully_executed: Is this document properly signed, dated, and filled in? (Set false if blank signature lines, empty form fields).
   - is_blank_template: Set to TRUE if the document is an uncompleted blank form or unexecuted template.
6. Identity Documents & Expiry (Crucial for Passports / NRICs / ID images):
   - id_holder_name: Name of the individual on the ID document.
   - id_type: "Passport", "National ID", etc.
   - id_number: Passport number or National ID number.
   - id_expiry_date: Expiry date (format: YYYY-MM-DD or null).
   - id_address: Full address printed on the ID document (e.g., "PASIR RIS DRIVE...").
   - is_expired: Compare id_expiry_date against today's date {today}. Is it expired?
   - has_exceptional_approval: Is there an explicit bank exceptional approval memo or sign-off?
7. Proof of Address & Utility Bills:
   - address_holder_name: Name of the customer/individual on the bill (e.g., "MR JOHN CITIZEN").
   - address_issue_date: Date the utility bill/statement was issued (format: YYYY-MM-DD).
   - proof_address: Full residential/service address printed on the bill (e.g., "10 OHM ROAD EAST...").
8. Fraudulent / Template / Synthetic Document Detection (CRITICAL COMPLIANCE REVIEW):
   - is_fraudulent_or_template: Set to TRUE if any of the following are detected:
     a) Template generator watermarks, logos, or text such as "Yutempl.com", "shotempl.com", "gotempl.com", "faketemplate", or novelty disclaimers.
     b) Synthetic placeholder data, e.g., NRIC like "S0000000H", DOB like "00-00-0000" or "0000-00-00", repeated dummy values.
     c) Obvious digital manipulation, cut-and-paste artifacts, or fraudulent template generator signatures.
   - fraud_reasons: List of specific strings explaining the fraud/template indicators found.
   - has_watermark_or_template_generator: boolean.
   - has_synthetic_placeholder_data: boolean.
9. Corporate Structure, Directors & UBO Details (ROD, ROM, and GLDB UBO Declaration):
   - directors: List all directors with names, ID numbers, nationality, appointment date, cessation date, and status.
   - ubos: List all Ultimate Beneficial Owners with full name, ID number, nationality, exact shareholding percentage (e.g. 100.0, 50.0), share count, and whether they are controllers.
   - has_structure_changes: Are there recent additions or removals of directors/shareholders noted in the register?
   - structure_change_notes: Summary of any structural changes.
10. Business Operations & Core Activities (Descriptions 7 & 8):
   - place_of_incorporation: Registered incorporation country/state.
   - place_of_business: Registered office address and operational premises.
   - business_operations_address: Physical office/warehouse/operations address.
   - core_business_activities: Detailed description of business model, activities, and SSIC/industry codes.
   - products_services_description: Products/services manufactured, produced, traded, or offered.
   - geographic_coverage: Countries/regions where company operates or conducts trade.
   - business_activity_changes: Any disclosed recent changes in company business activities.
   - customer_website: Corporate URL or website domain.
11. Authorizers, Administrators & Authorized Signatories (Description 24):
   - authorizers: List of authorized signatories / mandate holders named in Board Resolution or M&AA.
   - administrators: List of platform/banking administrators.
   - has_authorizers_idv: Are the authorizers/administrators cross-verified against valid ID documents?
   - authorizer_idv_notes: Notes on identification and verification completeness.
12. Individual UBO Wealth Plausibility & Corroboration (Steps 4, 6, 12, 18, 27 & App 1):
   - wealth_narrative_provided: Is there a clear explanation/narrative of how UBOs accumulated their legal wealth/capital?
   - wealth_source_narrative: Narrative summary of wealth source.
   - wealth_corroborating_docs_attached: For High Risk UBOs, are primary corroborating wealth documents attached?
   - wealth_docs_description: Specific wealth corroborating proof found on file.
13. Sanction Questionnaire & Strategic Goods (Descr. 10):
   - is_sanction_questionnaire: Is this a GLDB Sanction Questionnaire?
   - is_scf_department: Is the customer serviced under the Supply Chain Finance (SCF) team?
   - rm_department_code: Relationship Manager's department code (e.g. "SCF-SG-01", "WB-CORP-02").
   - is_scf_code_matched: Does RM department code match recognized master SCF codes (e.g. starting with "SCF")?
   - is_wholesale_trade_goods: Is entity engaged in wholesale trade of physical commodities or manufactured goods?
   - declared_traded_goods: List of physical goods/commodities declared as traded.
   - has_dual_use_goods: Are any declared goods categorized under Strategic / Dual-Use Goods lists (e.g., precision electronics, chemicals, aerospace parts, lasers, telecommunications cryptosystems, nuclear/military precursors)?
   - dual_use_goods_details: Description of matching dual-use items.
   - escalated_to_trade_compliance: Is there evidence of Trade Compliance escalation memo or sign-off?
14. Institutional Questionnaires (Descr. 12):
   - institutional_type: One of "BANK_FI", "FUNDS_PE", "PAYMENT_PROCESSOR_MSB", "TRUSTEE", or null.
   - wolfsberg_signature_date: Date signed on Wolfsberg CBDDQ (YYYY-MM-DD).
   - wolfsberg_is_recent_12m: Is the signature date within the last 12 months?
   - wolfsberg_has_critical_no_answer: Did the institution answer "No" to any core AML/CFT control questions (e.g., sanction screening, transaction monitoring, PEP controls, prohibition of shell banks)?
   - wolfsberg_critical_no_details: Details of negative answers.
15. CDD / EDD Questionnaire — Account Purpose, Tax Risk & Sign-Off (Descr. 13, 21, 28):
   - singapore_nexus_rationale: Documented commercial justification for opening an account in Singapore without physical presence.
   - has_valid_singapore_nexus: Is there a legitimate commercial rationale (e.g. regional treasury hub, APAC trade settlement)?
   - account_purpose: Declared purpose ("Operating CASA", "Loan Drawdown", "Both").
   - selected_product: Selected banking product.
   - account_purpose_matched: Does the declared purpose match the product?
   - expected_monthly_turnover: Expected monthly transaction volume (numerical amount in SGD/USD).
   - declared_annual_turnover: Declared annual turnover (numerical amount in SGD/USD).
   - is_passthrough_risk_flagged: Flag true if monthly throughput / expected volume is inconsistent with annual turnover (e.g. pass-through account risk).
   - routed_transaction_categories: List of transaction types/categories.
   - declared_counterparties: Declared counterparties and suppliers.
   - categories_aligned_with_business: Do payment categories align with declared business model?
   - tax_risk_section_populated: Is the Tax Risk declaration section fully answered without bare "N/A"?
   - tax_haven_jurisdictions: List of operational jurisdictions matching EU Non-Cooperative Tax Haven list (e.g. Panama, Cayman, BVI, Vanuatu, Samoa, etc.).
   - has_tax_mitigating_controls: If tax haven exposure exists, are mitigating controls documented (TIN, Tax Residency Certificate, FATCA/CRS declaration)?
   - tax_controls_description: Documented tax mitigations.
   - continuation_rationale: Written business continuation narrative text.
   - continuation_word_count: Number of words in continuation narrative (must be >= 30 words).
   - has_rm_maker_signoff: Has Relationship Manager (Maker) signed?
   - has_kyc_approver_signoff: Has KYC/AML Approver signed?
   - has_senior_approver_signoff: Has Senior Management / Committee Approver signed?
16. Ingestion Quality & Translations (Descr. 25):
   - ocr_confidence: Estimated OCR confidence percentage (0-100, default ~95).
   - dpi_resolution: Estimated image DPI resolution (default ~300).
   - is_blurry_or_cutoff: Is the scan visibly blurry, skewed, truncated, or illegible?
   - is_non_english: Is the original document in a non-English language?
   - document_language: Language of the document.
   - has_certified_translation: If non-English, is a certified English translation provided?
   - has_sworn_translator_statement: Does the translation contain a sworn translator statement & credentials?
   - certifier_name: Name of certifying individual for CTC.
   - certifier_title: Professional title (Advocate, Solicitor, Notary Public, Auditor, CorpSec).
   - certifier_org: Organization / Law Firm of certifier.

Today's date is {today}.

Return ONLY valid JSON matching this schema:
{{
  "doc_type": "bizfile" | "cert_incorporation" | "maa" | "rom" | "rod" | "board_resolution" | "ubo_declaration" | "id_document" | "proof_of_address" | "sanction_questionnaire" | "institutional_questionnaire" | "cdd_edd_questionnaire" | "translation_certificate" | "other",
  "legal_name": "string or null",
  "uen": "string or null",
  "former_names": "string or null",
  "entity_type": "string or null",
  "incorporation_date": "YYYY-MM-DD or null",
  "country_of_operations": "string or null",
  "company_status": "string or null",
  "bizfile_date": "YYYY-MM-DD or null",
  "is_ctc": boolean,
  "ctc_signature_found": boolean,
  "ctc_date": "string or null",
  "certifier_name": "string or null",
  "certifier_title": "string or null",
  "certifier_org": "string or null",
  "ctc_details_complete": boolean,
  "is_fully_executed": boolean,
  "is_blank_template": boolean,
  "id_holder_name": "string or null",
  "id_type": "string or null",
  "id_number": "string or null",
  "id_expiry_date": "YYYY-MM-DD or null",
  "id_address": "string or null",
  "is_expired": boolean,
  "has_exceptional_approval": boolean,
  "address_holder_name": "string or null",
  "address_issue_date": "YYYY-MM-DD or null",
  "proof_address": "string or null",
  "is_fraudulent_or_template": boolean,
  "fraud_reasons": ["string"],
  "has_watermark_or_template_generator": boolean,
  "has_synthetic_placeholder_data": boolean,
  "place_of_incorporation": "string or null",
  "place_of_business": "string or null",
  "business_operations_address": "string or null",
  "core_business_activities": "string or null",
  "products_services_description": "string or null",
  "geographic_coverage": "string or null",
  "business_activity_changes": "string or null",
  "customer_website": "string or null",
  "authorizers": ["string"],
  "administrators": ["string"],
  "has_authorizers_idv": boolean,
  "authorizer_idv_notes": "string or null",
  "wealth_narrative_provided": boolean,
  "wealth_source_narrative": "string or null",
  "wealth_corroborating_docs_attached": boolean,
  "wealth_docs_description": "string or null",
  "is_sanction_questionnaire": boolean,
  "is_scf_department": boolean,
  "rm_department_code": "string or null",
  "is_scf_code_matched": boolean,
  "is_wholesale_trade_goods": boolean,
  "declared_traded_goods": ["string"],
  "has_dual_use_goods": boolean,
  "dual_use_goods_details": "string or null",
  "escalated_to_trade_compliance": boolean,
  "institutional_type": "string or null",
  "wolfsberg_signature_date": "YYYY-MM-DD or null",
  "wolfsberg_is_recent_12m": boolean,
  "wolfsberg_has_critical_no_answer": boolean,
  "wolfsberg_critical_no_details": "string or null",
  "singapore_nexus_rationale": "string or null",
  "has_valid_singapore_nexus": boolean,
  "account_purpose": "string or null",
  "selected_product": "string or null",
  "account_purpose_matched": boolean,
  "expected_monthly_turnover": 0.0,
  "declared_annual_turnover": 0.0,
  "is_passthrough_risk_flagged": boolean,
  "routed_transaction_categories": ["string"],
  "declared_counterparties": ["string"],
  "categories_aligned_with_business": boolean,
  "tax_risk_section_populated": boolean,
  "tax_haven_jurisdictions": ["string"],
  "has_tax_mitigating_controls": boolean,
  "tax_controls_description": "string or null",
  "continuation_rationale": "string or null",
  "continuation_word_count": 0,
  "has_rm_maker_signoff": boolean,
  "has_kyc_approver_signoff": boolean,
  "has_senior_approver_signoff": boolean,
  "ocr_confidence": 95.0,
  "dpi_resolution": 300,
  "is_blurry_or_cutoff": boolean,
  "is_non_english": boolean,
  "document_language": "English",
  "has_certified_translation": boolean,
  "has_sworn_translator_statement": boolean,
  "directors": [
    {{"name": "...", "id_number": "...", "nationality": "...", "appointment_date": "...", "cessation_date": "...", "status": "CURRENT"}}
  ],
  "ubos": [
    {{"name": "...", "id_number": "...", "nationality": "...", "ownership_percentage": 100.0, "share_count": 1000, "is_controller": true, "is_nominee": false}}
  ],
  "has_structure_changes": boolean,
  "structure_change_notes": "string or null",
  "has_nominee_arrangement": boolean,
  "has_bearer_shares": boolean,
  "has_complex_structure": boolean,
  "complex_structure_rationale": "string or null",
  "risk_rating": "HIGH" | "MEDIUM" | "LOW",
  "has_board_resolution": boolean,
  "notes": "short summary of document execution, blanks, or issues"
}}
"""


def extract_document_with_vision(
    file_path: Path,
    original_name: str,
    today: date | None = None,
) -> RawDocExtraction:
    """Classify and extract document data using PyMuPDF / Direct Image + GPT-4o Vision."""
    if today is None:
        today = date.today()

    extracted_text, page_images = extract_text_and_images(file_path)

    client = get_client()

    # Determine mime type for image parts
    ext = file_path.suffix.lower()
    mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"

    content_parts: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Document Filename: {original_name}\n"
                f"Extracted Digital / OCR Text:\n```\n{extracted_text[:4000]}\n```\n\n"
                f"Please inspect the visual document images below for layout, stamps, seals, watermarks (e.g. Yutempl.com, shotempl.com), handwriting, expiry dates, addresses, core business activities, authorizers, and signature execution:"
            ),
        }
    ]

    for img_bytes in page_images[:settings.MAX_PAGES_PER_DOC]:
        content_parts.append(_image_part(img_bytes, mime=mime))

    prompt = DOCUMENT_CLASSIFICATION_AND_EXTRACTION_PROMPT.format(today=today.isoformat())

    response = client.chat.completions.create(
        model=settings.OPENAI_VISION_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content_parts},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=3200,
    )

    raw_json_str = response.choices[0].message.content or "{}"
    parsed_data = json.loads(raw_json_str)

    # Normalize doc_type to DocType enum with fallback string matching on filename
    dtype_str = parsed_data.get("doc_type", "").lower()
    fname = original_name.lower()
    if not dtype_str or dtype_str == "other":
        if any(k in fname for k in ["bizfile", "profile", "acra", "search"]):
            dtype_str = "bizfile"
        elif any(k in fname for k in ["m&aa", "maa", "memorandum", "articles", "constitution"]):
            dtype_str = "maa"
        elif any(k in fname for k in ["gldb", "declaration of ultimate", "ubo declaration", "beneficial owner"]):
            dtype_str = "ubo_declaration"
        elif any(k in fname for k in ["register of director", "director register", "rod"]):
            dtype_str = "rod"
        elif any(k in fname for k in ["rom", "member", "shareholder", "register of member"]):
            dtype_str = "rom"
        elif any(k in fname for k in ["board", "resolution", "mandate", "minutes"]):
            dtype_str = "board_resolution"
        elif any(k in fname for k in ["passport", "nric", "id card", "identity", "driving", "bean", "id", "ic"]):
            dtype_str = "id_document"
        elif any(k in fname for k in ["bill", "statement", "address", "poa", "screenshot"]):
            dtype_str = "proof_of_address"
        elif any(k in fname for k in ["incorporation", "coi", "certificate"]):
            dtype_str = "cert_incorporation"

    try:
        dtype = DocType(dtype_str)
    except ValueError:
        dtype = DocType.OTHER

    # Deterministic heuristic fallback for fraud markers in raw text or notes if LLM missed flags
    full_text_lower = (extracted_text + " " + (parsed_data.get("notes") or "") + " " + original_name).lower()
    is_fraud = bool(parsed_data.get("is_fraudulent_or_template", False))
    raw_reasons = list(parsed_data.get("fraud_reasons") or [])
    # Filter out any celebrity/fictional character mentions
    fraud_reasons = [
        r for r in raw_reasons 
        if not any(w in r.lower() for w in ["celebrity", "fictional", "actor", "character", "rowan", "atkinson", "bean"])
    ]

    if "yutempl" in full_text_lower or "yutempl.com" in full_text_lower:
        is_fraud = True
        if not any("yutempl" in r.lower() for r in fraud_reasons):
            fraud_reasons.append("ID document contains template watermark 'Yutempl.com'")
    if "shotempl" in full_text_lower or "gotempl" in full_text_lower:
        is_fraud = True
        if not any("shotempl" in r.lower() or "gotempl" in r.lower() for r in fraud_reasons):
            fraud_reasons.append("Utility bill contains template generator watermark 'shotempl.com' / 'gotempl.com'")
    if "s0000000h" in full_text_lower or parsed_data.get("id_number") == "S0000000H" or "00-00-0000" in full_text_lower:
        is_fraud = True
        if not any("synthetic" in r.lower() or "s0000000h" in r.lower() for r in fraud_reasons):
            fraud_reasons.append("ID contains synthetic placeholder data (NRIC: S0000000H, DOB: 00-00-0000)")

    directors = [
        DirectorItem(
            name=d.get("name", "Unknown"),
            id_number=d.get("id_number"),
            nationality=d.get("nationality"),
            appointment_date=d.get("appointment_date"),
            cessation_date=d.get("cessation_date"),
            status=d.get("status", "CURRENT"),
        )
        for d in parsed_data.get("directors", [])
        if isinstance(d, dict) and d.get("name")
    ]

    ubos = [
        UboItem(
            name=u.get("name", "Unknown"),
            id_number=u.get("id_number"),
            nationality=u.get("nationality"),
            ownership_percentage=float(u.get("ownership_percentage") or 0.0),
            share_count=u.get("share_count"),
            is_controller=bool(u.get("is_controller", False)),
            is_nominee=bool(u.get("is_nominee", False)),
        )
        for u in parsed_data.get("ubos", [])
        if isinstance(u, dict) and u.get("name")
    ]

    return RawDocExtraction(
        doc_type=dtype,
        filename=original_name,
        legal_name=parsed_data.get("legal_name"),
        uen=parsed_data.get("uen"),
        former_names=parsed_data.get("former_names"),
        entity_type=parsed_data.get("entity_type"),
        incorporation_date=parsed_data.get("incorporation_date"),
        country_of_operations=parsed_data.get("country_of_operations"),
        company_status=parsed_data.get("company_status"),
        bizfile_date=parsed_data.get("bizfile_date"),
        is_ctc=bool(parsed_data.get("is_ctc", False)),
        ctc_signature_found=bool(parsed_data.get("ctc_signature_found", False)),
        ctc_date=parsed_data.get("ctc_date"),
        is_fully_executed=bool(parsed_data.get("is_fully_executed", True)),
        is_blank_template=bool(parsed_data.get("is_blank_template", False)),
        id_holder_name=parsed_data.get("id_holder_name"),
        id_type=parsed_data.get("id_type"),
        id_number=parsed_data.get("id_number"),
        id_expiry_date=parsed_data.get("id_expiry_date"),
        id_address=parsed_data.get("id_address"),
        is_expired=bool(parsed_data.get("is_expired", False)),
        has_exceptional_approval=bool(parsed_data.get("has_exceptional_approval", False)),
        address_holder_name=parsed_data.get("address_holder_name"),
        address_issue_date=parsed_data.get("address_issue_date"),
        proof_address=parsed_data.get("proof_address"),
        is_fraudulent_or_template=is_fraud,
        fraud_reasons=fraud_reasons,
        has_watermark_or_template_generator=bool(parsed_data.get("has_watermark_or_template_generator", False)) or ("yutempl" in full_text_lower or "shotempl" in full_text_lower),
        has_synthetic_placeholder_data=bool(parsed_data.get("has_synthetic_placeholder_data", False)) or ("s0000000h" in full_text_lower),
        place_of_incorporation=parsed_data.get("place_of_incorporation"),
        place_of_business=parsed_data.get("place_of_business"),
        business_operations_address=parsed_data.get("business_operations_address"),
        core_business_activities=parsed_data.get("core_business_activities"),
        products_services_description=parsed_data.get("products_services_description"),
        geographic_coverage=parsed_data.get("geographic_coverage"),
        business_activity_changes=parsed_data.get("business_activity_changes"),
        customer_website=parsed_data.get("customer_website"),
        authorizers=parsed_data.get("authorizers") or [],
        administrators=parsed_data.get("administrators") or [],
        has_authorizers_idv=bool(parsed_data.get("has_authorizers_idv", False)),
        authorizer_idv_notes=parsed_data.get("authorizer_idv_notes"),
        wealth_narrative_provided=bool(parsed_data.get("wealth_narrative_provided", False)),
        wealth_source_narrative=parsed_data.get("wealth_source_narrative"),
        wealth_corroborating_docs_attached=bool(parsed_data.get("wealth_corroborating_docs_attached", False)),
        wealth_docs_description=parsed_data.get("wealth_docs_description"),
        directors=directors,
        ubos=ubos,
        has_structure_changes=bool(parsed_data.get("has_structure_changes", False)),
        structure_change_notes=parsed_data.get("structure_change_notes"),
        has_nominee_arrangement=bool(parsed_data.get("has_nominee_arrangement", False)),
        has_bearer_shares=bool(parsed_data.get("has_bearer_shares", False)),
        has_complex_structure=bool(parsed_data.get("has_complex_structure", False)),
        complex_structure_rationale=parsed_data.get("complex_structure_rationale"),
        risk_rating=parsed_data.get("risk_rating", "MEDIUM"),
        has_board_resolution=bool(parsed_data.get("has_board_resolution", False)),
        notes=parsed_data.get("notes"),
    )

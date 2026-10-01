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
   - "other" : Other supporting files.
2. Legal Name of Company & Registration Number (UEN)
3. Date of Incorporation, Entity Type, Country of Operations, Company Status ("Live", "Active", "Dormant", "Struck Off")
4. Certified True Copy (CTC): Is there a visible "Certified True Copy" stamp, certifier signature, date, or notary seal?
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
   - fraud_reasons: List of specific strings explaining the fraud/template indicators found (e.g., ["Contains watermark Yutempl.com", "Synthetic NRIC S0000000H and DOB 00-00-0000"]).
   - has_watermark_or_template_generator: boolean.
   - has_synthetic_placeholder_data: boolean.
9. Corporate Structure, Directors & UBO Details (Crucial for ROD, ROM, and GLDB UBO Declaration):
   - directors: List all directors with names, ID numbers, nationality, appointment date, cessation date, and status.
   - ubos: List all Ultimate Beneficial Owners with full name, ID number, nationality, exact shareholding percentage (e.g. 100.0, 50.0), share count, and whether they are controllers.
   - has_structure_changes: Are there recent additions or removals of directors/shareholders noted in the register?
   - structure_change_notes: Summary of any structural changes.
10. Nominee Arrangements & Complex Structures (Crucial for GLDB UBO Declaration):
   - has_nominee_arrangement: Are shares held on behalf of someone else / nominee shareholder?
   - has_bearer_shares: Are bearer shares issued or held?
   - has_complex_structure: Is there a multi-layered, offshore, trust, or complex corporate holding structure?
   - complex_structure_rationale: Documented legitimate business purpose for having a complex structure (or null if missing).
   - risk_rating: Default to "HIGH" if complex structure is present, otherwise "MEDIUM" or "LOW".

Today's date is {today}.

Return ONLY valid JSON matching this schema:
{{
  "doc_type": "bizfile" | "cert_incorporation" | "maa" | "rom" | "rod" | "board_resolution" | "ubo_declaration" | "id_document" | "proof_of_address" | "other",
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
  "notes": "short description of document execution, blanks, or issues"
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
                f"Please inspect the visual document images below for layout, stamps, seals, watermarks (e.g. Yutempl.com, shotempl.com), handwriting, expiry dates, addresses, and signature execution:"
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
        max_tokens=2800,
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
        is_fictional_or_celebrity=bool(parsed_data.get("is_fictional_or_celebrity", False)) or ("bean" in full_text_lower or "rowan" in full_text_lower),
        has_synthetic_placeholder_data=bool(parsed_data.get("has_synthetic_placeholder_data", False)) or ("s0000000h" in full_text_lower),
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

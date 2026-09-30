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
    """Extract digital text via PyMuPDF + render pages as PNG bytes."""
    ext = file_path.suffix.lower()
    if ext in IMAGE_EXT:
        img_bytes = file_path.read_bytes()
        ocr_text = ""
        if HAS_TESSERACT:
            try:
                ocr_text = pytesseract.image_to_string(Image.open(file_path))
            except Exception:
                ocr_text = ""
        return ocr_text, [img_bytes]

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


def _image_part(png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
    }


DOCUMENT_CLASSIFICATION_AND_EXTRACTION_PROMPT = """You are a senior wholesale banking KYC compliance specialist.
Analyze the provided document (text and/or page images) for a corporate client file.

Extract the structured fields accurately. Pay close attention to:
1. Document Type:
   - "bizfile" : ACRA BizFile, Company Search, Official Registry extract, or Certificate of Good Standing / Info.
   - "cert_incorporation" : Certificate of Incorporation, Registration Certificate, or Articles of Incorporation.
   - "maa" : Memorandum and Articles of Association (M&AA), Constitution, or By-laws.
   - "rom" : Register of Members (ROM), Share Register, or Shareholder list.
   - "board_resolution" : Board Resolution, Minutes, or Signing Mandate.
   - "other" : Other supporting files.
2. Legal Name of Company (exact character spelling)
3. Business Registration Number (UEN)
4. Former Names (if any)
5. Entity Type (e.g. Private Limited Company, Public Listed Company, Partnership, Sole Proprietor, Foreign Corporation)
6. Date of Incorporation (format: YYYY-MM-DD if possible)
7. Country of Operations / Incorporation (e.g. Singapore)
8. Company Status (e.g. "Live Company", "Active", "Dormant", "Struck Off", "Ceased")
9. BizFile Issue/Print Date (Date the registry search/extract was pulled)
10. Certified True Copy (CTC): Is there a visible "Certified True Copy" stamp, certifier signature, date, or notary seal?
11. Directorship & UBO details: List names, IDs, nationality, and ownership percentages.

Today's date is {today}.

Return ONLY valid JSON matching this schema:
{{
  "doc_type": "bizfile" | "cert_incorporation" | "maa" | "rom" | "board_resolution" | "other",
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
  "directors": [
    {{"name": "...", "id_number": "...", "nationality": "...", "appointment_date": "...", "status": "CURRENT"}}
  ],
  "ubos": [
    {{"name": "...", "id_number": "...", "ownership_percentage": 100.0, "share_count": 1000, "is_controller": true}}
  ],
  "has_board_resolution": boolean,
  "notes": "short description of findings"
}}
"""


def extract_document_with_vision(
    file_path: Path,
    original_name: str,
    today: date | None = None,
) -> RawDocExtraction:
    """Classify and extract document data using PyMuPDF + Tesseract + GPT-4o Vision."""
    if today is None:
        today = date.today()

    extracted_text, page_images = extract_text_and_images(file_path)

    client = get_client()

    content_parts: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Document Filename: {original_name}\n"
                f"Extracted Digital / OCR Text:\n```\n{extracted_text[:4000]}\n```\n\n"
                f"Please inspect the visual page images below for layout, stamps, seals, and handwriting:"
            ),
        }
    ]

    # Add up to MAX_PAGES_PER_DOC images
    for img_bytes in page_images[:settings.MAX_PAGES_PER_DOC]:
        content_parts.append(_image_part(img_bytes))

    prompt = DOCUMENT_CLASSIFICATION_AND_EXTRACTION_PROMPT.format(today=today.isoformat())

    response = client.chat.completions.create(
        model=settings.OPENAI_VISION_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content_parts},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=2500,
    )

    raw_json_str = response.choices[0].message.content or "{}"
    parsed_data = json.loads(raw_json_str)

    # Normalize doc_type to DocType enum
    dtype_str = parsed_data.get("doc_type", "other").lower()
    try:
        dtype = DocType(dtype_str)
    except ValueError:
        dtype = DocType.OTHER

    directors = [
        DirectorItem(
            name=d.get("name", "Unknown"),
            id_number=d.get("id_number"),
            nationality=d.get("nationality"),
            appointment_date=d.get("appointment_date"),
            status=d.get("status", "CURRENT"),
        )
        for d in parsed_data.get("directors", [])
        if isinstance(d, dict) and d.get("name")
    ]

    ubos = [
        UboItem(
            name=u.get("name", "Unknown"),
            id_number=u.get("id_number"),
            ownership_percentage=float(u.get("ownership_percentage") or 0.0),
            share_count=u.get("share_count"),
            is_controller=bool(u.get("is_controller", False)),
        )
        for u in parsed_data.get("ubos", [])
        if isinstance(u, dict) and u.get("name")
    ]

    return RawDocExtraction(
        doc_type=dtype,
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
        directors=directors,
        ubos=ubos,
        has_board_resolution=bool(parsed_data.get("has_board_resolution", False)),
        notes=parsed_data.get("notes"),
    )

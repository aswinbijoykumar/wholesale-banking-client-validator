"""Pydantic schemas and models for Wholesale Bank Document Ingestion and Verification."""
from datetime import date
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PVT_LTD = "Private Limited Company"
    PUBLIC_LISTED = "Public Listed Company"
    PARTNERSHIP = "Partnership"
    SOLE_PROPRIETOR = "Sole Proprietor"
    FOREIGN_CORP = "Foreign Corporation"


class DocType(str, Enum):
    BIZFILE = "bizfile"
    CERT_INCORPORATION = "cert_incorporation"
    MAA = "maa"
    ROM = "rom"
    ROD = "rod"                              # Register of Directors
    BOARD_RESOLUTION = "board_resolution"
    UBO_DECLARATION = "ubo_declaration"      # GLDB Declaration of UBOs
    ID_DOCUMENT = "id_document"              # Passport / NRIC / ID Image or PDF
    PROOF_OF_ADDRESS = "proof_of_address"    # Utility bill / bank statement
    OTHER = "other"


class ProcessingState(str, Enum):
    UPLOADED = "UPLOADED"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    OCR_PROCESSING = "OCR_PROCESSING"
    VISION_PROCESSING = "VISION_PROCESSING"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --- Extraction Models ---

class DirectorItem(BaseModel):
    name: str = Field(description="Full name of director")
    id_number: Optional[str] = Field(default=None, description="NRIC/FIN/Passport number")
    nationality: Optional[str] = Field(default=None, description="Nationality")
    appointment_date: Optional[str] = Field(default=None, description="Date of appointment (YYYY-MM-DD or raw)")
    cessation_date: Optional[str] = Field(default=None, description="Date of cessation/removal if any")
    status: str = Field(default="CURRENT", description="Current, Appointed, or Resigned/Removed")


class UboItem(BaseModel):
    name: str = Field(description="Full name of UBO/Shareholder")
    id_number: Optional[str] = Field(default=None, description="ID or registration number")
    nationality: Optional[str] = Field(default=None, description="Nationality")
    ownership_percentage: Optional[float] = Field(default=0.0, description="Percentage of shareholding")
    share_count: Optional[int] = Field(default=None, description="Number of shares held")
    is_controller: bool = Field(default=False, description="Whether person exercises ultimate effective control")
    is_nominee: bool = Field(default=False, description="Whether held under nominee arrangement")


class RawDocExtraction(BaseModel):
    doc_type: DocType
    filename: Optional[str] = None
    legal_name: Optional[str] = None
    uen: Optional[str] = None
    former_names: Optional[str] = None
    entity_type: Optional[str] = None
    incorporation_date: Optional[str] = None
    country_of_operations: Optional[str] = None
    company_status: Optional[str] = None  # e.g., 'Live Company', 'Active', 'Struck Off'
    bizfile_date: Optional[str] = None    # Date extract was generated/printed
    is_ctc: bool = False                  # Certified True Copy stamp/signature detected
    ctc_signature_found: bool = False
    ctc_date: Optional[str] = None
    is_fully_executed: bool = True        # Is document signed, dated, and completed (not blank template)
    is_blank_template: bool = False       # True if form has unfilled blanks, placeholders, or missing signatures
    
    # ID / Proof of Address specific fields
    id_holder_name: Optional[str] = None
    id_type: Optional[str] = None         # Passport, National ID, Driving License
    id_number: Optional[str] = None
    id_expiry_date: Optional[str] = None  # YYYY-MM-DD
    is_expired: bool = False
    has_exceptional_approval: bool = False
    address_holder_name: Optional[str] = None
    address_issue_date: Optional[str] = None
    
    # Structure & UBO Declaration specific fields
    directors: List[DirectorItem] = Field(default_factory=list)
    ubos: List[UboItem] = Field(default_factory=list)
    has_structure_changes: bool = False   # Recent additions/removals of directors or shareholders
    structure_change_notes: Optional[str] = None
    has_nominee_arrangement: bool = False
    has_bearer_shares: bool = False
    has_complex_structure: bool = False
    complex_structure_rationale: Optional[str] = None
    risk_rating: Optional[str] = None     # "HIGH", "MEDIUM", "LOW"
    
    has_board_resolution: bool = False
    notes: Optional[str] = None


class NormalizedCompanyProfile(BaseModel):
    legal_name: Optional[str] = None
    uen: Optional[str] = None
    former_names: Optional[str] = None
    entity_type: str = EntityType.PVT_LTD.value
    incorporation_date: Optional[str] = None
    country_of_operations: Optional[str] = None
    company_status: Optional[str] = None
    bizfile_date: Optional[str] = None
    is_bizfile_fresh_12m: bool = False
    directors: List[DirectorItem] = Field(default_factory=list)
    ubos: List[UboItem] = Field(default_factory=list)
    has_nominee_arrangement: bool = False
    has_bearer_shares: bool = False
    has_complex_structure: bool = False
    complex_structure_rationale: Optional[str] = None
    risk_rating: str = "MEDIUM"


# --- Itemized Document Evaluation Models ---

class ItemizedDocStatus(BaseModel):
    doc_name: str
    doc_type: str
    verdict: Verdict
    details: str
    reason: Optional[str] = None
    is_ctc: bool = False


class ValidationFinding(BaseModel):
    check_id: str
    finding_type: str
    severity: Priority
    missing_document: Optional[str] = None
    reason: str
    target_field: Optional[str] = None
    details: str


class CheckResult(BaseModel):
    check_id: str
    rule_name: str
    verdict: Verdict
    reason_code: Optional[str] = None
    priority: Priority
    evidence: str
    evaluated_files: List[ItemizedDocStatus] = Field(default_factory=list)
    findings: List[ValidationFinding] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    bundle_id: str
    run_id: str
    overall_verdict: Verdict
    summary: str
    results: List[CheckResult]
    findings: List[ValidationFinding]

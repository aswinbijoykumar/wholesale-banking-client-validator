"""Pydantic schemas and models for Wholesale Banking Document Ingestion and Verification."""
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
    BOARD_RESOLUTION = "board_resolution"
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
    status: str = Field(default="CURRENT", description="Current or resigned")


class UboItem(BaseModel):
    name: str = Field(description="Full name of UBO/Shareholder")
    id_number: Optional[str] = Field(default=None, description="ID or registration number")
    ownership_percentage: Optional[float] = Field(default=0.0, description="Percentage of shareholding")
    share_count: Optional[int] = Field(default=None, description="Number of shares held")
    is_controller: bool = Field(default=False, description="Whether person exercises ultimate effective control")


class RawDocExtraction(BaseModel):
    doc_type: DocType
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
    directors: List[DirectorItem] = Field(default_factory=list)
    ubos: List[UboItem] = Field(default_factory=list)
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


# --- Finding & Result Models ---

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
    findings: List[ValidationFinding] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    bundle_id: str
    run_id: str
    overall_verdict: Verdict
    summary: str
    results: List[CheckResult]
    findings: List[ValidationFinding]

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
    SANCTION_QUESTIONNAIRE = "sanction_questionnaire"          # GLDB Internal Sanction Questionnaire
    INSTITUTIONAL_QUESTIONNAIRE = "institutional_questionnaire"  # Wolfsberg CBDDQ, MSB, Funds, Trustee Declaration
    CDD_EDD_QUESTIONNAIRE = "cdd_edd_questionnaire"            # Account Purpose, Tax Risk & Sign-Off
    TRANSLATION_CERTIFICATE = "translation_certificate"        # Certified English Translation Certificate
    RISK_CALCULATOR = "risk_calculator"                        # GLDB Internal Risk Calculator Sheet
    TRANSACTION_LISTING = "transaction_listing"                # Past 6-Month Transaction Listing & RM Review
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
    id_address: Optional[str] = None
    
    # Proof of Address & Fraud/Template Detection
    address_holder_name: Optional[str] = None
    address_issue_date: Optional[str] = None
    proof_address: Optional[str] = None
    is_fraudulent_or_template: bool = False
    fraud_reasons: List[str] = Field(default_factory=list)
    has_watermark_or_template_generator: bool = False
    is_fictional_or_celebrity: bool = False
    has_synthetic_placeholder_data: bool = False
    
    # Business Activity, Operations & Online Presence (Desc 7 & 8)
    place_of_incorporation: Optional[str] = None
    place_of_business: Optional[str] = None
    business_operations_address: Optional[str] = None
    core_business_activities: Optional[str] = None
    products_services_description: Optional[str] = None
    geographic_coverage: Optional[str] = None
    business_activity_changes: Optional[str] = None
    customer_website: Optional[str] = None
    
    # Authorizers & Administrators ID&V (Desc 24)
    authorizers: List[str] = Field(default_factory=list)
    administrators: List[str] = Field(default_factory=list)
    has_authorizers_idv: bool = False
    authorizer_idv_notes: Optional[str] = None
    
    # Wealth Plausibility & UBO Corroboration (Desc 18 & App 1)
    wealth_narrative_provided: bool = False
    wealth_source_narrative: Optional[str] = None
    wealth_corroborating_docs_attached: bool = False
    wealth_docs_description: Optional[str] = None

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
    
    # --- 6. Sanction Questionnaire (Descr. 10) ---
    is_sanction_questionnaire: bool = False
    is_scf_department: bool = False
    rm_department_code: Optional[str] = None
    is_scf_code_matched: bool = False
    is_wholesale_trade_goods: bool = False
    declared_traded_goods: List[str] = Field(default_factory=list)
    has_dual_use_goods: bool = False
    dual_use_goods_details: Optional[str] = None
    escalated_to_trade_compliance: bool = False
    sanction_questionnaire_executed: bool = True
    
    # --- 8. Institutional Questionnaires (Descr. 12) ---
    institutional_type: Optional[str] = None  # "BANK_FI", "FUNDS_PE", "PAYMENT_PROCESSOR_MSB", "TRUSTEE"
    wolfsberg_signature_date: Optional[str] = None
    wolfsberg_is_recent_12m: bool = True
    wolfsberg_has_critical_no_answer: bool = False
    wolfsberg_critical_no_details: Optional[str] = None
    wolfsberg_escalated_compliance: bool = False
    
    # --- 9. CDD / EDD Questionnaire (Descr. 13, 21, 28) ---
    singapore_nexus_rationale: Optional[str] = None
    has_valid_singapore_nexus: bool = True
    account_purpose: Optional[str] = None  # "Operating CASA", "Loan Drawdown", "Both"
    selected_product: Optional[str] = None
    account_purpose_matched: bool = True
    expected_monthly_turnover: Optional[float] = None
    declared_annual_turnover: Optional[float] = None
    is_passthrough_risk_flagged: bool = False
    routed_transaction_categories: List[str] = Field(default_factory=list)
    declared_counterparties: List[str] = Field(default_factory=list)
    categories_aligned_with_business: bool = True
    tax_risk_section_populated: bool = True
    tax_haven_jurisdictions: List[str] = Field(default_factory=list)
    has_tax_mitigating_controls: bool = True
    tax_controls_description: Optional[str] = None  # TIN, Tax Residency Cert, CRS/FATCA
    continuation_rationale: Optional[str] = None
    continuation_word_count: int = 0
    has_rm_maker_signoff: bool = True
    has_kyc_approver_signoff: bool = True
    has_senior_approver_signoff: bool = True
    all_signoffs_completed: bool = True

    # --- 13. Ingestion Quality & Translations (Descr. 25) ---
    ocr_confidence: float = 95.0
    dpi_resolution: int = 300
    is_blurry_or_cutoff: bool = False
    is_non_english: bool = False
    document_language: Optional[str] = "English"
    has_certified_translation: bool = True
    has_sworn_translator_statement: bool = True
    certifier_name: Optional[str] = None
    certifier_title: Optional[str] = None
    certifier_org: Optional[str] = None
    ctc_details_complete: bool = True

    has_board_resolution: bool = False
    notes: Optional[str] = None

    # --- 14. Risk Calculator Specific Fields ---
    is_risk_calculator: bool = False
    calculator_customer_name: Optional[str] = None
    calculator_model_risk_score: Optional[float] = None
    calculator_rule_based_risk_score: Optional[float] = None
    calculator_final_risk_score: Optional[float] = None
    calculator_risk_rating: Optional[str] = None
    calculator_rule_reasons: List[str] = Field(default_factory=list)
    interested_parties: List["InterestedPartyRiskItem"] = Field(default_factory=list)

    # --- 15. Past 6-Month Transaction Listing Fields ---
    is_transaction_listing: bool = False
    transaction_records: List["TransactionRecord"] = Field(default_factory=list)
    rm_review_records: List["RmReviewMonthlyItem"] = Field(default_factory=list)


class TransactionRecord(BaseModel):
    customer_key: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_key: Optional[str] = None
    transaction_key: Optional[str] = None
    transact_date: Optional[date] = None
    transact_datetime: Optional[str] = None
    transaction_type: Optional[str] = None
    transact_currency: Optional[str] = "SGD"
    credit_transact_amount: float = 0.0
    debit_transact_amount: float = 0.0
    home_currency: Optional[str] = "SGD"
    credit_home_amount: float = 0.0
    debit_home_amount: float = 0.0
    counterparty_account_no: Optional[str] = None
    counterparty_name: Optional[str] = None
    description: Optional[str] = None
    value_date: Optional[date] = None
    segment: Optional[str] = None
    counterparty_bank1: Optional[str] = None
    counterparty_bank2: Optional[str] = None
    payment_detail: Optional[str] = None


class RmReviewMonthlyItem(BaseModel):
    month_year: str = Field(description="YYYY-MM format e.g. 2026-05")
    account_key: Optional[str] = None
    currency: str = "SGD"
    reported_inflow_amount: float = 0.0
    reported_outflow_amount: float = 0.0
    reported_inflow_count: int = 0
    reported_outflow_count: int = 0


class MonthlyTransactionSummary(BaseModel):
    month_year: str  # YYYY-MM
    account_key: str
    currency: str
    inflow_count: int = 0
    inflow_home_amount: float = 0.0
    outflow_count: int = 0
    outflow_home_amount: float = 0.0
    net_home_flow: float = 0.0


class TransactionListingProfile(BaseModel):
    is_provided: bool = False
    filename: Optional[str] = None
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None
    lookback_days: int = 0
    has_full_6m_lookback: bool = False
    total_transactions_count: int = 0
    monthly_summaries: List[MonthlyTransactionSummary] = Field(default_factory=list)
    average_monthly_inflow: float = 0.0
    average_monthly_outflow: float = 0.0
    turnover_variance_pct: Optional[float] = None
    is_dormant_detected: bool = False
    dormant_months: List[str] = Field(default_factory=list)
    is_spike_detected: bool = False
    spike_months: List[str] = Field(default_factory=list)
    rm_reconciliation_pass: bool = True
    rm_discrepancies: List[str] = Field(default_factory=list)


class InterestedPartyRiskItem(BaseModel):
    name: str = Field(description="Name of individual interested party / UBO")
    citizenship: Optional[str] = Field(default=None, description="Country of citizenship (e.g. HU-HUNGARY)")
    citizenship_score: Optional[float] = Field(default=None, description="Score for citizenship")
    residence_country: Optional[str] = Field(default=None, description="Country of residence (e.g. KH-CAMBODIA)")
    residence_score: Optional[float] = Field(default=None, description="Score for residence country")
    watchlist_risk: Optional[str] = Field(default="None", description="Watchlist status e.g. None, PEP, Sanction")
    watchlist_score: Optional[float] = Field(default=0.0, description="Watchlist risk score")
    total_model_score: Optional[float] = Field(default=None, description="Total Model Risk Score")
    rule_based_score: Optional[float] = Field(default=None, description="Rule Based Risk Score floor e.g. 100")
    rule_based_reasons: List[str] = Field(default_factory=list, description="Reasons for rule based override")
    final_risk_score: Optional[float] = Field(default=None, description="Final Individual Risk Score")


class RiskCalculatorProfile(BaseModel):
    is_provided: bool = False
    filename: Optional[str] = None
    customer_name: Optional[str] = None
    corporate_age_years: Optional[float] = None
    corporate_age_score: Optional[float] = None
    entity_watchlist_score: Optional[float] = None
    hq_country: Optional[str] = None
    hq_country_score: Optional[float] = None
    operations_country: Optional[str] = None
    operations_score: Optional[float] = None
    account_type: Optional[str] = None
    account_type_score: Optional[float] = None
    industry_ssic: Optional[str] = None
    industry_ssic_score: Optional[float] = None
    listing_status: Optional[str] = None
    listing_status_score: Optional[float] = None
    channel_method: Optional[str] = None
    channel_score: Optional[float] = None
    distance_to_bo_layers: Optional[int] = None
    distance_to_bo_score: Optional[float] = None
    connected_party_aggregate_score: Optional[float] = None
    parties: List[InterestedPartyRiskItem] = Field(default_factory=list)
    overall_model_score: Optional[float] = None
    rule_based_override_score: Optional[float] = None
    rule_based_reasons: List[str] = Field(default_factory=list)
    final_customer_risk_score: Optional[float] = None
    final_customer_risk_rating: Optional[str] = None  # LOW, MEDIUM, HIGH


class MasVerificationProfile(BaseModel):
    is_fi_nbfi: bool = False
    search_name_used: str = ""
    mas_profile_url: Optional[str] = None
    is_found_on_mas: bool = False
    licence_type: Optional[str] = None
    licence_status: Optional[str] = None  # "Current", "Active", "Ceased", "Suspended"
    country_of_incorporation: Optional[str] = None
    incorporation_date: Optional[str] = None
    key_personnel: List[dict] = Field(default_factory=list)  # [{"role": "Chief Executive", "name": "..."}]
    registered_address: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    raw_notes: Optional[str] = None


class DigitalFootprintProfile(BaseModel):
    target_url: str = ""
    domain: str = ""
    is_live: bool = False
    http_status: Optional[int] = None
    website_title: Optional[str] = None
    domain_created_date: Optional[str] = None
    domain_age_days: Optional[int] = None
    registrar: Optional[str] = None
    detected_services: List[str] = Field(default_factory=list)
    contact_phones: List[str] = Field(default_factory=list)
    contact_emails: List[str] = Field(default_factory=list)
    scraped_addresses: List[str] = Field(default_factory=list)
    is_shelf_company_risk: bool = False
    notes: List[str] = Field(default_factory=list)


class NormalizedCompanyProfile(BaseModel):
    legal_name: Optional[str] = None
    uen: Optional[str] = None
    former_names: Optional[str] = None
    entity_type: str = EntityType.PVT_LTD.value
    incorporation_date: Optional[str] = None
    country_of_operations: Optional[str] = None
    place_of_business: Optional[str] = None
    company_status: Optional[str] = None
    bizfile_date: Optional[str] = None
    is_bizfile_fresh_12m: bool = False
    core_business_activities: Optional[str] = None
    geographic_coverage: Optional[str] = None
    customer_website: Optional[str] = None
    directors: List[DirectorItem] = Field(default_factory=list)
    ubos: List[UboItem] = Field(default_factory=list)
    authorizers: List[str] = Field(default_factory=list)
    administrators: List[str] = Field(default_factory=list)
    has_nominee_arrangement: bool = False
    has_bearer_shares: bool = False
    has_complex_structure: bool = False
    complex_structure_rationale: Optional[str] = None
    risk_rating: str = "MEDIUM"
    mas_profile: Optional[MasVerificationProfile] = None
    risk_calculator: Optional[RiskCalculatorProfile] = None
    digital_footprint: Optional[DigitalFootprintProfile] = None
    transaction_listing: Optional[TransactionListingProfile] = None


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

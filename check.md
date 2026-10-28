# Wholesale Banking Client Validation Framework: Check & Sub-Check Reference (`check.md`)

## 1. Executive Summary

This document details the complete inventory of verification checks and granular sub-checks performed by the **Wholesale Banking Client Validator** platform.

- **Total Primary Validation Checks:** `14`
- **Total Granular Sub-Checks Implemented:** `55`
- **Architecture Pattern:** Context Aggregator + Strategy Pattern (`BundleContext` aggregated across all ingested files and processed sequentially by modular validators in [`backend/validators/rules/`](file:///c:/Works/GLDB_Singapore/wholesale-banking-client-validator/backend/validators/rules)).

---

## 2. Master Check Summary Matrix

| Check ID | Check Name | Validator Class | Severity | Evaluated Documents | Sub-Check Count |
| :--- | :--- | :--- | :---: | :--- | :---: |
| **`CHK_01_BIZFILE`** | Business Profile (ACRA / Registry) Validation | `RegistryValidator` | High | ACRA / Corporate Registry Profile | **4** |
| **`CHK_02_INCORP`** | Incorporation & Legal Status Consistency | `RegistryValidator` | High | Certificate of Incorporation, ACRA Profile | **3** |
| **`CHK_03_CONST`** | Constitutional Documents Verification | `ConstitutionalValidator` | High | M&AA, ROM, Board Resolutions, ID copies | **4** |
| **`CHK_04_CORP_STRUCT`**| Corporate Structure & Directorship Completeness | `StructureValidator` | High | Register of Directors (ROD), Structure Chart, Passports/IDs | **3** |
| **`CHK_05_ID_EXPIRY`** | Director/Authorizer Identification & Document Integrity | `IdentityValidator` | High | NRIC/Passport, Proof of Address (Utility Bill) | **6** |
| **`CHK_06_UBO_COMPLEX`**| Ultimate Beneficial Ownership & Complex Structure Governance | `StructureValidator` | High | UBO Declaration, Ownership Chart, Wealth Narratives | **5** |
| **`CHK_07_SANCTIONS`** | Trade & Sanctions Risk Assessment | `QuestionnairesValidator` | High | Trade / Sanctions Questionnaire, Strategic Goods Lists | **3** |
| **`CHK_08_INSTITUTIONAL`**| Institutional / FI Questionnaire & Wolfsberg CBDDQ | `QuestionnairesValidator` | High | Institutional Questionnaire, Wolfsberg CBDDQ / FCCQ | **3** |
| **`CHK_09_CDD_EDD`** | CDD / EDD Proposal Approval & Singapore Nexus | `QuestionnairesValidator` | High | CDD/EDD Proposal Form, Approvals, Annual Turnover | **7** |
| **`CHK_10_INGESTION_QUALITY`** | Ingestion & Document Image Quality Assurance | `QualityValidator` | Medium | All Ingested Client PDFs / TIF / Scans | **3** |
| **`CHK_11_MAS_REGISTER`** | MAS Financial Institutions Directory Verification | `MasRegisterValidator` | High | Live MAS Register API / Cache, Registry Profile, ROD | **4** |
| **`CHK_12_RISK_CALCULATOR`**| Client Risk Assessment & Rating Calculator | `RiskCalculatorValidator` | High | Risk Calculator Spreadsheet, Ingested KYC Bundle | **5** |
| **`CHK_13_DIGITAL_FOOTPRINT`**| Digital Footprint & Domain Verification | `DigitalFootprintValidator` | Medium | Corporate Website, Live RDAP / DNS, ACRA Profile | **3** |
| **`CHK_14_TRANSACTION_REVIEW`**| Transaction History & Throughput Verification | `TransactionReviewValidator` | High | Bank Statements (6+ months), CDD Proposal | **5** |
| **Total** | | | | | **55** |

---

## 3. Deep-Dive Specification of Checks & Sub-Checks

```
========================================================================================
CHECK 01: CHK_01_BIZFILE — Business Profile (ACRA / Registry) Validation
Source File: backend/validators/rules/registry.py
Process Step: Entity Verification | Severity: High
========================================================================================
```
- **Primary Objective:** Validates corporate registry profiles (e.g., ACRA BizFile) for currency, legal standing, physical operating presence, and core business activity alignment.
- **Documents Evaluated:** ACRA Business Profile / Foreign Company Registry Extract.
- **Sub-Checks:**
  1. **`CHK_01.1` Profile Freshness & Issuance Recency:**
     - *Logic:* Parses the registry profile issuance date and verifies it was issued within the last **12 months** (365 days) from the validation execution date.
     - *Target Fields:* `issuance_date`, `extracted_date`.
     - *Failure Reason:* `BIZFILE_OUTDATED` (e.g., "ACRA BizFile was issued over 12 months ago").
  2. **`CHK_01.2` Live / Active Operating Status:**
     - *Logic:* Extracts company legal status and asserts it matches active standing (e.g., `Live`, `Live Company`, `Active`). Flags any entity marked `Struck Off`, `Dissolved`, `Under Liquidation`, or `Dormant`.
     - *Target Fields:* `company_status`, `status`.
     - *Failure Reason:* `ENTITY_NOT_LIVE` (e.g., "Company status is Struck Off / Inactive").
  3. **`CHK_01.3` Physical Place of Business & Registered Address Verification:**
     - *Logic:* Confirms the existence of a valid, verifiable registered office address and principal place of operations within Singapore / registered jurisdiction, barring PO boxes without physical premise correlation.
     - *Target Fields:* `registered_office_address`, `principal_place_of_business`.
     - *Failure Reason:* `INVALID_REGISTERED_ADDRESS` (e.g., "No physical registered address detected").
  4. **`CHK_01.4` Core Business Activities (SSIC Code) Specification:**
     - *Logic:* Validates that primary and secondary SSIC codes and business descriptions are populated, coherent, and not generic or prohibited industry sectors.
     - *Target Fields:* `primary_ssic_code`, `primary_activity_description`.
     - *Failure Reason:* `MISSING_CORE_ACTIVITIES` (e.g., "Primary business activity description is absent").

---

```
========================================================================================
CHECK 02: CHK_02_INCORP — Incorporation & Legal Status Consistency
Source File: backend/validators/rules/registry.py
Process Step: Entity Verification | Severity: High
========================================================================================
```
- **Primary Objective:** Cross-verifies canonical entity identifiers across the Certificate of Incorporation and ACRA profile to detect discrepancies.
- **Documents Evaluated:** Certificate of Incorporation (COI), ACRA BizFile.
- **Sub-Checks:**
  1. **`CHK_02.1` Exact Legal Entity Name Matching:**
     - *Logic:* Performs normalized string comparison between the full legal name on the Certificate of Incorporation and the ACRA BizFile profile (accounting for Pte Ltd / Private Limited variations).
     - *Target Fields:* `entity_name`, `legal_name`.
     - *Failure Reason:* `NAME_MISMATCH` (e.g., "Entity name on COI does not match ACRA BizFile").
  2. **`CHK_02.2` Unique Entity Number (UEN) Reconciliation:**
     - *Logic:* Matches the standard 9- or 10-character Singapore UEN across documents to guarantee single-entity identity.
     - *Target Fields:* `uen`, `registration_number`.
     - *Failure Reason:* `UEN_MISMATCH` (e.g., "UEN on Certificate does not match Registry record").
  3. **`CHK_02.3` Incorporation Date Parity:**
     - *Logic:* Cross-checks the exact date, month, and year of legal registration across both incorporation instruments.
     - *Target Fields:* `incorporation_date`, `registration_date`.
     - *Failure Reason:* `INCORPORATION_DATE_MISMATCH` (e.g., "Incorporation date discrepancy detected").

---

```
========================================================================================
CHECK 03: CHK_03_CONST — Constitutional Documents Verification
Source File: backend/validators/rules/constitutional.py
Process Step: Constitutional Review | Severity: High
========================================================================================
```
- **Primary Objective:** Verifies statutory constitutional governance documents, Certified True Copy (CTC) attestations, execution by corporate officers, and authorizer delegations.
- **Documents Evaluated:** Memorandum & Articles of Association (M&AA / Constitution), Register of Members (ROM), Board Resolution / Power of Attorney, Director & Authorizer Identification.
- **Sub-Checks:**
  1. **`CHK_03.1` M&AA / Constitution Execution & CTC Verification:**
     - *Logic:* Inspects the client's Memorandum & Articles of Association or Constitution for valid execution signatures and professional Certified True Copy (CTC) certification.
     - *Target Fields:* `is_ctc`, `ctc_certifier_name`, `ctc_certifier_role`, `signatures_present`.
     - *Failure Reason:* `MAA_EXECUTION_OR_CTC_MISSING` (e.g., "M&AA is uncertified or unsigned").
  2. **`CHK_03.2` Register of Members (ROM) Completeness & Attestation:**
     - *Logic:* Confirms the Register of Members reflects the current shareholding structure, matches ACRA issued share capital, and holds valid corporate secretary certification.
     - *Target Fields:* `rom_shareholders`, `rom_share_allocation`, `rom_is_certified`.
     - *Failure Reason:* `ROM_INVALID_OR_MISSING` (e.g., "Register of Members missing or uncertified").
  3. **`CHK_03.3` Board Resolution Execution & Quorum Validity:**
     - *Logic:* Verifies the Board Resolution appointing account operators/signatories is duly signed by the required quorum of authorized directors as prescribed in the Constitution.
     - *Target Fields:* `resolution_date`, `director_signatures`, `quorum_met`.
     - *Failure Reason:* `BOARD_RESOLUTION_DEFECTIVE` (e.g., "Board Resolution lacks authorized director quorum").
  4. **`CHK_03.4` Authorized Signatory / Administrator Identity & Verification (ID&V) Reconciliation:**
     - *Logic:* Cross-references every person designated as an Account Signatory, Authorizer, or System Administrator in the Board Resolution against ingested Passport/NRIC and verifies their authority.
     - *Target Fields:* `authorized_signatories`, `admin_users`, `verified_identity_ids`.
     - *Failure Reason:* `AUTHORIZER_IDV_UNRESOLVED` (e.g., "Signatory identified in resolution has no verified ID").

---

```
========================================================================================
CHECK 04: CHK_04_CORP_STRUCT — Corporate Structure & Directorship Completeness
Source File: backend/validators/rules/structure.py
Process Step: Structure Analysis | Severity: High
========================================================================================
```
- **Primary Objective:** Validates the Register of Directors, ownership structure, and reconciliation between natural persons and corporate shareholders.
- **Documents Evaluated:** Register of Directors (ROD), Structure Chart, Passports / NRICs of Directors and Shareholders.
- **Sub-Checks:**
  1. **`CHK_04.1` Register of Directors (ROD) Completeness & Residency:**
     - *Logic:* Asserts ROD presence, extracts all active directors, and ensures compliance with statutory requirements (such as at least one ordinarily resident director in Singapore for local entities).
     - *Target Fields:* `directors`, `director_names`, `residential_addresses`, `citizenships`.
     - *Failure Reason:* `ROD_DEFICIENT_OR_NO_RESIDENT_DIRECTOR` (e.g., "No ordinarily resident director found").
  2. **`CHK_04.2` Ultimate Beneficial Owner (UBO) Percentage Identification:**
     - *Logic:* Inspects the shareholding registers and group structure chart to verify all natural persons holding $\ge 25\%$ (or $\ge 10\%$ for high-risk profiles) direct/indirect ownership or voting rights are explicitly identified.
     - *Target Fields:* `ubo_list`, `ownership_percentages`, `ultimate_controlling_parties`.
     - *Failure Reason:* `UBO_THRESHOLD_UNRESOLVED` (e.g., "Beneficial owners above statutory threshold not resolved").
  3. **`CHK_04.3` Director & UBO Identity Credential Completeness:**
     - *Logic:* Verifies that for 100% of identified active directors and UBOs, valid identity documents (Passport or NRIC) have been ingested into the verification bundle.
     - *Target Fields:* `director_ids_provided`, `ubo_ids_provided`.
     - *Failure Reason:* `MISSING_DIRECTOR_OR_UBO_ID` (e.g., "Missing passport/NRIC for identified Director/UBO").

---

```
========================================================================================
CHECK 05: CHK_05_ID_EXPIRY — Director/Authorizer Identification & Document Integrity
Source File: backend/validators/rules/identity.py
Process Step: Identity Verification | Severity: High
========================================================================================
```
- **Primary Objective:** Validates individual identity documents and proof of address for synthetic tampering, template watermarks, expiration, and name/address consistency.
- **Documents Evaluated:** Passport, National ID (NRIC/FIN), Proof of Address (Utility Bill, Bank Statement).
- **Sub-Checks:**
  1. **`CHK_05.1` Identity Document Presence & Mandatory Field Population:**
     - *Logic:* Checks that all required individual identity instruments are ingested with legible full name, document number, date of birth, and nationality.
     - *Target Fields:* `id_number`, `full_name`, `dob`, `nationality`.
     - *Failure Reason:* `ID_DOCUMENT_MISSING` (e.g., "Primary ID document not supplied").
  2. **`CHK_05.2` Synthetic Sample / Template Watermark Fraud Detection (ID):**
     - *Logic:* Scans OCR text and layout metadata for synthetic placeholder markers, test watermarks, or specimen indicators (e.g., `SPECIMEN`, `SAMPLE`, `DRAFT`, `FAKE`, `TEMPLATE`, `PEXELS`, `SHUTTERSTOCK`).
     - *Target Fields:* `raw_text`, `watermark_detected`, `is_specimen`.
     - *Failure Reason:* `FRAUDULENT_OR_SAMPLE_ID` (e.g., "Specimen or synthetic watermark detected on passport").
  3. **`CHK_05.3` Identification Expiration Threshold:**
     - *Logic:* Compares document expiry date against current date. Passports or national IDs expired or expiring within 30 days of onboarding fail verification.
     - *Target Fields:* `expiry_date`, `current_date`.
     - *Failure Reason:* `ID_EXPIRED` (e.g., "Passport expired on 2024-03-15").
  4. **`CHK_05.4` Synthetic Sample / Template Watermark Fraud Detection (Proof of Address):**
     - *Logic:* Scans proof of address (utility bill / bank statement) for template indicators, mock utilities, or placeholder design tokens.
     - *Target Fields:* `utility_bill_text`, `template_signatures`.
     - *Failure Reason:* `FRAUDULENT_POA_TEMPLATE` (e.g., "Utility bill identified as editable mock template").
  5. **`CHK_05.5` Proof of Address 90-Day Freshness Recency:**
     - *Logic:* Verifies utility bill / statement statement date is within **90 days** of onboarding submission date.
     - *Target Fields:* `statement_date`, `issuance_date`.
     - *Failure Reason:* `POA_STALE_OVER_90_DAYS` (e.g., "Utility bill older than 90 days").
  6. **`CHK_05.6` Cross-Document Name & Residential Address Reconciliation:**
     - *Logic:* Matches individual full name and residential address between the passport/NRIC, utility bill, and the CDD proposal. Flags address mismatches or phonetic discrepancies.
     - *Target Fields:* `id_name`, `id_address`, `poa_name`, `poa_address`.
     - *Failure Reason:* `NAME_ADDRESS_DISCREPANCY` (e.g., "Utility bill address does not match residential address").

---

```
========================================================================================
CHECK 06: CHK_06_UBO_COMPLEX — Ultimate Beneficial Ownership & Complex Structure Governance
Source File: backend/validators/rules/structure.py
Process Step: Ownership Governance | Severity: High
========================================================================================
```
- **Primary Objective:** Evaluates the formal UBO Declaration, bearer share prohibitions, nominee shareholder arrangements, layered ownership rationale, and wealth origin corroboration.
- **Documents Evaluated:** Signed UBO Declaration Form, Multi-Tier Ownership Diagram, Source of Wealth Corroboration.
- **Sub-Checks:**
  1. **`CHK_06.1` UBO Declaration Execution & Completeness:**
     - *Logic:* Confirms the formal UBO Declaration form is signed by an authorized director/executive officer and all intermediate ownership layers are enumerated down to natural individuals.
     - *Target Fields:* `ubo_declaration_signed`, `signatory_title`, `declaration_date`.
     - *Failure Reason:* `UBO_DECLARATION_INCOMPLETE` (e.g., "UBO Declaration form unexecuted").
  2. **`CHK_06.2` Bearer Share Prohibition Enforcement:**
     - *Logic:* Inspects constitutional and declaration clauses to verify that no entity in the intermediate chain has issued or possesses the capacity to issue bearer shares or bearer share warrants.
     - *Target Fields:* `has_bearer_shares`, `bearer_shares_prohibited`.
     - *Failure Reason:* `BEARER_SHARES_PERMITTED` (e.g., "Bearer shares not explicitly prohibited in corporate hierarchy").
  3. **`CHK_06.3` Nominee Director & Shareholder Arrangement Disclosure:**
     - *Logic:* Tests for nominee director, nominee shareholder, or blind trust structures; if present, validates that formal Nominee Agreements and the identity of Ultimate Nominators are fully disclosed.
     - *Target Fields:* `nominee_arrangement_present`, `nominator_identified`, `nominee_agreement_attached`.
     - *Failure Reason:* `UNDISCLOSED_NOMINEE_ARRANGEMENT` (e.g., "Nominee structure detected without nominator ID&V").
  4. **`CHK_06.4` Complex / Multi-Jurisdictional Structure Commercial Rationale:**
     - *Logic:* If $>2$ layers of holding companies or offshore secrecy jurisdictions (BVI, Cayman, Seychelles, Marshall Islands) exist, enforces presence of a detailed written commercial rationale signed by Relationship Manager.
     - *Target Fields:* `layer_count`, `offshore_jurisdictions`, `commercial_rationale_text`.
     - *Failure Reason:* `UNJUSTIFIED_COMPLEX_STRUCTURE` (e.g., "No commercial rationale documented for 3-tier offshore structure").
  5. **`CHK_06.5` Source of Wealth Narrative & Corroborating Evidence:**
     - *Logic:* Evaluates the substantive narrative documenting how the UBO generated aggregate personal net worth (e.g., business divestment, retained earnings, inheritance) along with corroborating external evidence (audited financials, dividend vouchers, tax returns).
     - *Target Fields:* `sow_narrative_words`, `sow_evidence_documents`.
     - *Failure Reason:* `INSUFFICIENT_SOW_CORROBORATION` (e.g., "Source of wealth narrative is under statutory depth or uncorroborated").

---

```
========================================================================================
CHECK 07: CHK_07_SANCTIONS — Trade & Sanctions Risk Assessment
Source File: backend/validators/rules/questionnaires.py
Process Step: Risk Questionnaire | Severity: High
========================================================================================
```
- **Primary Objective:** Evaluates client exposure to comprehensive/targeted sanctions regimes, Supply Chain Finance (SCF) risk triggers, and strategic dual-use goods.
- **Documents Evaluated:** Trade & Sanctions Risk Questionnaire, Ingested Customer Profile, Trade Compliance Escalation Memo.
- **Sub-Checks:**
  1. **`CHK_07.1` Sanctions Questionnaire Trigger Routing (High-Risk Sectors / SCF):**
     - *Logic:* Determines whether client operations touch high-risk sectors (Maritime, Defense, Energy, Precious Metals) or Supply Chain Finance requiring mandatory questionnaire execution.
     - *Target Fields:* `industry_sector`, `requires_trade_questionnaire`, `questionnaire_present`.
     - *Failure Reason:* `MISSING_SANCTIONS_QUESTIONNAIRE` (e.g., "High-risk trading entity missing mandatory trade questionnaire").
  2. **`CHK_07.2` Relationship Manager Department & SCF Master Code Alignment:**
     - *Logic:* Validates the RM booking center code against the bank's master division codes (e.g., verifying SCF/GTS trade accounts are handled by approved trade desks).
     - *Target Fields:* `rm_department_code`, `approved_trade_desks`.
     - *Failure Reason:* `UNAUTHORIZED_RM_DESK` (e.g., "RM department code not authorized for Supply Chain Finance").
  3. **`CHK_07.3` Strategic Dual-Use Goods & Trade Compliance Escalation:**
     - *Logic:* Scans goods descriptions and HS codes against international strategic dual-use control lists (Wassenaar, EU/MAS Dual-Use). If dual-use keywords appear, verifies an approval memo from Global Trade Compliance.
     - *Target Fields:* `goods_handled`, `strategic_goods_flag`, `trade_compliance_memo_approved`.
     - *Failure Reason:* `DUAL_USE_ESCALATION_MISSING` (e.g., "Dual-use technology detected without Trade Compliance sign-off").

---

```
========================================================================================
CHECK 08: CHK_08_INSTITUTIONAL — Institutional / FI Questionnaire & Wolfsberg CBDDQ
Source File: backend/validators/rules/questionnaires.py
Process Step: Institutional Review | Severity: High
========================================================================================
```
- **Primary Objective:** Validates specialized due diligence questionnaires for Financial Institutions, Fintechs, Payment Service Providers, and Correspondent Banking accounts.
- **Documents Evaluated:** Institutional Due Diligence Questionnaire, Wolfsberg CBDDQ (Correspondent Banking Due Diligence) or FCCQ.
- **Sub-Checks:**
  1. **`CHK_08.1` Dynamic Entity Classification & Questionnaire Applicability:**
     - *Logic:* Identifies if the entity is a Bank, Non-Bank FI, Asset Manager, or Payment Service Provider (under MAS PSA / FATF rules) triggering the Wolfsberg CBDDQ.
     - *Target Fields:* `entity_type`, `is_financial_institution`, `questionnaire_type`.
     - *Failure Reason:* `INSTITUTIONAL_QUESTIONNAIRE_MISSING` (e.g., "Licensed Payment Institution missing Wolfsberg CBDDQ").
  2. **`CHK_08.2` Wolfsberg CBDDQ Signature Recency ($\le 12$ Months):**
     - *Logic:* Verifies the Chief AML/Compliance Officer of the respondent institution signed and attested the questionnaire within the preceding **12 months**.
     - *Target Fields:* `cbddq_sign_off_date`, `cbddq_signatory_title`.
     - *Failure Reason:* `WOLFSBERG_QUESTIONNAIRE_EXPIRED` (e.g., "Wolfsberg CBDDQ signed $>12$ months ago").
  3. **`CHK_08.3` Critical Negative Answer Inspection (Correspondent / Nested Accounts):**
     - *Logic:* Scans responses to key questions (e.g., provision of shell bank services, nested correspondent relationships, PEP monitoring programs, anonymous account prohibition). Asserts no critical negative answers without compensating controls.
     - *Target Fields:* `shell_bank_services`, `nested_accounts`, `pep_screening_controls`.
     - *Failure Reason:* `PROHIBITED_INSTITUTIONAL_EXPOSURE` (e.g., "Respondent bank provides services to shell banks").

---

```
========================================================================================
CHECK 09: CHK_09_CDD_EDD — CDD / EDD Proposal Approval & Singapore Nexus
Source File: backend/validators/rules/questionnaires.py
Process Step: CDD / EDD Verification | Severity: High
========================================================================================
```
- **Primary Objective:** Validates the primary Client Due Diligence proposal form, establishing bona fide Singapore commercial nexus, throughput vs turnover realism, tax haven controls, and 3-tier governance sign-offs.
- **Documents Evaluated:** CDD/EDD Proposal Form, RM Submission Deck, Committee Approval Sheets.
- **Sub-Checks:**
  1. **`CHK_09.1` CDD / EDD Proposal Form Ingestion & Form Completion:**
     - *Logic:* Verifies the formal CDD / EDD proposal document is present and fully populated without blank mandatory sections.
     - *Target Fields:* `cdd_form_present`, `sections_completed`.
     - *Failure Reason:* `CDD_FORM_MISSING` (e.g., "CDD proposal form not ingested").
  2. **`CHK_09.2` Singapore Commercial Nexus Substantiation:**
     - *Logic:* Enforces substantive documentation of genuine commercial nexus to Singapore (e.g., local staff headcount, local operational office, Singapore vendor/customer contracts, local treasury hub operations) rather than purely pass-through booking.
     - *Target Fields:* `singapore_nexus_rationale`, `local_employees_count`, `local_contracts`.
     - *Failure Reason:* `INSUFFICIENT_SINGAPORE_NEXUS` (e.g., "No substantive Singapore business nexus articulated").
  3. **`CHK_09.3` Account Purpose & Wholesale Banking Product Alignment:**
     - *Logic:* Cross-checks declared account purpose (e.g., Trade Finance, FX Hedging, Cash Management) against the client's corporate profile, business model, and anticipated transaction types.
     - *Target Fields:* `account_purpose`, `requested_banking_products`, `business_activities`.
     - *Failure Reason:* `PRODUCT_PURPOSE_MISALIGNMENT` (e.g., "Treasury FX products requested for retail distribution business").
  4. **`CHK_09.4` Monthly Account Throughput vs Annual Turnover Pass-Through Risk:**
     - *Logic:* Calculates the annualized expected transaction volume ($12 \times \text{Expected Monthly Throughput}$). If annualized volume exceeds **$150\%$ of Annual Top-Line Turnover**, flags the account for high-risk pass-through / money laundering laundering risk.
     - *Target Fields:* `expected_monthly_volume`, `annual_turnover`.
     - *Failure Reason:* `PASS_THROUGH_VOLUME_EXCESS` (e.g., "Annualized throughput exceeds declared turnover by 240%").
  5. **`CHK_09.5` Tax Risk Completeness & 'N/A' Anti-Avoidance:**
     - *Logic:* Inspects the mandatory Tax Risk and FATCA/CRS section. Flags as invalid any submissions where tax residency answers or tax risk assessments are filled with `N/A`, `Not Applicable`, or blank.
     - *Target Fields:* `tax_residency_jurisdictions`, `tin_numbers`, `tax_risk_evaluation`.
     - *Failure Reason:* `TAX_RISK_INCOMPLETE_OR_NA` (e.g., "Tax risk section answered with N/A").
  6. **`CHK_09.6` EU / FATF Tax Haven & High-Risk Jurisdiction Mitigating Controls:**
     - *Logic:* Checks whether the entity, subsidiaries, or immediate parents are incorporated in EU non-cooperative tax jurisdictions or FATF grey/black-list countries. If present, verifies specialized enhanced tax mitigating controls.
     - *Target Fields:* `jurisdictions_of_operation`, `eu_blacklist_exposure`, `mitigating_controls`.
     - *Failure Reason:* `TAX_HAVEN_MITIGATION_ABSENT` (e.g., "Entity operates in EU Annex I jurisdiction without tax clearance memo").
  7. **`CHK_09.7` Continuation Narrative Depth ($\ge 30$ words) & 3-Tier Governance Sign-Off:**
     - *Logic:* Verifies the Relationship Manager wrote a substantive business continuation narrative (minimum 30 words) and that all required 3 tiers of sign-off are completed: **Maker (RM)**, **Checker (1LOD Team Lead)**, and **Approver (2LOD Compliance / Approving Authority)**.
     - *Target Fields:* `continuation_narrative_words`, `maker_signed`, `checker_signed`, `approver_signed`.
     - *Failure Reason:* `GOVERNANCE_SIGNOFF_INCOMPLETE` (e.g., "Approver sign-off missing or narrative under 30 words").

---

```
========================================================================================
CHECK 10: CHK_10_INGESTION_QUALITY — Ingestion & Document Image Quality Assurance
Source File: backend/validators/rules/quality.py
Process Step: Ingestion Quality | Severity: Medium
========================================================================================
```
- **Primary Objective:** Enforces forensic image and OCR quality standards, Certified True Copy (CTC) seal completeness, and certified translation requirements.
- **Documents Evaluated:** All Ingested Client PDF & Graphic Files.
- **Sub-Checks:**
  1. **`CHK_10.1` Document OCR Confidence, Resolution & Visual Integrity:**
     - *Logic:* Measures average optical character recognition confidence (minimum threshold $\ge 85\%$), scan resolution ($\ge 200\text{ DPI}$), and detects visual defects such as severe skewing, blurring, or clipped borders.
     - *Target Fields:* `ocr_confidence`, `dpi`, `is_blurred`, `is_skewed`, `is_truncated`.
     - *Failure Reason:* `POOR_OCR_OR_IMAGE_RESOLUTION` (e.g., "Scan resolution 120 DPI below 200 DPI requirement").
  2. **`CHK_10.2` Non-Registry Copy Certified True Copy (CTC) Execution:**
     - *Logic:* For any non-electronic registry document (e.g., foreign passports, physical resolutions), validates the presence of a complete CTC stamp containing: certifier signature, full printed name, professional capacity (Lawyer, Notary, CPA), date, and formal certifying statement.
     - *Target Fields:* `has_ctc_stamp`, `certifier_name`, `certifier_capacity`, `ctc_date`.
     - *Failure Reason:* `INCOMPLETE_CTC_ATTESTATION` (e.g., "CTC stamp lacks professional capacity and signature").
  3. **`CHK_10.3` Certified Sworn Translation for Foreign Language Instruments:**
     - *Logic:* Detects documents whose primary language is not English. Verifies the inclusion of a certified sworn translation executed by a court-registered or certified professional translator.
     - *Target Fields:* `detected_language`, `has_english_translation`, `translation_certified`.
     - *Failure Reason:* `NON_ENGLISH_DOCUMENT_UNTRANSLATED` (e.g., "Bahasa Indonesia deed lacks certified English translation").

---

```
========================================================================================
CHECK 11: CHK_11_MAS_REGISTER — MAS Financial Institutions Directory Verification
Source File: backend/validators/rules/mas_register.py
Process Step: Regulatory Register | Severity: High
========================================================================================
```
- **Primary Objective:** Cross-verifies financial entities against the Monetary Authority of Singapore (MAS) Financial Institutions Directory in real time.
- **Documents Evaluated:** Live MAS Register API / Local Cache, ACRA Profile, Register of Directors.
- **Sub-Checks:**
  1. **`CHK_11.1` Regulated Financial Entity Scope & Live MAS Search:**
     - *Logic:* Evaluates whether the onboarding entity performs regulated activities under the Securities and Futures Act (SFA), Payment Services Act (PSA), or Banking Act. Executes lookup against MAS directory.
     - *Target Fields:* `regulated_activity_flag`, `mas_institution_found`, `mas_institution_name`.
     - *Failure Reason:* `UNLICENSED_FINANCIAL_ACTIVITY` (e.g., "Entity conducts regulated activity but not found on MAS Register").
  2. **`CHK_11.2` Licence Standing (Active / Current vs Suspended / Revoked):**
     - *Logic:* Asserts the MAS regulatory licence status is `Active` or `Current`. Flags entities with `Suspended`, `Revoked`, or `Ceased` regulatory permissions.
     - *Target Fields:* `mas_licence_status`, `effective_licence_date`.
     - *Failure Reason:* `MAS_LICENCE_NOT_ACTIVE` (e.g., "MAS Capital Markets Services licence is Ceased").
  3. **`CHK_11.3` Country of Incorporation & UEN Concordance:**
     - *Logic:* Compares the registered jurisdiction and UEN recorded on the MAS directory against the client's ACRA Business Profile.
     - *Target Fields:* `mas_uen`, `bizfile_uen`, `mas_country`, `bizfile_country`.
     - *Failure Reason:* `MAS_REGISTRY_DISCREPANCY` (e.g., "UEN on MAS Register does not match ACRA BizFile").
  4. **`CHK_11.4` Key Management Personnel (CEO & Representative) Reconciliation:**
     - *Logic:* Cross-checks registered MAS Chief Executive Officers and appointed representatives against the company's Register of Directors.
     - *Target Fields:* `mas_key_executives`, `rod_directors`.
     - *Failure Reason:* `MAS_KEY_PERSONNEL_MISMATCH` (e.g., "CEO listed in MAS Register not reflected in Register of Directors").

---

```
========================================================================================
CHECK 12: CHK_12_RISK_CALCULATOR — Client Risk Assessment & Rating Calculator
Source File: backend/validators/rules/risk_calculator.py
Process Step: Risk Assessment | Severity: High
========================================================================================
```
- **Primary Objective:** Executes multi-feature risk scoring, individual interested party ratings, ceiling override enforcement, and audits uploaded risk calculator spreadsheets.
- **Documents Evaluated:** Client Risk Assessment Spreadsheet (.xlsx / .csv), Ingested Client KYC Master File.
- **Sub-Checks:**
  1. **`CHK_12.1` 10-Feature Entity Risk Scoring Execution:**
     - *Logic:* Computes deterministic risk scores across 10 defined risk dimensions: Country of Incorp, Industry/Sector, Delivery Channel, Product Risk, Sanctions Exposure, Legal Form, PEP Exposure, Adverse Media, Transaction Velocity, Cross-Border Flow.
     - *Target Fields:* `feature_scores_breakdown`, `weighted_composite_score`.
     - *Failure Reason:* `RISK_FEATURE_CALCULATION_ERROR` (e.g., "Missing feature score in entity model").
  2. **`CHK_12.2` Interested Party Identification & Individual Risk Scoring:**
     - *Logic:* Identifies all connected natural parties (Directors, Signatories, UBOs), calculates individual risk scores based on nationality, residency, PEP status, and sanctions hits.
     - *Target Fields:* `connected_parties_scores`, `pep_flags`, `high_risk_citizenships`.
     - *Failure Reason:* `PARTY_RISK_UNRESOLVED` (e.g., "Individual risk score failed for UBO").
  3. **`CHK_12.3` Mandatory Rule-Based Risk Ceiling Override Enforcement:**
     - *Logic:* Applies non-negotiable policy overrides: if any UBO is a PEP, or client operates in high-risk defense/cryptocurrency, or country of origin is FATF black-listed, the composite rating must automatically default to **High Risk**, overriding low weighted averages.
     - *Target Fields:* `override_triggers_hit`, `final_risk_band`.
     - *Failure Reason:* `OVERRIDE_CEILING_NOT_APPLIED` (e.g., "PEP connected party present but risk score remained Medium").
  4. **`CHK_12.4` Automated Composite Risk Band Determination:**
     - *Logic:* Assigns final formal rating: `Low` ($< 2.0$), `Medium` ($2.0 - 3.5$), `High` ($> 3.5$) based on mathematically validated models.
     - *Target Fields:* `composite_score`, `assigned_risk_tier`.
     - *Failure Reason:* `INVALID_RISK_BAND_ASSIGNMENT` (e.g., "Score 3.8 assigned Medium Risk").
  5. **`CHK_12.5` Uploaded Spreadsheet Audit (Omitted Parties & Score Understatements):**
     - *Logic:* Cross-checks RM-uploaded risk spreadsheet against ground-truth document facts. Flags any omitted connected parties or artificially downgraded individual risk scores.
     - *Target Fields:* `spreadsheet_parties`, `ground_truth_parties`, `understatement_detected`.
     - *Failure Reason:* `RISK_SPREADSHEET_DISCREPANCY` (e.g., "Uploaded risk calculator omitted 2 directors found on ROD").

---

```
========================================================================================
CHECK 13: CHK_13_DIGITAL_FOOTPRINT — Digital Footprint & Domain Verification
Source File: backend/validators/rules/digital_footprint.py
Process Step: Digital Footprint | Severity: Medium
========================================================================================
```
- **Primary Objective:** Validates corporate domain registration, web server availability, domain age shelf-life risks, and corporate commercial activity consistency.
- **Documents Evaluated:** Corporate Web Address, Live RDAP / WHOIS Records, ACRA Profile.
- **Sub-Checks:**
  1. **`CHK_13.1` Official Corporate Portal Online / HTTP Reachability:**
     - *Logic:* Performs asynchronous HTTP GET / HEAD requests to the declared corporate URL. Asserts response status code `200 OK` (or valid 3xx redirect) within standard timeouts.
     - *Target Fields:* `website_url`, `http_status_code`, `response_latency_ms`.
     - *Failure Reason:* `CORPORATE_WEBSITE_UNREACHABLE` (e.g., "Client website returned HTTP 404 / connection timeout").
  2. **`CHK_13.2` Domain Registration Age Shelf-Company Risk Threshold ($< 30$ Days):**
     - *Logic:* Queries RDAP / WHOIS protocols to retrieve domain creation date. Flags domains registered **$< 30$ days** prior to onboarding as high-risk disposable or newly created shelf-company indicators.
     - *Target Fields:* `domain_created_date`, `domain_age_days`.
     - *Failure Reason:* `DOMAIN_NEWLY_REGISTERED` (e.g., "Corporate domain registered only 14 days ago").
  3. **`CHK_13.3` Advertised Website Services vs ACRA Business Activity Reconciliation:**
     - *Logic:* Extracts meta descriptions, homepage H1/H2 tags, and service summaries; compares semantic content against ACRA SSIC activities to detect misleading or disguised operations.
     - *Target Fields:* `website_services_summary`, `acra_primary_activity`.
     - *Failure Reason:* `COMMERCIAL_ACTIVITY_INCONSISTENCY` (e.g., "Website advertises crypto broker services while registered as IT consulting").

---

```
========================================================================================
CHECK 14: CHK_14_TRANSACTION_REVIEW — Transaction History & Throughput Verification
Source File: backend/validators/rules/transaction_review.py
Process Step: Financial Review | Severity: High
========================================================================================
```
- **Primary Objective:** Evaluates historical bank statements, continuous lookback duration, multi-currency aggregation, dormancy, volume spikes, and variance against CDD declarations.
- **Documents Evaluated:** Bank Account Statements ($\ge 6$ months), CDD Proposal Form, Relationship Manager Review Summary.
- **Sub-Checks:**
  1. **`CHK_14.1` Continuous Lookback Window Verification ($\ge 170$ Days):**
     - *Logic:* Parses statement start and end transaction dates across all submitted pages. Asserts continuous statement coverage spanning at least **170 days** ($\approx 6$ full calendar months) without missing monthly intervals.
     - *Target Fields:* `statement_start_date`, `statement_end_date`, `coverage_days`.
     - *Failure Reason:* `INSUFFICIENT_STATEMENT_LOOKBACK` (e.g., "Bank statements span 82 days, failing 170-day requirement").
  2. **`CHK_14.2` Monthly Inflow/Outflow Aggregation & Multi-Currency Segregation:**
     - *Logic:* Groups every transaction line by calendar month and currency code (SGD, USD, EUR, etc.), calculating distinct monthly total debits, monthly total credits, and net cashflow.
     - *Target Fields:* `monthly_totals_by_currency`, `credit_volume`, `debit_volume`.
     - *Failure Reason:* `TRANSACTION_AGGREGATION_FAILURE` (e.g., "Failed to resolve currency groupings").
  3. **`CHK_14.3` Account Dormancy & Inactivity Detection ($\ge 2$ Consecutive Months):**
     - *Logic:* Identifies if the account had zero commercial operational transactions across $\ge 2$ consecutive calendar months (dormant entity activation risk).
     - *Target Fields:* `monthly_transaction_counts`, `consecutive_dormant_months`.
     - *Failure Reason:* `PROTRACTED_ACCOUNT_DORMANCY` (e.g., "Zero transactions recorded across 3 consecutive months").
  4. **`CHK_14.4` Sudden Transaction Volume / Velocity Spike Detection ($> 50\%$ Surge):**
     - *Logic:* Computes month-over-month percentage variances in aggregate turnover. Flags anomalous surges where monthly volume spikes by $>50\%$ above historical baseline average without documented justification.
     - *Target Fields:* `mom_variance_percentage`, `peak_monthly_volume`, `average_monthly_volume`.
     - *Failure Reason:* `ANOMALOUS_TRANSACTION_SPIKE` (e.g., "Inflows spiked by 180% month-over-month in month 5").
  5. **`CHK_14.5` CDD Declared Volume Cross-Reconciliation ($\le 50\%$ Variance):**
     - *Logic:* Compares actual observed average monthly inflow against the declared expected throughput in the CDD Proposal Form. Asserts absolute variance is $\le 50\%$. Also audits RM summary table for mathematical calculation errors.
     - *Target Fields:* `actual_monthly_inflow`, `declared_monthly_throughput`, `variance_percentage`, `rm_table_sums`.
     - *Failure Reason:* `DECLARED_ACTUAL_THROUGHPUT_DIVERGENCE` (e.g., "Actual monthly flow of $1.8M diverges by 80% from declared $1.0M").

---

## 4. Sub-Check Distribution Summary

```
CHK_01_BIZFILE:               [4 sub-checks]
CHK_02_INCORP:                [3 sub-checks]
CHK_03_CONST:                 [4 sub-checks]
CHK_04_CORP_STRUCT:           [3 sub-checks]
CHK_05_ID_EXPIRY:             [6 sub-checks]
CHK_06_UBO_COMPLEX:           [5 sub-checks]
CHK_07_SANCTIONS:             [3 sub-checks]
CHK_08_INSTITUTIONAL:         [3 sub-checks]
CHK_09_CDD_EDD:               [7 sub-checks]
CHK_10_INGESTION_QUALITY:     [3 sub-checks]
CHK_11_MAS_REGISTER:          [4 sub-checks]
CHK_12_RISK_CALCULATOR:       [5 sub-checks]
CHK_13_DIGITAL_FOOTPRINT:     [3 sub-checks]
CHK_14_TRANSACTION_REVIEW:    [5 sub-checks]
=============================================
TOTAL GRANULAR SUB-CHECKS:    55 sub-checks
```

## 5. Execution Architecture Reference

All checks are executed through the core orchestrator located at [`backend/validators/dispatcher.py`](file:///c:/Works/GLDB_Singapore/wholesale-banking-client-validator/backend/validators/dispatcher.py) via the `dispatch_wholesale_validation()` method. Each validator implements deterministic, audited logic ensuring compliance with Monetary Authority of Singapore (MAS) Notices 626 & 626A, FATF Recommendations, and internal wholesale banking risk appetite limits.

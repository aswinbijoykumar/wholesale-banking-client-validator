"""SQLite persistence layer for Wholesale Banking Client Validation Engine.

Provides the 12 wholesale banking tables:
- customer_bundles
- documents
- document_extractions
- company_profiles
- ubos
- directors
- validation_runs
- validation_results
- validation_findings
- document_requirements
- priority_rules
- audit_logs
"""
import sqlite3
import uuid
from datetime import datetime, timezone

from .config import settings


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
-- 1. Customer Bundles (Entities / Wholesale Client Files)
CREATE TABLE IF NOT EXISTS customer_bundles (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    uen           TEXT,
    entity_type   TEXT NOT NULL DEFAULT 'Private Limited Company',
    status        TEXT NOT NULL DEFAULT 'PENDING',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 2. Documents (Uploaded files per client bundle)
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    bundle_id     TEXT NOT NULL REFERENCES customer_bundles(id) ON DELETE CASCADE,
    doc_type      TEXT NOT NULL DEFAULT 'unclassified',  -- bizfile, cert_incorporation, maa, rom, board_resolution, other
    original_name TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    page_count    INTEGER NOT NULL DEFAULT 1,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    is_ctc        INTEGER DEFAULT 0, -- 1 if Certified True Copy verified
    uploaded_at   TEXT NOT NULL
);

-- 3. Document Extractions (Raw text, OCR, Vision interpretations)
CREATE TABLE IF NOT EXISTS document_extractions (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ocr_engine    TEXT, -- 'pymupdf', 'tesseract', 'gpt-4o'
    raw_text      TEXT,
    extracted_json TEXT, -- JSON structured fields
    extracted_at  TEXT NOT NULL
);

-- 4. Company Profiles (Normalized from extractions)
CREATE TABLE IF NOT EXISTS company_profiles (
    id                    TEXT PRIMARY KEY,
    bundle_id             TEXT NOT NULL UNIQUE REFERENCES customer_bundles(id) ON DELETE CASCADE,
    legal_name            TEXT,
    uen                   TEXT,
    former_names          TEXT,
    entity_type           TEXT,
    incorporation_date    TEXT,
    country_of_operations TEXT,
    company_status        TEXT, -- 'Active', 'Struck Off', 'Dormant', 'Ceased'
    bizfile_date          TEXT,
    is_bizfile_fresh_12m  INTEGER DEFAULT 0,
    updated_at            TEXT NOT NULL
);

-- 5. Directors
CREATE TABLE IF NOT EXISTS directors (
    id                TEXT PRIMARY KEY,
    bundle_id         TEXT NOT NULL REFERENCES customer_bundles(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    id_number         TEXT,
    nationality       TEXT,
    appointment_date  TEXT,
    status            TEXT DEFAULT 'CURRENT'
);

-- 6. UBOs / Shareholders
CREATE TABLE IF NOT EXISTS ubos (
    id                    TEXT PRIMARY KEY,
    bundle_id             TEXT NOT NULL REFERENCES customer_bundles(id) ON DELETE CASCADE,
    name                  TEXT NOT NULL,
    id_number             TEXT,
    ownership_percentage  REAL DEFAULT 0.0,
    share_count           INTEGER,
    is_controller         INTEGER DEFAULT 0
);

-- 7. Validation Runs (State machine runs per bundle)
CREATE TABLE IF NOT EXISTS validation_runs (
    id              TEXT PRIMARY KEY,
    bundle_id       TEXT NOT NULL REFERENCES customer_bundles(id) ON DELETE CASCADE,
    state           TEXT NOT NULL DEFAULT 'UPLOADED', -- UPLOADED, CLASSIFYING, EXTRACTING, OCR_PROCESSING, VISION_PROCESSING, NORMALIZING, VALIDATING, COMPLETED, FAILED
    overall_verdict TEXT, -- 'PASS', 'FAIL'
    summary         TEXT,
    error           TEXT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT
);

-- 8. Validation Results (Check-level verdicts: Desc 1 to 6)
CREATE TABLE IF NOT EXISTS validation_results (
    id                   TEXT PRIMARY KEY,
    run_id               TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    check_id             TEXT NOT NULL,
    rule_name            TEXT NOT NULL,
    verdict              TEXT NOT NULL, -- 'PASS', 'FAIL', 'NOT_APPLICABLE'
    reason_code          TEXT,          -- 'EXPIRED', 'MISSING_BIZFILE', 'CROSS_DOCUMENT_MISMATCH', etc.
    priority             TEXT NOT NULL, -- 'HIGH', 'MEDIUM', 'LOW'
    evidence             TEXT,
    evaluated_files_json TEXT,          -- JSON serialized itemized file results
    created_at           TEXT NOT NULL
);

-- 9. Validation Findings (Granular Explainable AI findings)
CREATE TABLE IF NOT EXISTS validation_findings (
    id                TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    check_id          TEXT NOT NULL,
    finding_type      TEXT NOT NULL,
    severity          TEXT NOT NULL, -- 'HIGH', 'MEDIUM', 'LOW'
    missing_document  TEXT,
    reason            TEXT NOT NULL,
    target_field      TEXT,
    details           TEXT,
    created_at        TEXT NOT NULL
);

-- 10. Document Requirements
CREATE TABLE IF NOT EXISTS document_requirements (
    id                TEXT PRIMARY KEY,
    entity_type       TEXT NOT NULL,
    doc_type          TEXT NOT NULL,
    is_mandatory      INTEGER NOT NULL DEFAULT 1,
    requires_ctc      INTEGER NOT NULL DEFAULT 0,
    validity_months   INTEGER
);

-- 11. Priority Rules
CREATE TABLE IF NOT EXISTS priority_rules (
    id            TEXT PRIMARY KEY,
    reason_code   TEXT NOT NULL UNIQUE,
    priority      TEXT NOT NULL, -- 'HIGH', 'MEDIUM', 'LOW'
    default_fail  INTEGER NOT NULL DEFAULT 1,
    description   TEXT
);

-- 12. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id            TEXT PRIMARY KEY,
    bundle_id     TEXT REFERENCES customer_bundles(id) ON DELETE SET NULL,
    run_id        TEXT REFERENCES validation_runs(id) ON DELETE SET NULL,
    action        TEXT NOT NULL,
    actor         TEXT NOT NULL DEFAULT 'system',
    details       TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_bundle ON documents(bundle_id);
CREATE INDEX IF NOT EXISTS idx_runs_bundle ON validation_runs(bundle_id);
CREATE INDEX IF NOT EXISTS idx_results_run ON validation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_run ON validation_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_directors_bundle ON directors(bundle_id);
CREATE INDEX IF NOT EXISTS idx_ubos_bundle ON ubos(bundle_id);
"""

SEED_DEFAULTS = """
-- Seed default document requirements
INSERT OR IGNORE INTO document_requirements (id, entity_type, doc_type, is_mandatory, requires_ctc, validity_months) VALUES
('req_pvt_bizfile', 'Private Limited Company', 'bizfile', 1, 0, 12),
('req_pvt_incorp',  'Private Limited Company', 'cert_incorporation', 1, 0, NULL),
('req_pvt_maa',     'Private Limited Company', 'maa', 1, 1, NULL),
('req_pvt_rom',     'Private Limited Company', 'rom', 1, 1, NULL),
('req_pvt_board',   'Private Limited Company', 'board_resolution', 0, 1, NULL);

-- Seed default priority rules
INSERT OR IGNORE INTO priority_rules (id, reason_code, priority, default_fail, description) VALUES
('pr_1',  'EXPIRED',                   'HIGH',   1, 'Registry extract/BizFile older than 12 months'),
('pr_2',  'MISSING_BIZFILE',           'HIGH',   1, 'ACRA Bizfile/Company Search missing'),
('pr_3',  'INACTIVE_COMPANY',          'HIGH',   1, 'Company status is not Active/Live'),
('pr_4',  'MISSING_INCORPORATION_DOC', 'HIGH',   1, 'Certificate of Incorporation missing'),
('pr_5',  'MISSING_UEN',               'HIGH',   1, 'Business registration number (UEN) missing'),
('pr_6',  'MISSING_INCORP_DATE',       'HIGH',   1, 'Incorporation date missing'),
('pr_7',  'MISSING_MAA',               'HIGH',   1, 'Memorandum & Articles of Association missing'),
('pr_8',  'MISSING_ROM',               'HIGH',   1, 'Register of Members missing'),
('pr_9',  'NON_CERTIFIED_DOCUMENT',    'MEDIUM', 1, 'Constitutional document not certified true copy (CTC)'),
('pr_10', 'CROSS_DOCUMENT_MISMATCH',   'HIGH',   1, 'Entity details mismatch across provided documents');
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.executescript(SEED_DEFAULTS)
        # Auto-migrate evaluated_files_json if older SQLite table exists
        try:
            conn.execute("ALTER TABLE validation_results ADD COLUMN evaluated_files_json TEXT")
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def log_audit(action: str, bundle_id: str | None = None, run_id: str | None = None, actor: str = "system", details: str = "") -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO audit_logs (id, bundle_id, run_id, action, actor, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id(), bundle_id, run_id, action, actor, details, now_iso())
        )
        conn.commit()
    finally:
        conn.close()

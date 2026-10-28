"""Wholesale Banking KYC & Policy Validation Engine — FastAPI backend.

Serves the wholesale client dashboard and REST API for customer bundles,
document extractions, validation state machine execution, and audit report generation.
"""
import json
import re
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import List, Optional

import pymupdf
from fastapi import (FastAPI, File, Form, HTTPException, Request, Response,
                     UploadFile)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .config import BASE_DIR, check_required, settings
from .db import get_conn, init_db, new_id, now_iso, log_audit
from .seed import seed_if_empty
from .rules import RULES
from .verifier import run_wholesale_verification
from .reports import render_wholesale_pdf
from .models import Verdict, Priority, ItemizedDocStatus, ValidationFinding
from .validators.subcheck_matrix import build_subchecks_for_result, build_executive_summary


ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".xlsx", ".xls"}
DOC_TYPES = {
    "bizfile",
    "cert_incorporation",
    "maa",
    "rom",
    "rod",
    "board_resolution",
    "ubo_declaration",
    "id_document",
    "proof_of_address",
    "sanction_questionnaire",
    "institutional_questionnaire",
    "cdd_edd_questionnaire",
    "translation_certificate",
    "risk_calculator",
    "transaction_listing",
    "other",
}
ENTITY_TYPES = {
    "Private Limited Company",
    "Public Listed Company",
    "Partnership",
    "Sole Proprietor",
    "Foreign Corporation",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_required()
    init_db()
    seed_if_empty()
    yield


app = FastAPI(title="Wholesale Client Policy Validation", version="2.0.0", lifespan=lifespan)

PUBLIC_API = {"/api/login", "/api/health", "/api/me"}


@app.get("/api/me")
def me(request: Request) -> dict:
    token = request.cookies.get(auth.COOKIE_NAME)
    if not auth.is_valid(token):
        raise HTTPException(401, "Not authenticated")
    return {"username": settings.AUTH_USERNAME}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """Session auth guard for /api/* endpoints."""
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API:
        if not auth.is_valid(request.cookies.get(auth.COOKIE_NAME)):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _bundle_row(conn, bundle_id: str):
    row = conn.execute("SELECT * FROM customer_bundles WHERE id = ?", (bundle_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Customer bundle not found")
    return row


def _bundle_payload(conn, row) -> dict:
    docs = conn.execute(
        "SELECT id, doc_type, original_name, content_type, is_ctc, uploaded_at, size_bytes FROM documents WHERE bundle_id = ?",
        (row["id"],),
    ).fetchall()

    last_run = conn.execute(
        "SELECT * FROM validation_runs WHERE bundle_id = ? ORDER BY started_at DESC LIMIT 1",
        (row["id"],),
    ).fetchone()

    profile = conn.execute(
        "SELECT * FROM company_profiles WHERE bundle_id = ?", (row["id"],)
    ).fetchone()

    findings_count = 0
    last_run_dict = dict(last_run) if last_run else None
    if last_run_dict:
        run_id = last_run_dict["id"]
        raw_results = conn.execute("SELECT * FROM validation_results WHERE run_id = ?", (run_id,)).fetchall()
        raw_findings = conn.execute("SELECT * FROM validation_findings WHERE run_id = ?", (run_id,)).fetchall()
        findings_count = len(raw_findings)
        findings_list = [dict(f) for f in raw_findings]
        
        parsed_findings_objs = [
            ValidationFinding(
                check_id=f["check_id"],
                finding_type=f["finding_type"],
                severity=Priority(f["severity"]) if f["severity"] in ["HIGH", "MEDIUM", "LOW"] else Priority.HIGH,
                missing_document=f.get("missing_document"),
                reason=f["reason"],
                target_field=f.get("target_field"),
                details=f["details"] or "",
            )
            for f in findings_list
        ]

        results_list = []
        for r in raw_results:
            rd = dict(r)
            eval_files = []
            if rd.get("evaluated_files_json"):
                try:
                    eval_files = json.loads(rd["evaluated_files_json"])
                except Exception:
                    eval_files = []
            rd["evaluated_files"] = eval_files

            sub_checks = []
            if rd.get("sub_checks_json"):
                try:
                    sub_checks = json.loads(rd["sub_checks_json"])
                except Exception:
                    sub_checks = []
            if not sub_checks:
                eval_file_objs = [
                    ItemizedDocStatus(
                        doc_name=ef.get("doc_name", ""),
                        doc_type=ef.get("doc_type", ""),
                        verdict=Verdict(ef.get("verdict", "PASS")),
                        details=ef.get("details", ""),
                        reason=ef.get("reason"),
                        is_ctc=bool(ef.get("is_ctc", False)),
                    )
                    for ef in eval_files
                ]
                v_enum = Verdict(rd.get("verdict", "PASS")) if rd.get("verdict") in ["PASS", "FAIL", "NOT_APPLICABLE"] else Verdict.PASS
                sub_checks_objs = build_subchecks_for_result(
                    check_id=rd["check_id"],
                    verdict=v_enum,
                    findings=parsed_findings_objs,
                    evaluated_files=eval_file_objs,
                )
                sub_checks = [sc.model_dump() for sc in sub_checks_objs]
            rd["sub_checks"] = sub_checks
            results_list.append(rd)

        last_run_dict["results"] = results_list
        last_run_dict["findings"] = findings_list

        if last_run_dict.get("executive_summary_json"):
            try:
                last_run_dict["executive_summary"] = json.loads(last_run_dict["executive_summary_json"])
            except Exception:
                last_run_dict["executive_summary"] = None
        if not last_run_dict.get("executive_summary"):
            last_run_dict["executive_summary"] = build_executive_summary(
                bundle_name=row["name"],
                uen=row["uen"],
                entity_type=row["entity_type"],
                overall_verdict=last_run_dict.get("overall_verdict", "PASS"),
                passed_count=len([r for r in results_list if r.get("verdict") == "PASS"]),
                total_count=len(results_list),
                findings=parsed_findings_objs,
                elapsed_seconds=last_run_dict.get("elapsed_seconds"),
                total_tokens=last_run_dict.get("total_tokens") or 0,
                cost_usd=last_run_dict.get("estimated_cost_usd") or 0.0,
            )

    return {
        "id": row["id"],
        "name": row["name"],
        "uen": row["uen"] or (profile["uen"] if profile else None),
        "entity_type": row["entity_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "doc_count": len(docs),
        "documents": [dict(d) for d in docs],
        "profile": dict(profile) if profile else None,
        "last_run": last_run_dict,
        "findings_count": findings_count,
    }


# --------------------------------------------------------------------------
# Meta & Rules
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.OPENAI_VISION_MODEL,
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "persistent_storage": bool(settings.DATA_DIR),
        "checks_supported": [
            "CHK_01_BIZFILE",
            "CHK_02_INCORP",
            "CHK_03_CONST",
            "CHK_04_CORP_STRUCT",
            "CHK_05_ID_EXPIRY",
            "CHK_06_UBO_COMPLEX",
            "CHK_07_SANCTIONS",
            "CHK_08_INSTITUTIONAL",
            "CHK_09_CDD_EDD",
            "CHK_10_INGESTION_QUALITY",
            "CHK_11_MAS_REGISTER",
            "CHK_12_RISK_CALCULATOR",
            "CHK_13_DIGITAL_FOOTPRINT",
        ],
    }


@app.get("/api/rules")
def get_rules() -> list:
    return RULES


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
@app.post("/api/login")
def login(response: Response, username: str = Form(...), password: str = Form(...)) -> dict:
    if not auth.verify_credentials(username.strip(), password):
        raise HTTPException(401, "Invalid username or password")
    token = auth.create_session()
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    return {"ok": True, "username": settings.AUTH_USERNAME}


@app.post("/api/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


# --------------------------------------------------------------------------
# Customer Bundles
# --------------------------------------------------------------------------
@app.get("/api/bundles")
def list_bundles() -> list:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM customer_bundles ORDER BY created_at DESC").fetchall()
        return [_bundle_payload(conn, r) for r in rows]
    finally:
        conn.close()


@app.post("/api/bundles")
def create_bundle(
    name: str = Form(...),
    uen: Optional[str] = Form(None),
    entity_type: str = Form("Private Limited Company"),
) -> dict:
    name = name.strip()
    if not name:
        raise HTTPException(400, "Bundle/Client name is required")
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")

    bundle_id = new_id()
    now = now_iso()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO customer_bundles (id, name, uen, entity_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bundle_id, name, uen.strip() if uen else None, entity_type, "PENDING", now, now),
        )
        conn.commit()
        log_audit("CREATE_BUNDLE", bundle_id=bundle_id, details=f"Created bundle for {name}")
        row = _bundle_row(conn, bundle_id)
        return _bundle_payload(conn, row)
    finally:
        conn.close()


@app.get("/api/bundles/{bundle_id}")
def get_bundle(bundle_id: str) -> dict:
    conn = get_conn()
    try:
        row = _bundle_row(conn, bundle_id)
        payload = _bundle_payload(conn, row)

        # Append full directors, ubos, and extractions
        directors = conn.execute("SELECT * FROM directors WHERE bundle_id = ?", (bundle_id,)).fetchall()
        ubos = conn.execute("SELECT * FROM ubos WHERE bundle_id = ?", (bundle_id,)).fetchall()
        payload["directors"] = [dict(d) for d in directors]
        payload["ubos"] = [dict(u) for u in ubos]

        # Append last run results and findings
        if payload.get("last_run"):
            run_id = payload["last_run"]["id"]
            raw_results = conn.execute("SELECT * FROM validation_results WHERE run_id = ?", (run_id,)).fetchall()
            results = []
            for r in raw_results:
                rd = dict(r)
                if rd.get("evaluated_files_json"):
                    try:
                        rd["evaluated_files"] = json.loads(rd["evaluated_files_json"])
                    except Exception:
                        rd["evaluated_files"] = []
                else:
                    rd["evaluated_files"] = []
                results.append(rd)

            findings = conn.execute("SELECT * FROM validation_findings WHERE run_id = ?", (run_id,)).fetchall()
            payload["last_run"]["results"] = results
            payload["last_run"]["findings"] = [dict(f) for f in findings]

        return payload
    finally:
        conn.close()


@app.delete("/api/bundles/{bundle_id}")
def delete_bundle(bundle_id: str) -> dict:
    conn = get_conn()
    try:
        row = _bundle_row(conn, bundle_id)
        docs = conn.execute("SELECT stored_name FROM documents WHERE bundle_id = ?", (bundle_id,)).fetchall()
        for d in docs:
            p = settings.storage_dir / d["stored_name"]
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        conn.execute("DELETE FROM customer_bundles WHERE id = ?", (bundle_id,))
        conn.commit()
        log_audit("DELETE_BUNDLE", bundle_id=bundle_id, details=f"Deleted bundle {row['name']}")
        return {"ok": True}
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Multi-file / Document Ingestion
# --------------------------------------------------------------------------
@app.post("/api/bundles/{bundle_id}/documents/batch")
async def upload_documents_batch(
    bundle_id: str,
    files: List[UploadFile] = File(...),
) -> dict:
    conn = get_conn()
    try:
        _bundle_row(conn, bundle_id)
    finally:
        conn.close()

    uploaded = []
    for file in files:
        original_name = file.filename or "doc"
        # Extract filename if full path was sent (folder uploads)
        original_name = Path(original_name).name
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXT:
            continue

        doc_id = new_id()
        stored_name = f"{doc_id}{ext}"
        storage_path = settings.storage_dir / stored_name

        content = await file.read()
        storage_path.write_bytes(content)

        page_count = 1
        if ext == ".pdf":
            try:
                with pymupdf.open(storage_path) as pdf:
                    page_count = len(pdf)
            except Exception:
                page_count = 1

        initial_doc_type = "unclassified"
        fname_lower = original_name.lower()
        fname_clean = " " + re.sub(r"[^a-z0-9]", " ", fname_lower) + " "

        def has_words(*words):
            for w in words:
                if re.search(rf"\b{re.escape(w)}\b", fname_clean):
                    return True
            return False

        if ext in {".csv", ".xlsx", ".xls"}:
            if any(k in fname_lower for k in ["risk", "calc", "matrix", "score"]):
                initial_doc_type = "risk_calculator"
            else:
                initial_doc_type = "transaction_listing"
        # 1. ID documents (Check FIRST so "UBO ID.jpg" or "Director ID.png" is id_document, NOT ubo_declaration)
        elif has_words("passport", "passports", "nric", "fin", "id", "ids", "identity", "identification", "license", "licence", "driving"):
            initial_doc_type = "id_document"
        # 2. Proof of Address (utility, bill, address, poa, etc.)
        elif has_words("utility", "utilities", "uttility", "bill", "bills", "poa", "address", "electricity", "water", "telecom", "tenancy", "residential", "statement", "council"):
            initial_doc_type = "proof_of_address"
        elif any(k in fname_lower for k in ["bizfile", "profile", "acra", "search"]):
            initial_doc_type = "bizfile"
        elif any(k in fname_lower for k in ["m&aa", "maa", "memorandum", "articles", "constitution"]):
            initial_doc_type = "maa"
        elif any(k in fname_lower for k in ["rom", "member", "shareholder"]):
            initial_doc_type = "rom"
        elif any(k in fname_lower for k in ["rod", "director", "directors"]):
            initial_doc_type = "rod"
        elif any(k in fname_lower for k in ["ubo", "beneficial owner", "gldb"]):
            initial_doc_type = "ubo_declaration"
        elif any(k in fname_lower for k in ["cdd", "edd"]):
            initial_doc_type = "cdd_edd_questionnaire"
        elif any(k in fname_lower for k in ["sanction"]):
            initial_doc_type = "sanction_questionnaire"
        elif any(k in fname_lower for k in ["wolfsberg", "msb"]):
            initial_doc_type = "institutional_questionnaire"
        elif any(k in fname_lower for k in ["trans", "tx", "statement", "ledger", "listing"]):
            initial_doc_type = "transaction_listing"

        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO documents 
                (id, bundle_id, doc_type, original_name, stored_name, content_type, page_count, size_bytes, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    bundle_id,
                    initial_doc_type,
                    original_name,
                    stored_name,
                    file.content_type or "application/octet-stream",
                    page_count,
                    len(content),
                    now_iso(),
                ),
            )
            conn.commit()
            uploaded.append(original_name)
        finally:
            conn.close()

    log_audit("UPLOAD_BATCH", bundle_id=bundle_id, details=f"Batch uploaded {len(uploaded)} files")
    return {"count": len(uploaded), "files": uploaded}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    conn = get_conn()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise HTTPException(404, "Document not found")
        p = settings.storage_dir / doc["stored_name"]
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        log_audit("DELETE_DOCUMENT", bundle_id=doc["bundle_id"], details=f"Deleted {doc['original_name']}")
        return {"ok": True}
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Verification & State Machine Execution
# --------------------------------------------------------------------------
@app.post("/api/bundles/{bundle_id}/verify")
def verify_bundle(bundle_id: str) -> dict:
    try:
        summary = run_wholesale_verification(bundle_id)
        return summary.model_dump()
    except Exception as e:
        raise HTTPException(500, f"Verification failed: {str(e)}")


@app.post("/api/verify-all")
def verify_all_bundles() -> dict:
    conn = get_conn()
    try:
        bundles = conn.execute("SELECT id FROM customer_bundles").fetchall()
    finally:
        conn.close()

    results = []
    for b in bundles:
        try:
            res = run_wholesale_verification(b["id"])
            results.append({"bundle_id": b["id"], "verdict": res.overall_verdict.value, "ok": True})
        except Exception as e:
            results.append({"bundle_id": b["id"], "error": str(e), "ok": False})

    return {"processed": len(results), "results": results}


# --------------------------------------------------------------------------
# PDF Audit Report Export
# --------------------------------------------------------------------------
@app.get("/api/bundles/{bundle_id}/report.pdf")
def export_bundle_report(bundle_id: str):
    conn = get_conn()
    try:
        row = _bundle_row(conn, bundle_id)
        payload = _bundle_payload(conn, row)
        directors = conn.execute("SELECT * FROM directors WHERE bundle_id = ?", (bundle_id,)).fetchall()
        ubos = conn.execute("SELECT * FROM ubos WHERE bundle_id = ?", (bundle_id,)).fetchall()
        payload["directors"] = [dict(d) for d in directors]
        payload["ubos"] = [dict(u) for u in ubos]

        if payload.get("last_run"):
            run_id = payload["last_run"]["id"]
            results = conn.execute("SELECT * FROM validation_results WHERE run_id = ?", (run_id,)).fetchall()
            findings = conn.execute("SELECT * FROM validation_findings WHERE run_id = ?", (run_id,)).fetchall()
            payload["last_run"]["results"] = [dict(r) for r in results]
            payload["last_run"]["findings"] = [dict(f) for f in findings]
    finally:
        conn.close()

    pdf_bytes = render_wholesale_pdf(payload)
    safe_title = (row["name"] or "Client").replace(" ", "_")
    filename = f"Wholesale_Validation_Report_{safe_title}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quote(filename)}"'},
    )


# --------------------------------------------------------------------------
# Static Assets / Single-Page Frontend
# --------------------------------------------------------------------------
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(frontend_dir / "index.html")

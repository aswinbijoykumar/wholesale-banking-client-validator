"""Wholesale Banking KYC & Policy Validation Engine — FastAPI backend.

Serves the wholesale client dashboard and REST API for customer bundles,
document extractions, validation state machine execution, and audit report generation.
"""
import json
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
from .rules import RULES
from .seed import seed_if_empty
from .verifier import run_wholesale_verification
from .reports import render_wholesale_pdf

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
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
        "SELECT id, state, overall_verdict, summary, started_at, completed_at, error "
        "FROM validation_runs WHERE bundle_id = ? ORDER BY started_at DESC LIMIT 1",
        (row["id"],),
    ).fetchone()

    profile = conn.execute(
        "SELECT * FROM company_profiles WHERE bundle_id = ?", (row["id"],)
    ).fetchone()

    findings_count = 0
    if last_run:
        fc = conn.execute(
            "SELECT COUNT(*) as c FROM validation_findings WHERE run_id = ?", (last_run["id"],)
        ).fetchone()
        findings_count = fc["c"] if fc else 0

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
        "last_run": dict(last_run) if last_run else None,
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

        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO documents 
                (id, bundle_id, doc_type, original_name, stored_name, content_type, page_count, size_bytes, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    bundle_id,
                    "unclassified",
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

"""Wholesale Banking Ingestion & Verification Orchestrator.

Orchestrates the entire multi-phase state machine:
UPLOADED -> CLASSIFYING -> EXTRACTING -> OCR_PROCESSING -> VISION_PROCESSING -> NORMALIZING -> VALIDATING -> COMPLETED
"""
import json
import time
from datetime import date
from pathlib import Path
from typing import Dict, Any, List

from .config import settings
from .db import get_conn, now_iso, new_id, log_audit
from .models import (
    ProcessingState,
    RawDocExtraction,
    DocType,
    Verdict,
    ValidationSummary,
)
from .pipeline import extract_document_with_vision
from .validator import validate_wholesale_bundle
from .services.cost_estimator import calculate_cost_usd, record_run_estimation
from .validators.subcheck_matrix import build_subchecks_for_result, build_executive_summary



def update_run_state(conn, run_id: str, state: ProcessingState, error: str | None = None):
    conn.execute(
        "UPDATE validation_runs SET state = ?, error = ? WHERE id = ?",
        (state.value, error, run_id),
    )
    conn.commit()


def run_wholesale_verification(bundle_id: str, today: date | None = None) -> ValidationSummary:
    run_start_time = time.perf_counter()
    if today is None:
        today = date.today()

    conn = get_conn()
    try:
        bundle = conn.execute("SELECT * FROM customer_bundles WHERE id = ?", (bundle_id,)).fetchone()
        if not bundle:
            raise ValueError(f"Customer bundle {bundle_id} not found.")

        # Create validation_run record
        run_id = new_id()
        conn.execute(
            "INSERT INTO validation_runs (id, bundle_id, state, started_at) VALUES (?, ?, ?, ?)",
            (run_id, bundle_id, ProcessingState.UPLOADED.value, now_iso()),
        )
        conn.commit()
        log_audit("START_VALIDATION_RUN", bundle_id=bundle_id, run_id=run_id, details=f"Starting verification for {bundle['name']}")

        docs = conn.execute(
            "SELECT * FROM documents WHERE bundle_id = ? ORDER BY uploaded_at ASC",
            (bundle_id,),
        ).fetchall()

        # Phase 1: CLASSIFYING & EXTRACTING
        update_run_state(conn, run_id, ProcessingState.CLASSIFYING)
        extractions: List[RawDocExtraction] = []

        storage = settings.storage_dir

        for doc in docs:
            doc_path = storage / doc["stored_name"]
            if not doc_path.exists():
                continue

            update_run_state(conn, run_id, ProcessingState.VISION_PROCESSING)
            ext = extract_document_with_vision(doc_path, doc["original_name"], today=today)
            extractions.append(ext)

            # Update document table with classified doc_type and is_ctc
            conn.execute(
                "UPDATE documents SET doc_type = ?, is_ctc = ? WHERE id = ?",
                (ext.doc_type.value, 1 if ext.is_ctc else 0, doc["id"]),
            )

            # Store extraction details
            conn.execute(
                "INSERT INTO document_extractions (id, document_id, ocr_engine, raw_text, extracted_json, extracted_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    doc["id"],
                    "pymupdf+ocr+gpt-4o",
                    ext.notes or "",
                    ext.model_dump_json(),
                    now_iso(),
                ),
            )
            conn.commit()

        # Phase 2: NORMALIZING
        update_run_state(conn, run_id, ProcessingState.NORMALIZING)

        # Phase 3: VALIDATING (Deterministic Rules)
        update_run_state(conn, run_id, ProcessingState.VALIDATING)
        check_results, findings, profile = validate_wholesale_bundle(
            bundle_name=bundle["name"],
            bundle_entity_type=bundle["entity_type"],
            extractions=extractions,
            today=today,
        )

        # Store company profile
        conn.execute(
            """INSERT OR REPLACE INTO company_profiles 
            (id, bundle_id, legal_name, uen, former_names, entity_type, incorporation_date, country_of_operations, company_status, bizfile_date, is_bizfile_fresh_12m, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id(),
                bundle_id,
                profile.legal_name,
                profile.uen,
                profile.former_names,
                profile.entity_type,
                profile.incorporation_date,
                profile.country_of_operations,
                profile.company_status,
                profile.bizfile_date,
                1 if profile.is_bizfile_fresh_12m else 0,
                now_iso(),
            ),
        )

        # Store Directors & UBOs
        conn.execute("DELETE FROM directors WHERE bundle_id = ?", (bundle_id,))
        for d in profile.directors:
            conn.execute(
                "INSERT INTO directors (id, bundle_id, name, id_number, nationality, appointment_date, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id(), bundle_id, d.name, d.id_number, d.nationality, d.appointment_date, d.status),
            )

        conn.execute("DELETE FROM ubos WHERE bundle_id = ?", (bundle_id,))
        for u in profile.ubos:
            conn.execute(
                "INSERT INTO ubos (id, bundle_id, name, id_number, ownership_percentage, share_count, is_controller) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id(), bundle_id, u.name, u.id_number, u.ownership_percentage, u.share_count, 1 if u.is_controller else 0),
            )

        # Determine overall verdict
        has_fail = any(r.verdict == Verdict.FAIL for r in check_results)
        overall_verdict = Verdict.FAIL if has_fail else Verdict.PASS
        summary_text = (
            f"Validation Completed: {overall_verdict.value}. "
            f"{len([r for r in check_results if r.verdict == Verdict.PASS])}/{len(check_results)} checks passed."
        )

        # Generate Sub-Checks for each check result
        for cr in check_results:
            cr.sub_checks = build_subchecks_for_result(
                check_id=cr.check_id,
                verdict=cr.verdict,
                findings=findings,
                evaluated_files=cr.evaluated_files,
            )

        # Store Check Results & Findings
        for cr in check_results:
            result_id = new_id()
            eval_files_json = json.dumps([ef.model_dump() for ef in cr.evaluated_files])
            sub_checks_json = json.dumps([sc.model_dump() for sc in cr.sub_checks])
            conn.execute(
                "INSERT INTO validation_results (id, run_id, check_id, rule_name, verdict, reason_code, priority, evidence, evaluated_files_json, sub_checks_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id,
                    run_id,
                    cr.check_id,
                    cr.rule_name,
                    cr.verdict.value,
                    cr.reason_code,
                    cr.priority.value,
                    cr.evidence,
                    eval_files_json,
                    sub_checks_json,
                    now_iso(),
                ),
            )

        for f in findings:
            conn.execute(
                "INSERT INTO validation_findings (id, run_id, check_id, finding_type, severity, missing_document, reason, target_field, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    run_id,
                    f.check_id,
                    f.finding_type,
                    f.severity.value,
                    f.missing_document,
                    f.reason,
                    f.target_field,
                    f.details,
                    now_iso(),
                ),
            )

        # Performance & Cost Telemetry
        total_prompt_tokens = sum(getattr(e, "prompt_tokens", 0) for e in extractions)
        total_completion_tokens = sum(getattr(e, "completion_tokens", 0) for e in extractions)
        total_tokens = sum(getattr(e, "total_tokens", 0) for e in extractions)
        elapsed_seconds = round(time.perf_counter() - run_start_time, 2)
        estimated_cost_usd = calculate_cost_usd(total_prompt_tokens, total_completion_tokens)

        # Build Executive Summary
        exec_summary = build_executive_summary(
            bundle_name=bundle["name"],
            uen=bundle["uen"],
            entity_type=bundle["entity_type"],
            overall_verdict=overall_verdict.value,
            passed_count=len([r for r in check_results if r.verdict == Verdict.PASS]),
            total_count=len(check_results),
            findings=findings,
            elapsed_seconds=elapsed_seconds,
            total_tokens=total_tokens,
            cost_usd=estimated_cost_usd,
        )

        # Complete Run
        conn.execute(
            """UPDATE validation_runs 
            SET state = ?, overall_verdict = ?, summary = ?, completed_at = ?,
                prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, elapsed_seconds = ?, estimated_cost_usd = ?,
                executive_summary_json = ?
            WHERE id = ?""",
            (
                ProcessingState.COMPLETED.value,
                overall_verdict.value,
                summary_text,
                now_iso(),
                total_prompt_tokens,
                total_completion_tokens,
                total_tokens,
                elapsed_seconds,
                estimated_cost_usd,
                json.dumps(exec_summary),
                run_id,
            ),
        )
        conn.execute("UPDATE customer_bundles SET status = ?, updated_at = ? WHERE id = ?", (overall_verdict.value, now_iso(), bundle_id))
        conn.commit()

        log_audit(
            "COMPLETE_VALIDATION_RUN",
            bundle_id=bundle_id,
            run_id=run_id,
            details=f"Verdict: {overall_verdict.value} | Time: {elapsed_seconds}s | Tokens: {total_tokens} | Cost: ${estimated_cost_usd:.4f}",
        )

        # File estimation report into estimations/ folder
        try:
            record_run_estimation(
                run_id=run_id,
                bundle_id=bundle_id,
                bundle_name=bundle["name"],
                entity_type=bundle["entity_type"],
                overall_verdict=overall_verdict.value,
                summary_text=summary_text,
                elapsed_seconds=elapsed_seconds,
                total_prompt_tokens=total_prompt_tokens,
                total_completion_tokens=total_completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                extractions=extractions,
                check_results=check_results,
            )
        except Exception as e:
            print(f"Warning: Failed to record estimation file: {e}")

        return ValidationSummary(
            bundle_id=bundle_id,
            run_id=run_id,
            overall_verdict=overall_verdict,
            summary=summary_text,
            results=check_results,
            findings=findings,
            elapsed_seconds=elapsed_seconds,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            executive_summary=exec_summary,
        )
    except Exception as e:
        conn.rollback()
        try:
            update_run_state(conn, run_id, ProcessingState.FAILED, error=str(e))
            log_audit("FAILED_VALIDATION_RUN", bundle_id=bundle_id, run_id=run_id, details=str(e))
        except Exception:
            pass
        raise e
    finally:
        conn.close()

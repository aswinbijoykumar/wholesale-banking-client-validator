"""Cost and Performance Estimation Service for Wholesale Banking Policy Validation.

Tracks token consumption, execution latency, and financial costs per validation run.
Files comprehensive audit records into the 'estimations/' folder in 'estimations.txt'
and per-run breakdown files to assist with deployment cost modeling and monitoring.
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from ..config import BASE_DIR
from ..models import CheckResult, RawDocExtraction, Verdict

# Target output directory
ESTIMATIONS_DIR: Path = BASE_DIR / "estimations"

# Pricing rates based on standard OpenAI API pricing (GPT-4o)
# Prompt: $2.50 / 1,000,000 tokens ($0.0000025 per token)
# Completion: $10.00 / 1,000,000 tokens ($0.000010 per token)
PRICE_PER_M_PROMPT = 2.50
PRICE_PER_M_COMPLETION = 10.00
USD_TO_SGD_RATE = 1.35


def calculate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate estimated cost in USD based on token counts."""
    p_cost = (prompt_tokens / 1_000_000.0) * PRICE_PER_M_PROMPT
    c_cost = (completion_tokens / 1_000_000.0) * PRICE_PER_M_COMPLETION
    return round(p_cost + c_cost, 6)


def record_run_estimation(
    run_id: str,
    bundle_id: str,
    bundle_name: str,
    entity_type: str,
    overall_verdict: str,
    summary_text: str,
    elapsed_seconds: float,
    total_prompt_tokens: int,
    total_completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    extractions: List[RawDocExtraction],
    check_results: List[CheckResult],
) -> Path:
    """Record comprehensive cost and execution metrics into estimations/estimations.txt and a run-specific file."""
    ESTIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estimated_cost_sgd = round(estimated_cost_usd * USD_TO_SGD_RATE, 4)
    
    passed_checks = len([r for r in check_results if r.verdict == Verdict.PASS])
    total_checks = len(check_results)
    
    # Generate itemized document table
    doc_lines = []
    for ext in extractions:
        doc_fname = ext.filename or "Unnamed Document"
        is_tabular = getattr(ext, "is_transaction_listing", False) or doc_fname.lower().endswith((".csv", ".xlsx", ".xls"))
        engine_label = "Deterministic Tabular Parser (Zero-Token)" if is_tabular else "OpenAI GPT-4o Vision API"
        p_tok = getattr(ext, "prompt_tokens", 0)
        c_tok = getattr(ext, "completion_tokens", 0)
        t_tok = getattr(ext, "total_tokens", 0)
        t_sec = getattr(ext, "extraction_time_seconds", 0.0)
        d_cost = calculate_cost_usd(p_tok, c_tok)
        
        doc_lines.append(
            f"  * {doc_fname}\n"
            f"    - Ingestion Method   : {engine_label}\n"
            f"    - Detected Type      : {ext.doc_type.value if hasattr(ext.doc_type, 'value') else ext.doc_type}\n"
            f"    - Tokens (In / Out)  : {p_tok:,} prompt / {c_tok:,} completion (Total: {t_tok:,})\n"
            f"    - Extraction Time    : {t_sec:.2f}s\n"
            f"    - Document Cost      : ${d_cost:.5f} USD\n"
        )
    
    doc_table_str = "".join(doc_lines) if doc_lines else "  (No documents ingested)\n"

    # Deployment cost projections
    cost_per_100 = estimated_cost_usd * 100
    cost_per_1000 = estimated_cost_usd * 1000
    cost_per_100_sgd = cost_per_100 * USD_TO_SGD_RATE
    cost_per_1000_sgd = cost_per_1000 * USD_TO_SGD_RATE
    est_throughput_per_hr = int(3600 / elapsed_seconds) if elapsed_seconds > 0 else 0

    entry_block = f"""
================================================================================
WHOLESALE BANKING POLICY VALIDATION — RUN COST & PERFORMANCE ESTIMATION
================================================================================
Timestamp               : {timestamp_str}
Run ID                  : {run_id}
Customer Bundle         : {bundle_name} (ID: {bundle_id})
Entity Type             : {entity_type}
Validation Verdict      : {overall_verdict} ({passed_checks}/{total_checks} Checks Passed)
Summary                 : {summary_text}
Total Run Duration      : {elapsed_seconds:.2f} seconds
--------------------------------------------------------------------------------
TOKEN CONSUMPTION METRICS (OpenAI GPT-4o)
--------------------------------------------------------------------------------
Prompt (Input) Tokens   : {total_prompt_tokens:,} tokens
Completion (Output)     : {total_completion_tokens:,} tokens
Total Tokens Used       : {total_tokens:,} tokens
--------------------------------------------------------------------------------
FINANCIAL COST BREAKDOWN
--------------------------------------------------------------------------------
Prompt Cost ($2.50/1M)  : ${((total_prompt_tokens / 1_000_000) * PRICE_PER_M_PROMPT):.6f} USD
Output Cost ($10.00/1M) : ${((total_completion_tokens / 1_000_000) * PRICE_PER_M_COMPLETION):.6f} USD
Total Estimated Cost    : ${estimated_cost_usd:.5f} USD (~SGD {estimated_cost_sgd:.4f})
--------------------------------------------------------------------------------
ITEMIZED DOCUMENT EXTRACTION BREAKDOWN ({len(extractions)} files)
--------------------------------------------------------------------------------
{doc_table_str}--------------------------------------------------------------------------------
DEPLOYMENT COST PROJECTIONS FOR STAKEHOLDERS
--------------------------------------------------------------------------------
Estimated Cost per 1 Corporate Bundle   : ${estimated_cost_usd:.4f} USD (~SGD {estimated_cost_sgd:.3f})
Estimated Cost per 100 Client Bundles   : ${cost_per_100:.2f} USD (~SGD {cost_per_100_sgd:.2f})
Estimated Cost per 1,000 Client Bundles : ${cost_per_1000:.2f} USD (~SGD {cost_per_1000_sgd:.2f})
Estimated Single-Worker Throughput      : ~{est_throughput_per_hr} client files / hour
================================================================================
"""

    # 1. Append to consolidated estimations.txt
    consolidated_file = ESTIMATIONS_DIR / "estimations.txt"
    with open(consolidated_file, "a", encoding="utf-8") as f:
        f.write(entry_block)

    # 2. Write individual run file
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", bundle_name)[:30]
    run_file = ESTIMATIONS_DIR / f"run_{run_id[:8]}_{safe_name}.txt"
    run_file.write_text(entry_block.strip() + "\n", encoding="utf-8")

    return consolidated_file

"""Branded PDF Audit Report Generator for Wholesale Banking Policy Verification."""
import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate,
    Paragraph, Spacer, Table, TableStyle
)

from .config import BASE_DIR

# Professional Wholesale Banking Palette
NAVY        = colors.HexColor("#0f172a")
BLUE        = colors.HexColor("#1e3a8a")
BLUE_LT     = colors.HexColor("#f0f4f8")
TEAL        = colors.HexColor("#0d9488")
PASS        = colors.HexColor("#16a34a")
PASS_BG     = colors.HexColor("#dcfce7")
PASS_BORDER = colors.HexColor("#86efac")
FAIL        = colors.HexColor("#dc2626")
FAIL_BG     = colors.HexColor("#fee2e2")
FAIL_BORDER = colors.HexColor("#fca5a5")
WARN        = colors.HexColor("#d97706")
WARN_BG     = colors.HexColor("#fef3c7")
MUTED       = colors.HexColor("#64748b")
BORDER      = colors.HexColor("#e2e8f0")
WHITE       = colors.white

LOGO_PATH = BASE_DIR / "frontend" / "logo.png"


def _page_decor(canvas, doc):
    w, h = A4
    if LOGO_PATH.exists():
        try:
            canvas.drawImage(str(LOGO_PATH), 18*mm, h - 24*mm, width=40*mm, height=14*mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawRightString(w - 18*mm, h - 17*mm, "WHOLESALE CLIENT POLICY AUDIT")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 18*mm, h - 22*mm, "Corporate Document Compliance & Policy Engine")

    y = h - 26*mm
    canvas.setLineWidth(1.2)
    canvas.setStrokeColor(BLUE)
    canvas.line(18*mm, y, w - 18*mm, y)

    # Footer
    canvas.setLineWidth(0.5)
    canvas.setStrokeColor(BORDER)
    canvas.line(18*mm, 16*mm, w - 18*mm, 16*mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18*mm, 11*mm, "CONFIDENTIAL — FOR INTERNAL WHOLESALE BANKING COMPLIANCE USE ONLY")
    canvas.drawRightString(w - 18*mm, 11*mm, f"Page {doc.page}")


def render_wholesale_pdf(bundle_payload: dict) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm,
        rightMargin=18*mm,
        topMargin=30*mm,
        bottomMargin=22*mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    template = PageTemplate(id="audit_page", frames=frame, onPage=_page_decor)
    doc.addPageTemplates([template])

    styles = {
        "title": ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY),
        "subtitle": ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED),
        "h2": ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("Body", fontName="Helvetica", fontSize=8.5, leading=12, textColor=NAVY),
        "evidence": ParagraphStyle("Evidence", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=MUTED),
        "fail_text": ParagraphStyle("FailText", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=FAIL),
        "pass_text": ParagraphStyle("PassText", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=PASS),
    }

    story = []

    # Title & Client Header
    story.append(Paragraph(bundle_payload.get("name", "Corporate Client File"), styles["title"]))
    uen_txt = f"UEN: {bundle_payload.get('uen') or 'N/A'}"
    type_txt = f"Entity Type: {bundle_payload.get('entity_type', 'Private Limited Company')}"
    audit_date = datetime.now().strftime("%d %b %Y, %H:%M UTC")
    story.append(Paragraph(f"{uen_txt} &nbsp;|&nbsp; {type_txt} &nbsp;|&nbsp; Audit Date: {audit_date}", styles["subtitle"]))
    story.append(Spacer(1, 4*mm))

    # Overall Status Banner
    last_run = bundle_payload.get("last_run") or {}
    overall = str(last_run.get("overall_verdict") or "PENDING")
    is_pass = overall == "PASS"

    banner_bg = PASS_BG if is_pass else FAIL_BG
    banner_border = PASS_BORDER if is_pass else FAIL_BORDER
    banner_color = PASS if is_pass else FAIL

    summary_text = str(last_run.get("summary") or "Validation pending.")
    exec_summary = last_run.get("executive_summary") or {}

    banner_content = [
        [
            Paragraph(f"<b>OVERALL VERDICT: {overall}</b>", ParagraphStyle("BannerTitle", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=banner_color)),
            Paragraph(summary_text, ParagraphStyle("BannerSub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=NAVY)),
        ]
    ]
    banner_table = Table(banner_content, colWidths=[55*mm, 119*mm])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), banner_bg),
        ("BOX", (0, 0), (-1, -1), 1, banner_border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 4*mm))

    # Executive Summary & Risk Highlights
    if exec_summary:
        story.append(Paragraph("Executive Compliance Summary", styles["h2"]))
        exec_rows = [
            [
                Paragraph("<b>Compliance Score</b>", styles["body"]),
                Paragraph(f"<b>{exec_summary.get('compliance_percentage', 0)}%</b> ({exec_summary.get('passed_count', 0)}/{exec_summary.get('total_count', 14)} Passed)", styles["pass_text"] if is_pass else styles["fail_text"]),
                Paragraph("<b>Assigned Risk Tier</b>", styles["body"]),
                Paragraph(f"<b>{exec_summary.get('risk_tier', 'Standard')}</b>", styles["body"]),
            ],
            [
                Paragraph("<b>Executive Findings</b>", styles["body"]),
                Paragraph(exec_summary.get("narrative", summary_text), styles["body"]),
                Paragraph("<b>Recommendation</b>", styles["body"]),
                Paragraph(exec_summary.get("recommendation", "Review required."), styles["fail_text"] if not is_pass else styles["pass_text"]),
            ],
        ]
        exec_table = Table(exec_rows, colWidths=[38*mm, 52*mm, 34*mm, 50*mm])
        exec_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE_LT),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(exec_table)
        story.append(Spacer(1, 4*mm))

    # Check Results & Granular Sub-Checks
    story.append(Paragraph("Wholesale Policy Check Breakdown & Granular Sub-Checks", styles["h2"]))
    results = last_run.get("results") or []

    if not results:
        story.append(Paragraph("No verification checks executed yet.", styles["body"]))
    else:
        for r in results:
            r_pass = r.get("verdict") == "PASS"
            badge_color = PASS if r_pass else FAIL
            badge_bg = PASS_BG if r_pass else FAIL_BG
            badge_border = PASS_BORDER if r_pass else FAIL_BORDER

            # Evaluated / Cross-checked files text
            eval_files = r.get("evaluated_files") or []
            files_txt = ", ".join([f"{ef.get('doc_name')} ({ef.get('doc_type')})" for ef in eval_files]) if eval_files else "Master Client Bundle Dossier"

            card_rows = [
                [
                    Paragraph(f"<b>{r.get('check_id', 'CHK')} — {r.get('rule_name', 'Rule')}</b>", ParagraphStyle("CardHead", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=NAVY)),
                    Paragraph(f"<b>{r.get('verdict', 'PENDING')}</b>", ParagraphStyle("CardBadge", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=badge_color, alignment=2)),
                ],
                [
                    Paragraph(f"<b>Evidence & Findings:</b> {str(r.get('evidence') or 'None')}", styles["body"]),
                    Paragraph(f"Priority: <b>{str(r.get('priority') or 'HIGH')}</b>", styles["subtitle"]),
                ],
                [
                    Paragraph(f"<b>Cross-Checked Files:</b> <font color='#64748b'>{files_txt}</font>", styles["body"]),
                    Paragraph(f"Reason: <b>{r.get('reason_code') or 'COMPLIANT'}</b>", styles["subtitle"]),
                ],
            ]

            card_table = Table(card_rows, colWidths=[134*mm, 40*mm])
            card_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.append(card_table)

            # Granular sub-checks table
            sub_checks = r.get("sub_checks") or []
            if sub_checks:
                sub_rows = [
                    [
                        Paragraph("<b>Sub-Check ID & Title</b>", styles["body"]),
                        Paragraph("<b>Status</b>", styles["body"]),
                        Paragraph("<b>Verification Criteria & Result</b>", styles["body"]),
                    ]
                ]
                for sc in sub_checks:
                    sc_pass = sc.get("verdict") == "PASS"
                    sc_style = styles["pass_text"] if sc_pass else styles["fail_text"]
                    sub_rows.append([
                        Paragraph(f"<b>{sc.get('sub_id')}</b>: {sc.get('name')}", styles["body"]),
                        Paragraph(f"<b>{sc.get('verdict')}</b>", sc_style),
                        Paragraph(str(sc.get("details") or sc.get("description")), styles["body"]),
                    ])
                sub_table = Table(sub_rows, colWidths=[56*mm, 20*mm, 98*mm])
                sub_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(sub_table)

            story.append(Spacer(1, 3*mm))


    # Detailed Explainable Findings
    findings = last_run.get("findings") or []
    if findings:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("Explainable Findings & Actionable Gaps", styles["h2"]))
        finding_rows = [
            [
                Paragraph("<b>Check ID</b>", styles["body"]),
                Paragraph("<b>Reason Code</b>", styles["body"]),
                Paragraph("<b>Severity</b>", styles["body"]),
                Paragraph("<b>Details & Gap Description</b>", styles["body"]),
            ]
        ]
        for f in findings:
            finding_rows.append([
                Paragraph(str(f.get("check_id") or ""), styles["body"]),
                Paragraph(str(f.get("reason") or "GAP"), styles["fail_text"]),
                Paragraph(str(f.get("severity") or "HIGH"), styles["body"]),
                Paragraph(str(f.get("details") or ""), styles["body"]),
            ])
        f_table = Table(finding_rows, colWidths=[30*mm, 42*mm, 22*mm, 80*mm])
        f_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE_LT),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(f_table)

    # Ingested Documents List
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Ingested File Evidence & CTC Status", styles["h2"]))
    docs = bundle_payload.get("documents", [])
    if not docs:
        story.append(Paragraph("No documents uploaded for this client bundle.", styles["body"]))
    else:
        doc_rows = [
            [
                Paragraph("<b>Filename</b>", styles["body"]),
                Paragraph("<b>Classified Type</b>", styles["body"]),
                Paragraph("<b>Certified True Copy (CTC)</b>", styles["body"]),
                Paragraph("<b>Uploaded At</b>", styles["body"]),
            ]
        ]
        for d in docs:
            ctc_label = "Verified CTC (Stamp/Sig)" if d.get("is_ctc") else "Standard Copy"
            ctc_style = styles["pass_text"] if d.get("is_ctc") else styles["body"]
            doc_rows.append([
                Paragraph(d.get("original_name", "file"), styles["body"]),
                Paragraph(d.get("doc_type", "unclassified"), styles["body"]),
                Paragraph(ctc_label, ctc_style),
                Paragraph(str(d.get("uploaded_at", ""))[:19].replace("T", " "), styles["subtitle"]),
            ])
        d_table = Table(doc_rows, colWidths=[64*mm, 40*mm, 40*mm, 30*mm])
        d_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE_LT),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(d_table)

    doc.build(story)
    return buf.getvalue()

from datetime import date
from typing import List
from dateutil import parser as date_parser

from backend.models import (
    DocType,
    EntityType,
    NormalizedCompanyProfile,
    RawDocExtraction,
)


def parse_date_safe(d_str: str | None) -> date | None:
    if not d_str:
        return None
    try:
        return date_parser.parse(d_str).date()
    except Exception:
        return None


def calculate_month_diff(d1: date, d2: date) -> int:
    return (d1.year - d2.year) * 12 + (d1.month - d2.month)


class BundleContext:
    """Pre-segments documents once so individual rules do not duplicate filtering loops."""

    def __init__(
        self,
        bundle_name: str,
        bundle_entity_type: str,
        extractions: List[RawDocExtraction],
        today: date,
    ):
        self.bundle_name = bundle_name
        self.bundle_entity_type = bundle_entity_type
        self.extractions = extractions
        self.today = today

        # Document grouping by shared types
        self.bizfile_docs = [e for e in extractions if e.doc_type == DocType.BIZFILE]
        self.incorp_docs = [e for e in extractions if e.doc_type == DocType.CERT_INCORPORATION]
        self.maa_docs = [e for e in extractions if e.doc_type == DocType.MAA]
        self.rom_docs = [e for e in extractions if e.doc_type == DocType.ROM]
        self.rod_docs = [e for e in extractions if e.doc_type == DocType.ROD]
        self.board_docs = [e for e in extractions if e.doc_type == DocType.BOARD_RESOLUTION]
        self.ubo_decl_docs = [e for e in extractions if e.doc_type == DocType.UBO_DECLARATION]
        self.id_docs = [e for e in extractions if e.doc_type == DocType.ID_DOCUMENT]
        self.poa_docs = [e for e in extractions if e.doc_type == DocType.PROOF_OF_ADDRESS]
        self.sanction_docs = [
            e for e in extractions
            if e.doc_type == DocType.SANCTION_QUESTIONNAIRE or getattr(e, "is_sanction_questionnaire", False)
        ]
        self.institutional_docs = [
            e for e in extractions
            if e.doc_type == DocType.INSTITUTIONAL_QUESTIONNAIRE or getattr(e, "institutional_type", None)
        ]
        self.cdd_docs = [
            e for e in extractions
            if e.doc_type == DocType.CDD_EDD_QUESTIONNAIRE
            or getattr(e, "singapore_nexus_rationale", None)
            or getattr(e, "continuation_rationale", None)
        ]
        self.translation_docs = [
            e for e in extractions
            if e.doc_type == DocType.TRANSLATION_CERTIFICATE or getattr(e, "has_certified_translation", False)
        ]

        # Canonical Profile
        self.profile = NormalizedCompanyProfile(
            entity_type=bundle_entity_type or EntityType.PVT_LTD.value
        )
        self._populate_profile()

    def _populate_profile(self):
        for ext in (
            self.bizfile_docs
            + self.incorp_docs
            + self.rod_docs
            + self.ubo_decl_docs
            + self.extractions
        ):
            if ext.legal_name and not self.profile.legal_name:
                self.profile.legal_name = ext.legal_name
            if ext.uen and not self.profile.uen:
                self.profile.uen = ext.uen
            if ext.former_names and not self.profile.former_names:
                self.profile.former_names = ext.former_names
            if ext.entity_type and not self.profile.entity_type:
                self.profile.entity_type = ext.entity_type
            if ext.incorporation_date and not self.profile.incorporation_date:
                self.profile.incorporation_date = ext.incorporation_date
            if ext.country_of_operations and not self.profile.country_of_operations:
                self.profile.country_of_operations = ext.country_of_operations
            if ext.place_of_business and not self.profile.place_of_business:
                self.profile.place_of_business = ext.place_of_business
            if ext.company_status and not self.profile.company_status:
                self.profile.company_status = ext.company_status
            if ext.bizfile_date and not self.profile.bizfile_date:
                self.profile.bizfile_date = ext.bizfile_date
            if ext.core_business_activities and not self.profile.core_business_activities:
                self.profile.core_business_activities = ext.core_business_activities
            if ext.geographic_coverage and not self.profile.geographic_coverage:
                self.profile.geographic_coverage = ext.geographic_coverage
            if ext.customer_website and not self.profile.customer_website:
                self.profile.customer_website = ext.customer_website
            if ext.directors and not self.profile.directors:
                self.profile.directors = ext.directors
            if ext.ubos and not self.profile.ubos:
                self.profile.ubos = ext.ubos
            if ext.authorizers:
                for a in ext.authorizers:
                    if a not in self.profile.authorizers:
                        self.profile.authorizers.append(a)
            if ext.administrators:
                for ad in ext.administrators:
                    if ad not in self.profile.administrators:
                        self.profile.administrators.append(ad)
            if ext.has_nominee_arrangement:
                self.profile.has_nominee_arrangement = True
            if ext.has_bearer_shares:
                self.profile.has_bearer_shares = True
            if ext.has_complex_structure:
                self.profile.has_complex_structure = True
                self.profile.complex_structure_rationale = ext.complex_structure_rationale
                self.profile.risk_rating = "HIGH"

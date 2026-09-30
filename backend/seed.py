"""Pre-populate the app with demo corporate wholesale client bundles if database is empty."""
from datetime import datetime, timezone
from pathlib import Path

from .config import BASE_DIR
from .db import get_conn, new_id, now_iso

DEMO_BUNDLES = [
    {
        "name": "Apex Global Trading Pte. Ltd.",
        "uen": "201912345K",
        "entity_type": "Private Limited Company",
    },
    {
        "name": "Pacific Horizons Shipping Ltd.",
        "uen": "201509876M",
        "entity_type": "Public Listed Company",
    },
    {
        "name": "Vertex Capital Partners (SG)",
        "uen": "T18LL0123A",
        "entity_type": "Partnership",
    },
]


def seed_if_empty() -> None:
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM customer_bundles").fetchone()["c"]
        if count > 0:
            return  # already seeded

        for bundle in DEMO_BUNDLES:
            conn.execute(
                "INSERT INTO customer_bundles (id, name, uen, entity_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    bundle["name"],
                    bundle["uen"],
                    bundle["entity_type"],
                    "PENDING",
                    now_iso(),
                    now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()

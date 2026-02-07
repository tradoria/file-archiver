"""Flask application factory."""

import csv
from pathlib import Path
from typing import Optional

from flask import Flask

from archiver.web.database import init_db, set_db_path


def load_csv_data(artifacts_dir: Path) -> list[dict]:
    """Load report_analyzed.csv into memory."""
    report_path = artifacts_dir / "report_analyzed.csv"
    if not report_path.exists():
        return []

    with open(report_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def create_app(config: Optional[dict] = None, config_path: Optional[Path] = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "file-archiver-secret-key"

    # Store config
    cfg = config or {}
    artifacts_dir = Path(cfg.get("artifacts_dir", "./artifacts")).resolve()

    app.config["ARTIFACTS_DIR"] = artifacts_dir
    app.config["CSV_DATA"] = load_csv_data(artifacts_dir)
    app.config["CONFIG_PATH"] = config_path or Path("config.yaml")
    app.config["ARCHIVER_ROOT"] = Path.cwd()

    # Initialize database
    db_path = artifacts_dir / "archiver.db"
    set_db_path(db_path)
    init_db()

    # Sync CSV data with database (initial load)
    from archiver.web.database import get_decision, upsert_decision

    for row in app.config["CSV_DATA"]:
        file_hash = row.get("hash", "")
        if file_hash and not get_decision(file_hash):
            upsert_decision(
                file_hash=file_hash,
                original_path=row.get("path", ""),
                suggested_destination=row.get("suggested_destination", "Sonstiges"),
                final_destination=row.get("suggested_destination", "Sonstiges"),
                status="REVIEW" if row.get("analysis_status") == "REVIEW" else "OK",
            )

    # Register routes
    from archiver.web.routes import register_routes
    register_routes(app)

    return app

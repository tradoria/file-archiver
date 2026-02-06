"""Generate report.csv from scan results."""

import csv
from pathlib import Path


FIELDNAMES = ["path", "type", "text_path", "hash", "status"]


def write_report(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

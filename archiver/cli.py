"""CLI entry point using Typer."""

import csv
import uuid
from pathlib import Path

import typer
import yaml

from archiver.analyzer import analyze_content
from archiver.extractor import extract_text, WhisperNotAvailableError
from archiver.metadata import file_meta, save_meta
from archiver.report import write_report
from archiver.scanner import scan
from archiver.sorter import compute_sorting

app = typer.Typer(help="Local File Archiver – scan & extract text from files.")


@app.callback()
def main() -> None:
    """Local File Archiver – scan files and extract text."""


def _load_config(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


@app.command("scan")
def scan_cmd(
    root: Path = typer.Option(None, "--root", "-r", help="Root directory to scan."),
    config: Path = typer.Option(
        Path("config.yaml"), "--config", "-c", help="Path to config.yaml."
    ),
    limit: int = typer.Option(0, "--limit", "-n", help="Max files to process (0 = all)."),
    force: bool = typer.Option(False, "--force", "-f", help="Force rescan, ignore cache."),
    incremental: bool = typer.Option(True, "--incremental", "-i", help="Only scan new/changed files (default)."),
) -> None:
    """Scan a directory, extract text, collect metadata, write report."""
    cfg = _load_config(config)

    if root is None:
        root = Path(cfg.get("root_dir", "."))
    root = root.resolve()

    if not root.is_dir():
        typer.echo(f"ERROR: {root} is not a directory.", err=True)
        raise typer.Exit(1)

    artifacts = Path(cfg.get("artifacts_dir", "./artifacts")).resolve()
    text_dir = artifacts / "text"
    meta_dir = artifacts / "meta"
    text_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Initialize scan cache DB
    from archiver.web.database import init_db, set_db_path, is_file_scanned, mark_file_scanned
    db_path = artifacts / "archiver.db"
    set_db_path(db_path)
    init_db()

    ignore = set(cfg.get("ignore_patterns", []))
    extensions = {e if e.startswith(".") else f".{e}" for e in cfg.get("supported_extensions", [])} or None

    # Whisper config for audio/video transcription
    whisper_config = {
        "whisper_enabled": cfg.get("whisper_enabled", True),
        "whisper_model": cfg.get("whisper_model", "base"),
        "whisper_language": cfg.get("whisper_language", "de"),
    }

    use_cache = incremental and not force
    if force:
        typer.echo("Force-Modus: Cache wird ignoriert")
    elif use_cache:
        typer.echo("Incremental-Modus: Nur neue/geaenderte Dateien")

    typer.echo(f"Scanning: {root}")
    files = scan(root, extensions=extensions, ignore=ignore or None)
    total = len(files)
    if limit > 0:
        files = files[:limit]
    typer.echo(f"Found {total} supported files (processing {len(files)}).\n")

    rows: list[dict] = []
    stats = {"processed": 0, "skipped": 0, "new": 0}

    for idx, filepath in enumerate(files, 1):
        suffix = filepath.suffix.lower()

        # Get hash BEFORE extraction (for incremental check)
        meta = file_meta(filepath)
        file_hash = meta["sha256"]
        file_size = meta.get("size_bytes", 0)

        # Check if already scanned (incremental mode)
        if use_cache and is_file_scanned(file_hash):
            stats["skipped"] += 1
            continue

        file_id = uuid.uuid4().hex[:12]
        text_path = text_dir / f"{file_id}.txt"
        meta_path = meta_dir / f"{file_id}.json"

        meta["id"] = file_id
        meta["original_name"] = filepath.name

        status = "OK"
        try:
            text = extract_text(filepath, whisper_config)
            text_path.write_text(text, encoding="utf-8")
            meta["text_file"] = str(text_path)
        except WhisperNotAvailableError as exc:
            status = "SKIP_NO_WHISPER"
            meta["error"] = str(exc)
        except Exception as exc:
            status = "ERROR"
            meta["error"] = str(exc)
            typer.echo(f"  ERROR extracting {filepath}: {exc}")

        meta["status"] = status
        save_meta(meta, meta_path)

        # Mark as scanned in cache
        mark_file_scanned(file_hash, str(filepath), file_size)

        rows.append(
            {
                "path": str(filepath),
                "type": suffix,
                "text_path": str(text_path) if status == "OK" else "",
                "hash": file_hash,
                "status": status,
            }
        )
        stats["processed"] += 1
        stats["new"] += 1

        rel_path = str(filepath.relative_to(root)).encode("ascii", "replace").decode("ascii")
        typer.echo(f"  [{idx}/{len(files)}] [{status}] {rel_path}")

    report_path = artifacts / "report.csv"
    write_report(rows, report_path)

    typer.echo(f"\n{'=' * 40}")
    typer.echo(f"Done!")
    typer.echo(f"  Neu verarbeitet: {stats['new']}")
    typer.echo(f"  Uebersprungen:   {stats['skipped']} (bereits gescannt)")
    typer.echo(f"  Gesamt geprueft: {len(files)}")
    typer.echo(f"\nReport:    {report_path}")
    typer.echo(f"Artifacts: {artifacts}")


@app.command("scan-batch")
def scan_batch_cmd(
    roots: list[str] = typer.Option(None, "--roots", "-r", help="List of root directories to scan."),
    use_config: bool = typer.Option(False, "--use-config", "-C", help="Read scan_roots from config.yaml."),
    config: Path = typer.Option(
        Path("config.yaml"), "--config", "-c", help="Path to config.yaml."
    ),
    limit: int = typer.Option(0, "--limit", "-n", help="Max total files to process (0 = all)."),
) -> None:
    """Batch scan multiple directories into a single report."""
    cfg = _load_config(config)

    # Determine roots
    scan_roots: list[Path] = []
    if use_config:
        config_roots = cfg.get("scan_roots", [])
        scan_roots = [Path(r).resolve() for r in config_roots if r and not r.strip().startswith("#")]
    if roots:
        scan_roots.extend([Path(r).resolve() for r in roots])

    if not scan_roots:
        typer.echo("ERROR: No roots specified. Use --roots or --use-config with scan_roots in config.yaml.", err=True)
        raise typer.Exit(1)

    # Validate roots
    valid_roots = []
    for root in scan_roots:
        if root.is_dir():
            valid_roots.append(root)
        else:
            typer.echo(f"WARNING: Skipping invalid directory: {root}")

    if not valid_roots:
        typer.echo("ERROR: No valid directories found.", err=True)
        raise typer.Exit(1)

    artifacts = Path(cfg.get("artifacts_dir", "./artifacts")).resolve()
    text_dir = artifacts / "text"
    meta_dir = artifacts / "meta"
    text_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    ignore = set(cfg.get("ignore_patterns", []))
    extensions = {e if e.startswith(".") else f".{e}" for e in cfg.get("supported_extensions", [])} or None

    whisper_config = {
        "whisper_enabled": cfg.get("whisper_enabled", True),
        "whisper_model": cfg.get("whisper_model", "base"),
        "whisper_language": cfg.get("whisper_language", "de"),
    }

    typer.echo(f"Batch Scan: {len(valid_roots)} directories")
    for r in valid_roots:
        typer.echo(f"  - {r}")
    typer.echo("")

    # Collect all files from all roots
    all_files: list[tuple[Path, Path]] = []  # (filepath, source_root)
    for root in valid_roots:
        typer.echo(f"Discovering files in: {root}")
        files = scan(root, extensions=extensions, ignore=ignore or None)
        typer.echo(f"  Found {len(files)} files")
        all_files.extend([(f, root) for f in files])

    total_found = len(all_files)
    typer.echo(f"\nTotal: {total_found} files across all directories")

    if limit > 0:
        all_files = all_files[:limit]
        typer.echo(f"Processing first {len(all_files)} files (limit: {limit})")

    typer.echo("")

    # Deduplicate by hash (process each unique file only once)
    seen_hashes: dict[str, dict] = {}  # hash -> row data
    rows: list[dict] = []
    processed = 0
    skipped_duplicates = 0

    for filepath, source_root in all_files:
        processed += 1
        file_id = uuid.uuid4().hex[:12]
        suffix = filepath.suffix.lower()
        text_path = text_dir / f"{file_id}.txt"
        meta_path = meta_dir / f"{file_id}.json"

        # Get metadata first to check hash
        meta = file_meta(filepath)
        file_hash = meta["sha256"]

        # Check for duplicate
        if file_hash in seen_hashes:
            skipped_duplicates += 1
            rel_path = str(filepath.relative_to(source_root)).encode("ascii", "replace").decode("ascii")
            typer.echo(f"  [{processed}/{len(all_files)}] [DUP] {rel_path}")
            continue

        meta["id"] = file_id
        meta["original_name"] = filepath.name

        status = "OK"
        try:
            text = extract_text(filepath, whisper_config)
            text_path.write_text(text, encoding="utf-8")
            meta["text_file"] = str(text_path)
        except WhisperNotAvailableError as exc:
            status = "SKIP_NO_WHISPER"
            meta["error"] = str(exc)
        except Exception as exc:
            status = "ERROR"
            meta["error"] = str(exc)

        meta["status"] = status
        save_meta(meta, meta_path)

        row = {
            "path": str(filepath),
            "type": suffix,
            "text_path": str(text_path) if status == "OK" else "",
            "hash": file_hash,
            "status": status,
            "source_root": str(source_root),
        }
        rows.append(row)
        seen_hashes[file_hash] = row

        rel_path = str(filepath.relative_to(source_root)).encode("ascii", "replace").decode("ascii")
        typer.echo(f"  [{processed}/{len(all_files)}] [{status}] {rel_path}")

    # Write report with source_root column
    report_path = artifacts / "report.csv"
    fieldnames = ["path", "type", "text_path", "hash", "status", "source_root"]
    with open(report_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    typer.echo(f"\n{'=' * 40}")
    typer.echo(f"Done!")
    typer.echo(f"  Processed: {len(rows)} unique files")
    typer.echo(f"  Skipped:   {skipped_duplicates} duplicates")
    typer.echo(f"  Total:     {processed} files checked")
    typer.echo(f"\nReport:    {report_path}")
    typer.echo(f"Artifacts: {artifacts}")


@app.command("analyze")
def analyze_cmd(
    config: Path = typer.Option(
        Path("config.yaml"), "--config", "-c", help="Path to config.yaml."
    ),
    limit: int = typer.Option(0, "--limit", "-n", help="Max files to analyze (0 = all)."),
    use_llm: bool = typer.Option(False, "--use-llm", "-L", help="Use LLM for sorting suggestions."),
) -> None:
    """Analyze scanned files: generate tags, doc_type, and sorting suggestions."""
    cfg = _load_config(config)
    artifacts = Path(cfg.get("artifacts_dir", "./artifacts")).resolve()
    text_dir = artifacts / "text"

    # LLM config
    llm_enabled = use_llm or cfg.get("llm_sorting", False)
    llm_config = {
        "llm_sorting_model": cfg.get("llm_sorting_model", "gemma3:4b"),
        "llm_base_url": cfg.get("llm_base_url", ""),
        "ionos_ai_token": cfg.get("ionos_ai_token", ""),
        "artifacts_dir": str(artifacts),
    }
    if llm_enabled:
        typer.echo(f"LLM-Sortierung aktiviert (Model: {llm_config['llm_sorting_model']})")

    report_path = artifacts / "report.csv"
    if not report_path.exists():
        typer.echo("ERROR: report.csv not found. Run 'scan' first.", err=True)
        raise typer.Exit(1)

    # Read existing report
    with open(report_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if limit > 0:
        rows = rows[:limit]

    typer.echo(f"Analyzing {len(rows)} files...\n")

    # Build duplicate groups by hash
    hash_groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        h = row.get("hash", "")
        if h:
            if h not in hash_groups:
                hash_groups[h] = []
            hash_groups[h].append(idx)

    # Assign duplicate group IDs
    duplicate_group_map: dict[int, str] = {}
    group_id = 1
    for h, indices in hash_groups.items():
        if len(indices) > 1:
            gid = f"DUP_{group_id:03d}"
            for idx in indices:
                duplicate_group_map[idx] = gid
            group_id += 1

    # Track filename occurrences for versioning
    filename_counts: dict[str, int] = {}

    analyzed_rows: list[dict] = []
    stats = {"OK": 0, "REVIEW": 0}
    destinations: dict[str, list[str]] = {}
    dup_stats = {"total_duplicates": 0, "duplicate_groups": group_id - 1}

    for idx, row in enumerate(rows):
        original_path = row["path"]
        text_path_str = row.get("text_path", "")
        text_path = Path(text_path_str) if text_path_str else None

        # Read text content
        text = ""
        if text_path and text_path.exists():
            try:
                text = text_path.read_text(encoding="utf-8")[:5000]
            except Exception:
                pass

        # Analyze content
        analysis = analyze_content(text_path, original_path) if text_path else {"tags": [], "doc_type": "Sonstiges"}

        # Compute sorting
        sorting = compute_sorting(
            original_path=original_path,
            text=text,
            tags=analysis["tags"],
            doc_type=analysis["doc_type"],
            use_llm=llm_enabled,
            llm_config=llm_config,
            file_hash=row.get("hash", ""),
        )

        # Filename versioning
        original_filename = Path(original_path).name
        base_name = original_filename
        if base_name in filename_counts:
            filename_counts[base_name] += 1
            # Add version number
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            versioned_name = f"{stem}_{filename_counts[base_name]:03d}{suffix}"
        else:
            filename_counts[base_name] = 1
            versioned_name = base_name

        # Duplicate group
        dup_group = duplicate_group_map.get(idx, "")
        if dup_group:
            dup_stats["total_duplicates"] += 1

        # Build analyzed row
        analyzed_row = {
            **row,
            "tags": ";".join(analysis["tags"]),
            "doc_type": analysis["doc_type"],
            "folder_prior": sorting["folder_prior"],
            "suggested_destination": sorting["suggested_destination"],
            "confidence": sorting["confidence"],
            "reason": sorting["reason"],
            "analysis_status": sorting["analysis_status"],
            "duplicate_group": dup_group,
            "versioned_name": versioned_name,
        }
        analyzed_rows.append(analyzed_row)

        # Stats
        stats[sorting["analysis_status"]] += 1
        dest = sorting["suggested_destination"]
        if dest not in destinations:
            destinations[dest] = []
        destinations[dest].append(versioned_name)

        # Progress
        filename_display = original_filename.encode("ascii", "replace").decode("ascii")
        dup_marker = f" [{dup_group}]" if dup_group else ""
        typer.echo(f"  [{sorting['analysis_status']}] {filename_display} -> {dest} ({sorting['confidence']}){dup_marker}")

    # Write analyzed report
    analyzed_path = artifacts / "report_analyzed.csv"
    fieldnames = [
        "path", "type", "text_path", "hash", "status", "source_root",
        "tags", "doc_type", "folder_prior", "suggested_destination",
        "confidence", "reason", "analysis_status",
        "duplicate_group", "versioned_name",
    ]
    with open(analyzed_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(analyzed_rows)

    # Write sorting plan
    plan_path = artifacts / "sorting_plan.md"
    _write_sorting_plan(plan_path, analyzed_rows, stats, destinations, dup_stats)

    typer.echo(f"\nDone. {len(analyzed_rows)} files analyzed.")
    typer.echo(f"  OK: {stats['OK']}, REVIEW: {stats['REVIEW']}")
    typer.echo(f"  Duplikate: {dup_stats['total_duplicates']} Dateien in {dup_stats['duplicate_groups']} Gruppen")
    typer.echo(f"\nOutputs:")
    typer.echo(f"  Report:  {analyzed_path}")
    typer.echo(f"  Plan:    {plan_path}")


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(5000, "--port", "-p", help="Port to run the server on."),
    config: Path = typer.Option(
        Path("config.yaml"), "--config", "-c", help="Path to config.yaml."
    ),
) -> None:
    """Start the web review interface."""
    from archiver.web.app import create_app

    cfg = _load_config(config)
    flask_app = create_app(cfg, config_path=config.resolve())
    typer.echo(f"Starting review interface at http://localhost:{port}")
    flask_app.run(host="127.0.0.1", port=port, debug=False)


@app.command("copy")
def copy_cmd(
    target: Path = typer.Option(..., "--target", "-t", help="Target directory for sorted files."),
    mode: str = typer.Option("copy", "--mode", "-m", help="'copy' or 'move' files."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without copying."),
    include_transcripts: bool = typer.Option(False, "--include-transcripts", "-T", help="Place transcripts next to originals."),
    source_csv: Path = typer.Option(None, "--source-csv", "-s", help="Source CSV (default: artifacts/report_final.csv)."),
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config.yaml."),
) -> None:
    """Copy or move files to target directory based on sorting decisions."""
    import shutil
    from datetime import datetime

    cfg = _load_config(config)
    artifacts = Path(cfg.get("artifacts_dir", "./artifacts")).resolve()

    # Determine source CSV
    if source_csv is None:
        source_csv = artifacts / "report_final.csv"
        if not source_csv.exists():
            source_csv = artifacts / "report_analyzed.csv"

    if not source_csv.exists():
        typer.echo(f"ERROR: CSV not found: {source_csv}", err=True)
        typer.echo("Run 'analyze' first, or use Web-UI to export report_final.csv.", err=True)
        raise typer.Exit(1)

    # Validate mode
    if mode not in ("copy", "move"):
        typer.echo(f"ERROR: Mode must be 'copy' or 'move', got '{mode}'", err=True)
        raise typer.Exit(1)

    # Read CSV
    with open(source_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        typer.echo("No files found in CSV.")
        raise typer.Exit(0)

    typer.echo(f"Source CSV: {source_csv}")
    typer.echo(f"Target:     {target}")
    typer.echo(f"Mode:       {mode}")
    typer.echo(f"Dry-run:    {dry_run}")
    typer.echo(f"Transcripts: {include_transcripts}")
    typer.echo(f"\nProcessing {len(rows)} files...\n")

    # Stats
    stats = {"success": 0, "skipped": 0, "error": 0}
    log_entries: list[str] = []
    log_entries.append(f"Copy Log - {datetime.now().isoformat()}")
    log_entries.append(f"Source: {source_csv}")
    log_entries.append(f"Target: {target}")
    log_entries.append(f"Mode: {mode}, Dry-run: {dry_run}, Transcripts: {include_transcripts}")
    log_entries.append("=" * 60)

    for idx, row in enumerate(rows, 1):
        original_path = Path(row.get("path", ""))
        text_path_str = row.get("text_path", "")
        text_path = Path(text_path_str) if text_path_str else None

        # Determine destination folder (final_destination > suggested_destination)
        destination = row.get("final_destination") or row.get("suggested_destination") or "Sonstiges"

        # Use versioned_name if available, else original filename
        filename = row.get("versioned_name") or original_path.name

        # Build target path
        target_folder = target / destination
        target_file = target_folder / filename

        # Check source exists
        if not original_path.exists():
            status = "SKIP (source missing)"
            stats["skipped"] += 1
            log_entries.append(f"[SKIP] {original_path} -> source not found")
            typer.echo(f"  [{idx}/{len(rows)}] SKIP (missing): {original_path.name}")
            continue

        # Check if already exists at target
        if target_file.exists():
            status = "SKIP (exists)"
            stats["skipped"] += 1
            log_entries.append(f"[SKIP] {original_path} -> {target_file} (already exists)")
            typer.echo(f"  [{idx}/{len(rows)}] SKIP (exists): {filename}")
            continue

        # Dry-run: just show
        if dry_run:
            action = "COPY" if mode == "copy" else "MOVE"
            typer.echo(f"  [{idx}/{len(rows)}] {action}: {original_path.name}")
            typer.echo(f"           -> {target_file}")
            if include_transcripts and text_path and text_path.exists():
                transcript_target = target_folder / (Path(filename).stem + ".txt")
                typer.echo(f"           +T {transcript_target.name}")
            stats["success"] += 1
            log_entries.append(f"[DRY-RUN] {original_path} -> {target_file}")
            continue

        # Actually copy/move
        try:
            # Create target folder
            target_folder.mkdir(parents=True, exist_ok=True)

            if mode == "copy":
                shutil.copy2(original_path, target_file)
                action = "COPIED"
            else:
                shutil.move(str(original_path), str(target_file))
                action = "MOVED"

            log_entries.append(f"[{action}] {original_path} -> {target_file}")

            # Copy transcript if requested
            if include_transcripts and text_path and text_path.exists():
                transcript_target = target_folder / (Path(filename).stem + ".txt")
                shutil.copy2(text_path, transcript_target)
                log_entries.append(f"[TRANSCRIPT] {text_path} -> {transcript_target}")

            stats["success"] += 1
            typer.echo(f"  [{idx}/{len(rows)}] {action}: {filename} -> {destination}")

        except Exception as e:
            stats["error"] += 1
            log_entries.append(f"[ERROR] {original_path} -> {e}")
            typer.echo(f"  [{idx}/{len(rows)}] ERROR: {filename} - {e}")

    # Summary
    typer.echo(f"\n{'=' * 40}")
    typer.echo(f"Done!")
    typer.echo(f"  Success: {stats['success']}")
    typer.echo(f"  Skipped: {stats['skipped']}")
    typer.echo(f"  Errors:  {stats['error']}")

    # Write log file
    if not dry_run:
        log_path = target / "copy_log.txt"
        log_entries.append("=" * 60)
        log_entries.append(f"Summary: {stats['success']} success, {stats['skipped']} skipped, {stats['error']} errors")
        target.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_entries), encoding="utf-8")
        typer.echo(f"\nLog: {log_path}")
    else:
        typer.echo(f"\n[DRY-RUN] No files were copied. Remove --dry-run to execute.")


def _write_sorting_plan(path: Path, rows: list[dict], stats: dict, destinations: dict, dup_stats: dict) -> None:
    """Write sorting_plan.md with statistics and suggestions."""
    lines = [
        "# Sorting Plan",
        "",
        "## Statistik",
        "",
        f"- **Analysiert:** {len(rows)} Dateien",
        f"- **OK (confidence >= 0.6):** {stats['OK']}",
        f"- **REVIEW (confidence < 0.6):** {stats['REVIEW']}",
        f"- **Duplikate:** {dup_stats['total_duplicates']} Dateien in {dup_stats['duplicate_groups']} Gruppen",
        "",
        "## Sortiervorschläge nach Zielordner",
        "",
    ]

    for dest, files in sorted(destinations.items()):
        lines.append(f"### {dest} ({len(files)} Dateien)")
        lines.append("")
        for fname in files[:10]:  # Max 10 per category in summary
            lines.append(f"- {fname}")
        if len(files) > 10:
            lines.append(f"- ... und {len(files) - 10} weitere")
        lines.append("")

    # Duplicate groups section
    dup_rows = [r for r in rows if r.get("duplicate_group")]
    if dup_rows:
        lines.append("## Duplikat-Gruppen (gleicher Hash)")
        lines.append("")
        # Group by duplicate_group
        dup_groups: dict[str, list[dict]] = {}
        for r in dup_rows:
            g = r["duplicate_group"]
            if g not in dup_groups:
                dup_groups[g] = []
            dup_groups[g].append(r)

        for gid, items in sorted(dup_groups.items()):
            lines.append(f"### {gid} ({len(items)} Dateien)")
            lines.append("")
            for item in items:
                fname = Path(item["path"]).name
                lines.append(f"- {fname}")
                lines.append(f"  - Pfad: `{item['path']}`")
            lines.append("")

    # Review list (exclude duplicates to reduce noise)
    seen_names = set()
    review_items = []
    for r in rows:
        if r["analysis_status"] == "REVIEW":
            fname = Path(r["path"]).name
            if fname not in seen_names:
                review_items.append(r)
                seen_names.add(fname)

    if review_items:
        lines.append("## Review-Liste (manuelle Prüfung empfohlen)")
        lines.append("")
        lines.append(f"*{len(review_items)} eindeutige Dateien (Duplikate zusammengefasst)*")
        lines.append("")
        for item in review_items:
            fname = Path(item["path"]).name
            dup_marker = f" **[{item['duplicate_group']}]**" if item.get("duplicate_group") else ""
            lines.append(f"- **{fname}**{dup_marker}")
            lines.append(f"  - Vorschlag: {item['suggested_destination']} (Confidence: {item['confidence']})")
            lines.append(f"  - Grund: {item['reason']}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

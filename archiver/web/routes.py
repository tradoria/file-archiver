"""Flask routes for the review interface."""

import csv
import shutil
import yaml
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for

from archiver.web.scan_manager import scan_manager

from archiver.web.database import (
    get_decision,
    get_all_decisions,
    update_decision_status,
    get_decision_stats,
    get_chat_history,
    add_chat_message,
    clear_chat_history,
)

# Destination options from sorter.py
DESTINATIONS = [
    "01 Grundwissen LLM",
    "02 Analyse Unternehmensstruktur und Prozesse",
    "03 KI Konzepte und Geschäftsfeldentwicklung",
    "04 Prompt Engineering",
    "05 KI Tools und Plattformen",
    "06 Datenschutz und Compliance",
    "07 Implementierung und Rollout",
    "08 KPIs und Erfolgsmessung",
    "Prompts-Sammlung",
    "Tools-und-Workflows",
    "Rechtliches",
    "Sonstiges",
    "Schrottplatz/Systemdateien",
    "Schrottplatz/Dozenten-Orga",
]


def register_routes(app: Flask) -> None:
    """Register all routes with the Flask app."""

    @app.route("/")
    def dashboard():
        """Dashboard with stats and REVIEW items table."""
        csv_data = app.config.get("CSV_DATA", [])
        decisions = {d["file_hash"]: d for d in get_all_decisions()}

        # Calculate stats
        total = len(csv_data)
        ok_count = sum(1 for r in csv_data if r.get("analysis_status") == "OK")
        review_count = sum(1 for r in csv_data if r.get("analysis_status") == "REVIEW")

        # Count pending reviews (not yet approved)
        pending_review = sum(
            1 for r in csv_data
            if r.get("analysis_status") == "REVIEW"
            and decisions.get(r.get("hash", ""), {}).get("status") != "APPROVED"
        )

        # Count duplicates
        dup_groups = set()
        for r in csv_data:
            if r.get("duplicate_group"):
                dup_groups.add(r["duplicate_group"])
        duplicate_count = len(dup_groups)

        # Filter for REVIEW items
        filter_status = request.args.get("status", "REVIEW")
        filter_dest = request.args.get("destination", "")
        search = request.args.get("search", "").lower()

        items = []
        for row in csv_data:
            file_hash = row.get("hash", "")
            decision = decisions.get(file_hash, {})

            # Determine effective status
            analysis_status = row.get("analysis_status", "OK")
            decision_status = decision.get("status", analysis_status)

            # Filter by status
            if filter_status == "REVIEW" and decision_status == "APPROVED":
                continue
            if filter_status == "APPROVED" and decision_status != "APPROVED":
                continue
            if filter_status == "all":
                pass
            elif filter_status not in ("REVIEW", "APPROVED", "all") and analysis_status != filter_status:
                continue

            # Filter by destination
            dest = decision.get("final_destination") or row.get("suggested_destination", "")
            if filter_dest and dest != filter_dest:
                continue

            # Search filter
            filename = Path(row.get("path", "")).name.lower()
            if search and search not in filename:
                continue

            items.append({
                "hash": file_hash,
                "filename": Path(row.get("path", "")).name,
                "path": row.get("path", ""),
                "type": row.get("type", ""),
                "suggested_destination": row.get("suggested_destination", ""),
                "final_destination": dest,
                "confidence": row.get("confidence", "0"),
                "tags": row.get("tags", ""),
                "duplicate_group": row.get("duplicate_group", ""),
                "analysis_status": analysis_status,
                "decision_status": decision_status,
            })

        return render_template(
            "dashboard.html",
            stats={
                "total": total,
                "ok": ok_count,
                "review": review_count,
                "pending_review": pending_review,
                "duplicates": duplicate_count,
            },
            items=items,
            destinations=DESTINATIONS,
            filter_status=filter_status,
            filter_dest=filter_dest,
            search=search,
        )

    @app.route("/review/<file_hash>")
    def detail(file_hash: str):
        """Detail view for a specific file."""
        csv_data = app.config.get("CSV_DATA", [])

        # Find row by hash
        row = next((r for r in csv_data if r.get("hash") == file_hash), None)
        if not row:
            flash("Datei nicht gefunden.", "error")
            return redirect(url_for("dashboard"))

        decision = get_decision(file_hash)
        artifacts_dir = app.config.get("ARTIFACTS_DIR", Path("artifacts"))

        # Read text content preview
        text_path = row.get("text_path", "")
        text_preview = ""
        if text_path and Path(text_path).exists():
            try:
                text_preview = Path(text_path).read_text(encoding="utf-8")[:1000]
            except Exception:
                text_preview = "[Fehler beim Lesen]"

        # Find next REVIEW item
        decisions_map = {d["file_hash"]: d for d in get_all_decisions()}
        next_hash = None
        found_current = False
        for r in csv_data:
            h = r.get("hash", "")
            if found_current:
                if r.get("analysis_status") == "REVIEW":
                    d = decisions_map.get(h, {})
                    if d.get("status") != "APPROVED":
                        next_hash = h
                        break
            if h == file_hash:
                found_current = True

        return render_template(
            "detail.html",
            file={
                "hash": file_hash,
                "filename": Path(row.get("path", "")).name,
                "path": row.get("path", ""),
                "type": row.get("type", ""),
                "text_path": text_path,
                "suggested_destination": row.get("suggested_destination", ""),
                "final_destination": decision.get("final_destination") if decision else row.get("suggested_destination", ""),
                "confidence": row.get("confidence", "0"),
                "reason": row.get("reason", ""),
                "tags": row.get("tags", "").split(";") if row.get("tags") else [],
                "doc_type": row.get("doc_type", ""),
                "duplicate_group": row.get("duplicate_group", ""),
                "analysis_status": row.get("analysis_status", ""),
                "decision_status": decision.get("status") if decision else row.get("analysis_status", ""),
                "action_type": decision.get("action_type") if decision else None,
            },
            text_preview=text_preview,
            destinations=DESTINATIONS,
            next_hash=next_hash,
        )

    @app.route("/api/decision/<file_hash>", methods=["POST"])
    def submit_decision(file_hash: str):
        """Submit a decision for a file."""
        data = request.get_json() or {}
        action = data.get("action", "")
        destination = data.get("destination", "")

        csv_data = app.config.get("CSV_DATA", [])
        row = next((r for r in csv_data if r.get("hash") == file_hash), None)

        if not row:
            return jsonify({"error": "Datei nicht gefunden"}), 404

        suggested = row.get("suggested_destination", "Sonstiges")

        if action == "accept":
            final_dest = suggested
            status = "APPROVED"
        elif action == "change":
            final_dest = destination or suggested
            status = "APPROVED"
        elif action == "scrapyard":
            final_dest = "Schrottplatz/Systemdateien"
            status = "APPROVED"
        elif action == "skip":
            final_dest = suggested
            status = "REVIEW"
        else:
            return jsonify({"error": "Unbekannte Aktion"}), 400

        success = update_decision_status(file_hash, status, action, final_dest)

        if not success:
            # Decision doesn't exist yet, create it
            from archiver.web.database import upsert_decision
            upsert_decision(
                file_hash=file_hash,
                original_path=row.get("path", ""),
                suggested_destination=suggested,
                final_destination=final_dest,
                status=status,
                action_type=action,
            )

        return jsonify({"success": True, "status": status, "final_destination": final_dest})

    @app.route("/api/summary/<file_hash>")
    def get_summary(file_hash: str):
        """Get or generate LLM summary for a file."""
        from archiver.web.ollama_service import generate_summary

        csv_data = app.config.get("CSV_DATA", [])
        row = next((r for r in csv_data if r.get("hash") == file_hash), None)

        if not row:
            return jsonify({"error": "Datei nicht gefunden"}), 404

        text_path = row.get("text_path", "")
        if not text_path or not Path(text_path).exists():
            return jsonify({"summary": "Kein Textinhalt verfügbar."})

        try:
            text_content = Path(text_path).read_text(encoding="utf-8")
        except Exception as e:
            return jsonify({"summary": f"Fehler beim Lesen: {e}"})

        summary = generate_summary(file_hash, text_content)
        return jsonify({"summary": summary})

    @app.route("/export/csv")
    def export_csv():
        """Export final report with decisions."""
        import io
        import csv as csv_module

        csv_data = app.config.get("CSV_DATA", [])
        decisions = {d["file_hash"]: d for d in get_all_decisions()}
        artifacts_dir = app.config.get("ARTIFACTS_DIR", Path("artifacts"))

        # Build output rows
        fieldnames = [
            "path", "type", "text_path", "hash", "status",
            "tags", "doc_type", "folder_prior", "suggested_destination",
            "confidence", "reason", "analysis_status",
            "duplicate_group", "versioned_name",
            "final_destination", "decision_status", "action_type",
        ]

        output = io.StringIO()
        writer = csv_module.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in csv_data:
            file_hash = row.get("hash", "")
            decision = decisions.get(file_hash, {})

            out_row = {**row}
            out_row["final_destination"] = decision.get("final_destination", row.get("suggested_destination", ""))
            out_row["decision_status"] = decision.get("status", row.get("analysis_status", ""))
            out_row["action_type"] = decision.get("action_type", "")
            writer.writerow(out_row)

        # Save to file
        export_path = artifacts_dir / "report_final.csv"
        export_path.write_text(output.getvalue(), encoding="utf-8")

        # Return as download
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name="report_final.csv",
        )

    @app.route("/export/transcript/<file_hash>", methods=["POST"])
    def export_transcript(file_hash: str):
        """Export transcript to Transkripte folder."""
        csv_data = app.config.get("CSV_DATA", [])
        artifacts_dir = app.config.get("ARTIFACTS_DIR", Path("artifacts"))

        row = next((r for r in csv_data if r.get("hash") == file_hash), None)
        if not row:
            return jsonify({"error": "Datei nicht gefunden"}), 404

        text_path = row.get("text_path", "")
        if not text_path or not Path(text_path).exists():
            return jsonify({"error": "Kein Transkript vorhanden"}), 404

        # Get original filename (without extension) + .txt
        original_name = Path(row.get("path", "")).stem + ".txt"

        # Create Transkripte folder
        transkripte_dir = artifacts_dir.parent / "Transkripte"
        transkripte_dir.mkdir(exist_ok=True)

        # Copy file
        dest_path = transkripte_dir / original_name
        shutil.copy2(text_path, dest_path)

        return jsonify({"success": True, "path": str(dest_path)})

    @app.route("/api/chat/<file_hash>", methods=["POST"])
    def chat(file_hash: str):
        """Chat with LLM about a file."""
        from archiver.web.ollama_service import chat_with_context

        data = request.get_json() or {}
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"error": "Keine Nachricht angegeben"}), 400

        csv_data = app.config.get("CSV_DATA", [])
        row = next((r for r in csv_data if r.get("hash") == file_hash), None)

        if not row:
            return jsonify({"error": "Datei nicht gefunden"}), 404

        # Read text content
        text_path = row.get("text_path", "")
        text_content = ""
        if text_path and Path(text_path).exists():
            try:
                text_content = Path(text_path).read_text(encoding="utf-8")
            except Exception:
                text_content = ""

        # Get decision for current destination
        decision = get_decision(file_hash)
        current_destination = (
            decision.get("final_destination") if decision
            else row.get("suggested_destination", "")
        )

        # Build file context
        file_context = {
            "filename": Path(row.get("path", "")).name,
            "text_content": text_content,
            "tags": row.get("tags", ""),
            "doc_type": row.get("doc_type", ""),
            "suggested_destination": row.get("suggested_destination", ""),
            "current_destination": current_destination,
            "confidence": row.get("confidence", ""),
            "reason": row.get("reason", ""),
        }

        # Get chat history
        history = get_chat_history(file_hash)

        # Save user message
        add_chat_message(file_hash, "user", user_message)

        # Get LLM response
        response = chat_with_context(user_message, file_context, history)

        # Save assistant response
        add_chat_message(file_hash, "assistant", response)

        return jsonify({
            "response": response,
            "history": get_chat_history(file_hash),
        })

    @app.route("/api/chat/<file_hash>/history")
    def get_chat(file_hash: str):
        """Get chat history for a file."""
        history = get_chat_history(file_hash)
        return jsonify({"history": history})

    @app.route("/api/chat/<file_hash>/clear", methods=["POST"])
    def clear_chat(file_hash: str):
        """Clear chat history for a file."""
        clear_chat_history(file_hash)
        return jsonify({"success": True})

    @app.route("/export")
    def export_page():
        """Export page with copy options."""
        csv_data = app.config.get("CSV_DATA", [])
        decisions = {d["file_hash"]: d for d in get_all_decisions()}

        # Calculate stats
        total = len(csv_data)
        ok_count = 0
        review_count = 0
        scrapyard_count = 0

        for row in csv_data:
            file_hash = row.get("hash", "")
            decision = decisions.get(file_hash, {})
            dest = decision.get("final_destination") or row.get("suggested_destination", "")

            if dest.startswith("Schrottplatz"):
                scrapyard_count += 1
            elif row.get("analysis_status") == "REVIEW" and decision.get("status") != "APPROVED":
                review_count += 1
            else:
                ok_count += 1

        return render_template(
            "export.html",
            stats={
                "total": total,
                "ok": ok_count,
                "review": review_count,
                "scrapyard": scrapyard_count,
            },
        )

    @app.route("/api/export/copy", methods=["POST"])
    def api_export_copy():
        """Copy files to target directory."""
        from datetime import datetime

        data = request.get_json() or {}
        target = data.get("target", "").strip()
        dry_run = data.get("dry_run", True)
        exclude_scrapyard = data.get("exclude_scrapyard", True)
        only_approved = data.get("only_approved", False)
        include_transcripts = data.get("include_transcripts", False)

        if not target:
            return jsonify({"error": "Zielverzeichnis fehlt"}), 400

        target_path = Path(target)

        csv_data = app.config.get("CSV_DATA", [])
        decisions = {d["file_hash"]: d for d in get_all_decisions()}

        stats = {"success": 0, "skipped": 0, "errors": 0}
        destinations: dict[str, int] = {}
        log_entries = [
            f"Export Log - {datetime.now().isoformat()}",
            f"Target: {target}",
            f"Dry-run: {dry_run}",
            "=" * 50,
        ]

        for row in csv_data:
            file_hash = row.get("hash", "")
            original_path = Path(row.get("path", ""))
            text_path_str = row.get("text_path", "")

            decision = decisions.get(file_hash, {})
            dest = decision.get("final_destination") or row.get("suggested_destination", "Sonstiges")
            status = decision.get("status", row.get("analysis_status", "OK"))

            # Filter: Schrottplatz
            if exclude_scrapyard and dest.startswith("Schrottplatz"):
                stats["skipped"] += 1
                continue

            # Filter: Only approved
            if only_approved and status not in ("APPROVED", "OK"):
                stats["skipped"] += 1
                continue

            # Check source exists
            if not original_path.exists():
                stats["skipped"] += 1
                log_entries.append(f"[SKIP] {original_path} - nicht gefunden")
                continue

            # Build target path
            filename = row.get("versioned_name") or original_path.name
            target_folder = target_path / dest
            target_file = target_folder / filename

            # Track destinations
            destinations[dest] = destinations.get(dest, 0) + 1

            if dry_run:
                stats["success"] += 1
                log_entries.append(f"[DRY-RUN] {original_path} -> {target_file}")
            else:
                try:
                    target_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original_path, target_file)
                    log_entries.append(f"[COPIED] {original_path} -> {target_file}")

                    # Copy transcript if requested
                    if include_transcripts and text_path_str and Path(text_path_str).exists():
                        transcript_target = target_folder / (Path(filename).stem + ".txt")
                        shutil.copy2(text_path_str, transcript_target)
                        log_entries.append(f"[TRANSCRIPT] -> {transcript_target}")

                    stats["success"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    log_entries.append(f"[ERROR] {original_path} - {e}")

        # Write log file
        log_path = None
        if not dry_run and stats["success"] > 0:
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                log_path = target_path / "copy_log.txt"
                log_entries.append("=" * 50)
                log_entries.append(f"Erfolg: {stats['success']}, Fehler: {stats['errors']}")
                log_path.write_text("\n".join(log_entries), encoding="utf-8")
            except Exception:
                pass

        return jsonify({
            "success": stats["success"],
            "skipped": stats["skipped"],
            "errors": stats["errors"],
            "destinations": destinations,
            "dry_run": dry_run,
            "log_path": str(log_path) if log_path else None,
        })

    # ========== SCAN ROUTES ==========

    @app.route("/scan")
    def scan_page():
        """Scan page with folder management and options."""
        config_path = app.config.get("CONFIG_PATH", Path("config.yaml"))
        scan_roots = []

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    scan_roots = config.get("scan_roots") or []
                    # Filter out commented entries (None values from YAML)
                    scan_roots = [r for r in scan_roots if r]
            except Exception:
                pass

        return render_template("scan.html", scan_roots=scan_roots)

    @app.route("/api/scan/folders", methods=["POST"])
    def manage_folders():
        """Add or remove scan folders from config."""
        data = request.get_json() or {}
        action = data.get("action")
        folder = data.get("folder", "").strip()

        config_path = app.config.get("CONFIG_PATH", Path("config.yaml"))

        # Load current config
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
            except Exception:
                pass

        scan_roots = config.get("scan_roots") or []
        # Filter out None values
        scan_roots = [r for r in scan_roots if r]

        if action == "add":
            if not folder:
                return jsonify({"error": "Ordner fehlt"}), 400
            # Validate folder exists
            if not Path(folder).exists():
                return jsonify({"error": f"Ordner existiert nicht: {folder}"}), 400
            if folder not in scan_roots:
                scan_roots.append(folder)

        elif action == "remove":
            if folder in scan_roots:
                scan_roots.remove(folder)

        else:
            return jsonify({"error": "Unbekannte Aktion"}), 400

        # Save config
        config["scan_roots"] = scan_roots
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            return jsonify({"error": f"Fehler beim Speichern: {e}"}), 500

        return jsonify({"success": True, "folders": scan_roots})

    @app.route("/api/scan/start", methods=["POST"])
    def start_scan():
        """Start a background scan job."""
        data = request.get_json() or {}
        folders = data.get("folders", [])
        options = {
            "incremental": data.get("incremental", True),
            "force": data.get("force", False),
            "use_llm": data.get("use_llm", False),
            "analyze": data.get("analyze", True),
            "limit": data.get("limit"),
        }

        if not folders:
            return jsonify({"error": "Keine Ordner angegeben"}), 400

        # Create and start job
        job = scan_manager.create_job(folders, options)
        archiver_path = app.config.get("ARCHIVER_ROOT", Path.cwd())
        job.start(archiver_path)

        return jsonify({"success": True, "job_id": job.job_id})

    @app.route("/api/scan/status/<job_id>")
    def scan_status(job_id: str):
        """Get status of a scan job."""
        job = scan_manager.get_job(job_id)
        if not job:
            return jsonify({"error": "Job nicht gefunden"}), 404
        return jsonify(job.to_dict())

    @app.route("/api/scan/stop", methods=["POST"])
    def stop_scan():
        """Stop a running scan job."""
        data = request.get_json() or {}
        job_id = data.get("job_id")

        if not job_id:
            return jsonify({"error": "Job-ID fehlt"}), 400

        success = scan_manager.stop_job(job_id)
        return jsonify({"success": success})

    @app.route("/settings")
    def settings_page():
        """Settings page: LLM-Sortierung an/aus, Modell/URL, API-Key."""
        config_path = app.config.get("CONFIG_PATH", Path("config.yaml"))
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
            except Exception:
                pass

        return render_template(
            "settings.html",
            llm_sorting=bool(config.get("llm_sorting", False)),
            llm_sorting_model=config.get("llm_sorting_model", "openai/llama-3.3-70b"),
            llm_base_url=config.get("llm_base_url", "https://openai.inference.de-txl.ionos.com/v1"),
            has_api_key=bool(config.get("ionos_ai_token")),
        )

    @app.route("/api/settings", methods=["POST"])
    def save_settings():
        """Save LLM settings. The API key is only overwritten if a new,
        non-empty value was submitted, so re-saving other fields never
        wipes an already-stored key - and the key itself is never sent
        back to the browser (see settings_page above)."""
        data = request.get_json() or {}
        config_path = app.config.get("CONFIG_PATH", Path("config.yaml"))

        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
            except Exception:
                pass

        config["llm_sorting"] = bool(data.get("llm_sorting"))

        model = (data.get("llm_sorting_model") or "").strip()
        if model:
            config["llm_sorting_model"] = model

        base_url = (data.get("llm_base_url") or "").strip()
        if base_url:
            config["llm_base_url"] = base_url

        api_key = (data.get("api_key") or "").strip()
        if api_key:
            config["ionos_ai_token"] = api_key
        elif data.get("clear_api_key"):
            config.pop("ionos_ai_token", None)

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            return jsonify({"error": f"Fehler beim Speichern: {e}"}), 500

        return jsonify({"success": True, "has_api_key": bool(config.get("ionos_ai_token"))})

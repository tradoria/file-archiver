"""Flask routes for the review interface."""

import csv
import shutil
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for

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

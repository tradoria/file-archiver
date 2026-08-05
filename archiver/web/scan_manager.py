"""Background scan job manager for the web UI."""

import subprocess
import sys
import threading
import uuid
import re
from pathlib import Path
from typing import Optional
from collections import deque


def _archiver_command() -> list[str]:
    """Build the base command to re-invoke the archiver CLI.

    Uses sys.executable so this works both from a normal Python
    environment and from a frozen PyInstaller build, where there is
    no guarantee a "python" interpreter is on PATH.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--archiver-cli"]
    return [sys.executable, "-m", "archiver"]


class ScanJob:
    """Represents a running or completed scan job."""

    def __init__(self, job_id: str, folders: list[str], options: dict):
        self.job_id = job_id
        self.folders = folders
        self.options = options

        self.status = "pending"  # pending, running, done, error
        self.phase = "Initialisiere..."
        self.current_folder = ""
        self.current_file = ""
        self.total = 0
        self.processed = 0
        self.skipped = 0
        self.errors = 0

        self.log_lines: deque[str] = deque(maxlen=500)
        self.log_read_index = 0
        self.error_message = ""

        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, archiver_path: Path):
        """Start the scan in a background thread."""
        self._thread = threading.Thread(target=self._run, args=(archiver_path,), daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the running scan."""
        if self._process:
            self._process.terminate()
            self.status = "error"
            self.error_message = "Abgebrochen"

    def _run(self, archiver_path: Path):
        """Run the scan process."""
        self.status = "running"

        try:
            for i, folder in enumerate(self.folders):
                if self.status == "error":
                    break

                self.current_folder = folder
                self.phase = f"Scanne Ordner {i + 1}/{len(self.folders)}"
                self._add_log(f"Starte Scan: {folder}")

                # Build scan command
                cmd = _archiver_command() + ["scan", "--root", folder]

                if self.options.get("incremental"):
                    cmd.append("--incremental")
                if self.options.get("force"):
                    cmd.append("--force")
                if self.options.get("limit"):
                    cmd.extend(["--limit", str(self.options["limit"])])

                self._add_log(f"Befehl: {' '.join(cmd)}")

                # Run scan
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(archiver_path),
                    bufsize=1,
                )

                # Parse output
                for line in self._process.stdout:
                    line = line.rstrip()
                    if not line:
                        continue

                    self._add_log(line)
                    self._parse_line(line)

                self._process.wait()

                if self._process.returncode != 0:
                    self._add_log(f"Scan beendet mit Code {self._process.returncode}")

            # Run analyze if requested
            if self.options.get("analyze") and self.status == "running":
                self.phase = "Analysiere..."
                self._add_log("Starte Analyse...")

                cmd = _archiver_command() + ["analyze"]
                if self.options.get("use_llm"):
                    cmd.append("--use-llm")

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(archiver_path),
                    bufsize=1,
                )

                for line in self._process.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    self._add_log(line)

                self._process.wait()
                self._add_log("Analyse abgeschlossen")

            self.status = "done"

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            self._add_log(f"Fehler: {e}")

    def _add_log(self, line: str):
        """Add a line to the log buffer."""
        self.log_lines.append(line)

    def _parse_line(self, line: str):
        """Parse a scan output line to extract progress."""
        # Match: Found X supported files (processing Y).
        match = re.search(r"Found (\d+) supported files", line)
        if match:
            self.total = int(match.group(1))
            return

        # Match: [1/385] [OK] filename
        match = re.match(r"\s*\[(\d+)/(\d+)\]\s*\[(\w+)\]\s*(.+)", line)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            status = match.group(3)
            filename = match.group(4)

            self.total = total
            self.current_file = filename

            if status == "OK":
                self.processed = current
            elif status == "SKIP":
                self.skipped += 1
            elif status == "ERROR":
                self.errors += 1
            return

        # Match: Uebersprungen: X (bereits gescannt)
        match = re.search(r"Uebersprungen:\s*(\d+)", line)
        if match:
            self.skipped = int(match.group(1))
            return

        # Match: Neu verarbeitet: X
        match = re.search(r"Neu verarbeitet:\s*(\d+)", line)
        if match:
            self.processed = int(match.group(1))
            return

    def get_new_logs(self) -> list[str]:
        """Get new log lines since last check."""
        logs = list(self.log_lines)
        new_logs = logs[self.log_read_index:]
        self.log_read_index = len(logs)
        return new_logs

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "current_folder": self.current_folder,
            "current_file": self.current_file,
            "total": self.total,
            "processed": self.processed,
            "skipped": self.skipped,
            "errors": self.errors,
            "error_message": self.error_message,
            "new_logs": self.get_new_logs(),
        }


class ScanManager:
    """Manages scan jobs."""

    def __init__(self):
        self.jobs: dict[str, ScanJob] = {}

    def create_job(self, folders: list[str], options: dict) -> ScanJob:
        """Create a new scan job."""
        job_id = str(uuid.uuid4())[:8]
        job = ScanJob(job_id, folders, options)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[ScanJob]:
        """Get a job by ID."""
        return self.jobs.get(job_id)

    def stop_job(self, job_id: str) -> bool:
        """Stop a running job."""
        job = self.jobs.get(job_id)
        if job:
            job.stop()
            return True
        return False


# Global instance
scan_manager = ScanManager()

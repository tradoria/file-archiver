"""Sorting logic: suggest destinations based on content analysis."""

import re
from pathlib import Path

# Schrottplatz-Kategorien (höchste Priorität - vor allem anderen prüfen)
SCRAPYARD_CATEGORIES = {
    "Schrottplatz/Systemdateien": {
        "filenames": [
            "license.txt", "licence.txt", "readme.txt", "readme.md",
            "requirements.txt", "passwort.txt", "password.txt",
            ".gitignore", "config.yaml", "config.json", "config.ini",
            "eula.txt", "copying.txt", "changelog.txt", "changelog.md",
            "launcherlicense.txt", "licenseagreement.txt",
        ],
        "patterns": ["license", "readme", "changelog", "eula"],
    },
    "Schrottplatz/Dozenten-Orga": {
        "filenames": [],
        "patterns": [
            "viona", "profiles", "vitero", "klassenliste", "klassenuebersicht",
            "teilnehmer", "anwesenheit", "fehlzeit", "stundenplan",
            "dozentenuebersicht", "dozentenfach", "raumliste", "moduldetails",
            "hilfe_p3", "kontaktliste", "zertifikatedruck",
        ],
    },
}

# Module 01-08 Definitionen
MODULE_PATTERNS = {
    "01": {
        "name": "01 Grundwissen LLM",
        "keywords": ["llm", "sprachmodell", "language model", "token", "temperatur", "sampling", "grundlagen"],
    },
    "02": {
        "name": "02 Analyse Unternehmensstruktur und Prozesse",
        "keywords": ["prozess", "analyse", "unternehmen", "struktur", "workflow", "optimierung", "lema", "retoure"],
    },
    "03": {
        "name": "03 KI Konzepte und Geschäftsfeldentwicklung",
        "keywords": ["konzept", "geschäftsfeld", "strategie", "business", "entwicklung", "innovation"],
    },
    "04": {
        "name": "04 Prompt Engineering",
        "keywords": ["prompt", "prompting", "system prompt", "chain of thought", "few-shot"],
    },
    "05": {
        "name": "05 KI Tools und Plattformen",
        "keywords": ["tool", "plattform", "chatgpt", "claude", "gemini", "copilot", "api"],
    },
    "06": {
        "name": "06 Datenschutz und Compliance",
        "keywords": ["datenschutz", "dsgvo", "compliance", "eu ai act", "regulierung", "rechtlich"],
    },
    "07": {
        "name": "07 Implementierung und Rollout",
        "keywords": ["implementierung", "rollout", "deployment", "einführung", "pilotprojekt"],
    },
    "08": {
        "name": "08 KPIs und Erfolgsmessung",
        "keywords": ["kpi", "metrik", "messung", "monitoring", "erfolg", "roi"],
    },
}

# Nicht-Modul Kategorien
OTHER_CATEGORIES = {
    "Prompts-Sammlung": ["prompt", "system prompt", "chatgpt prompt", "claude prompt"],
    "Tools-und-Workflows": ["n8n", "automation", "workflow", "integration", "zapier", "make"],
    "Rechtliches": ["dsgvo", "eu ai act", "datenschutz", "compliance", "verordnung", "recht"],
}


def extract_folder_prior(path: str) -> str | None:
    """Extract module folder if file is already in a module (01-08)."""
    path_lower = path.lower()

    # Pattern: "aufgaben/0X " oder ähnlich
    for module_num, module_info in MODULE_PATTERNS.items():
        # Suche nach Modul-Ordnernamen im Pfad
        patterns = [
            f"aufgaben\\{module_num}",
            f"aufgaben/{module_num}",
            f"\\{module_num} ",
            f"/{module_num} ",
        ]
        for pattern in patterns:
            if pattern in path_lower or pattern.replace("\\", "/") in path_lower:
                return module_info["name"]

    return None


def suggest_destination(text: str, filename: str, original_path: str, folder_prior: str | None) -> tuple[str, float, str]:
    """
    Suggest a destination folder.
    Returns: (suggested_destination, confidence, reason)
    """
    filename_lower = filename.lower()
    path_lower = original_path.lower()

    # HÖCHSTE PRIORITÄT: Schrottplatz-Kategorien (auch wenn in Modul!)
    for category, rules in SCRAPYARD_CATEGORIES.items():
        # Exakte Dateinamen
        if filename_lower in rules["filenames"]:
            return (category, 0.95, f"Systemdatei '{filename}' erkannt.")

        # Pattern-Matching
        for pattern in rules["patterns"]:
            if pattern in filename_lower:
                return (category, 0.9, f"Dateiname enthält '{pattern}' - {category}.")

    # Wenn bereits in einem Modul → beibehalten
    if folder_prior:
        return (folder_prior, 0.9, f"Datei bereits im Modul '{folder_prior}' organisiert.")

    combined = f"{filename} {text}".lower()

    # Pfad-basierte Erkennung für Nicht-Modul-Kategorien (hohe Priorität)
    PATH_CATEGORY_HINTS = {
        "Tools-und-Workflows": ["n8n", "automation", "workflow", "zapier", "make.com"],
        "Rechtliches": ["dsgvo", "compliance", "rechtlich", "legal"],
        "Prompts-Sammlung": ["prompts", "prompt-sammlung"],
    }

    for category, path_hints in PATH_CATEGORY_HINTS.items():
        for hint in path_hints:
            if hint in path_lower:
                return (category, 0.85, f"Pfad enthält '{hint}' - eindeutige Zuordnung zu '{category}'.")

    # Versuche Modul-Zuordnung basierend auf Inhalt
    best_module = None
    best_score = 0

    for module_num, module_info in MODULE_PATTERNS.items():
        score = sum(1 for kw in module_info["keywords"] if kw in combined)
        if score > best_score:
            best_score = score
            best_module = module_info["name"]

    # Prüfe auch Nicht-Modul-Kategorien
    best_other = None
    best_other_score = 0

    for category, keywords in OTHER_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_other_score:
            best_other_score = score
            best_other = category

    # Entscheidung: Nicht-Modul hat Vorrang bei gleichem Score
    if best_other_score >= 2:
        confidence = min(0.5 + best_other_score * 0.15, 0.8)
        return (best_other, confidence, f"Passt zur Kategorie '{best_other}' ({best_other_score} Keywords).")

    if best_score >= 2:
        confidence = min(0.5 + best_score * 0.1, 0.85)
        return (best_module, confidence, f"Inhalt passt zu Modul-Themen ({best_score} Keywords).")

    if best_other_score >= 1:
        confidence = min(0.4 + best_other_score * 0.15, 0.65)
        return (best_other, confidence, f"Passt zur Kategorie '{best_other}' ({best_other_score} Keywords).")

    # Fallback: Sonstiges
    return ("Sonstiges", 0.3, "Keine eindeutige Zuordnung möglich.")


def compute_sorting(
    original_path: str,
    text: str,
    tags: list[str],
    doc_type: str,
) -> dict:
    """Compute full sorting suggestion."""
    filename = Path(original_path).name
    folder_prior = extract_folder_prior(original_path)

    suggested_dest, confidence, reason = suggest_destination(text, filename, original_path, folder_prior)

    # Review-Status
    status = "REVIEW" if confidence < 0.6 else "OK"

    return {
        "folder_prior": folder_prior or "",
        "suggested_destination": suggested_dest,
        "confidence": round(confidence, 2),
        "reason": reason,
        "analysis_status": status,
    }

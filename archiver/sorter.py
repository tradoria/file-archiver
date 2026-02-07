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
    use_llm: bool = False,
    llm_config: dict | None = None,
    file_hash: str | None = None,
) -> dict:
    """Compute full sorting suggestion."""
    filename = Path(original_path).name
    folder_prior = extract_folder_prior(original_path)

    # Try LLM-based sorting if enabled
    if use_llm and text and file_hash:
        llm_result = llm_suggest_destination(
            text=text,
            filename=filename,
            file_hash=file_hash,
            llm_config=llm_config or {},
        )
        if llm_result:
            return {
                "folder_prior": folder_prior or "",
                "suggested_destination": llm_result["destination"],
                "confidence": llm_result["confidence"],
                "reason": f"[LLM] {llm_result['reason']}",
                "analysis_status": "OK" if llm_result["confidence"] >= 0.6 else "REVIEW",
            }

    # Fallback to keyword heuristics
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


# All available categories for LLM with descriptions
CATEGORY_DESCRIPTIONS = {
    "01 Grundwissen LLM": "Funktionsweise von Sprachmodellen, Transformer-Architektur, Token, Training, Halluzinationen, Grundlagen KI",
    "02 Analyse Unternehmensstruktur und Prozesse": "Ist-Analyse, Prozessaufnahme, Stakeholder-Analyse, Potenzialanalyse fuer KI, Unternehmensanalyse",
    "03 KI Konzepte und Geschaeftsfeldentwicklung": "Use-Cases entwickeln, Business Cases, ROI-Berechnung, Geschaeftsmodelle mit KI, KI-Strategie",
    "04 Prompt Engineering": "Prompts schreiben, Techniken (Chain-of-Thought, Few-Shot, Zero-Shot), Prompt-Optimierung, Prompt-Design",
    "05 KI Tools und Plattformen": "ChatGPT, Claude, Copilot, Midjourney, DALL-E, Tool-Vergleiche, API-Nutzung, Plattform-Tutorials",
    "06 Datenschutz und Compliance": "DSGVO, EU-AI-Act, Risikoklassen, Datenschutz-Folgenabschaetzung, KI-Regulierung - KEINE Rechnungen!",
    "07 Implementierung und Rollout": "Change Management, Schulungen, Pilotprojekte, Einfuehrungsstrategien, Mitarbeiter-Training",
    "08 KPIs und Erfolgsmessung": "Metriken, Monitoring, Evaluation, Qualitaetssicherung, Performance-Messung",
    "Prompts-Sammlung": "Fertige Prompt-Vorlagen, Prompt-Bibliotheken, Copy-Paste Prompts",
    "Tools-und-Workflows": "n8n, Automatisierung, Agenten, technische Workflows, Make, Zapier, Integrationen",
    "Rechtliches": "Gesetze, Verordnungen, juristische Texte zu KI, Rechtsgrundlagen - KEINE Rechnungen/Bestellungen!",
    "Sonstiges": "Alles ohne klaren KI-Bezug, unklare Zuordnung",
    "Schrottplatz/Systemdateien": "README, LICENSE, Config-Dateien, technische Metadaten, Changelog",
    "Schrottplatz/Dozenten-Orga": "VIONA, ProFiles, Vitero, interne IBB-Dokumente, Klassenlisten, Teilnehmerlisten",
    "Schrottplatz/Privat": "Rechnungen, Bestellungen, Lieferscheine, persoenliche Dokumente, Kontoauszuege, Quittungen",
}

ALL_CATEGORIES = list(CATEGORY_DESCRIPTIONS.keys())


def llm_suggest_destination(
    text: str,
    filename: str,
    file_hash: str,
    llm_config: dict,
) -> dict | None:
    """
    Use LLM to suggest destination folder.
    Returns: {"destination": str, "confidence": float, "reason": str} or None on failure.
    """
    import requests

    # Check cache first
    try:
        from archiver.web.database import get_cached_llm_sorting, cache_llm_sorting, init_db, set_db_path
        from pathlib import Path as P

        # Ensure DB is initialized
        artifacts_dir = P(llm_config.get("artifacts_dir", "./artifacts")).resolve()
        db_path = artifacts_dir / "archiver.db"
        set_db_path(db_path)
        init_db()

        cached = get_cached_llm_sorting(file_hash)
        if cached:
            return {
                "destination": cached["suggested_destination"],
                "confidence": cached["confidence"],
                "reason": cached["reason"],
            }
    except Exception:
        pass  # Continue without cache

    model = llm_config.get("llm_sorting_model", "gemma3:4b")
    ollama_url = "http://localhost:11434/api/generate"

    # Build prompt with detailed category descriptions
    categories_with_desc = "\n".join(
        f"- {cat}: {desc}" for cat, desc in CATEGORY_DESCRIPTIONS.items()
    )
    text_excerpt = text[:1500]

    prompt = f"""Du bist ein praeziser Datei-Klassifizierer fuer ein KI-Schulungsarchiv.

WICHTIGE REGELN:
1. Ordne NUR zu, wenn der Inhalt THEMATISCH zur Kategorie passt
2. Rechnungen, Bestellungen, Lieferscheine gehoeren zu "Schrottplatz/Privat" - NIEMALS zu "Rechtliches"!
3. "Rechtliches" ist NUR fuer Gesetze, Verordnungen, juristische KI-Texte
4. "06 Datenschutz und Compliance" ist fuer DSGVO/EU-AI-Act Lernmaterial - KEINE Geschaeftsdokumente
5. Bei Unsicherheit waehle "Sonstiges" mit niedriger Confidence

DATEINAME: {filename}

INHALT (Auszug):
{text_excerpt}

KATEGORIEN MIT BESCHREIBUNG:
{categories_with_desc}

Antworte EXAKT in diesem Format (keine andere Ausgabe):
KATEGORIE: <exakter Kategoriename aus der Liste>
CONFIDENCE: <0.0-1.0>
GRUND: <kurze Begruendung auf Deutsch>"""

    try:
        response = requests.post(
            ollama_url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json().get("response", "")

        # Parse response
        destination = "Sonstiges"
        confidence = 0.5
        reason = "LLM-Analyse"

        for line in result.strip().split("\n"):
            line = line.strip()
            if line.startswith("KATEGORIE:"):
                dest = line.replace("KATEGORIE:", "").strip()
                # Validate against known categories
                for cat in ALL_CATEGORIES:
                    if cat.lower() == dest.lower() or cat in dest:
                        destination = cat
                        break
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf = float(line.replace("CONFIDENCE:", "").strip())
                    confidence = max(0.0, min(1.0, conf))
                except ValueError:
                    pass
            elif line.startswith("GRUND:"):
                reason = line.replace("GRUND:", "").strip()

        # Cache result
        try:
            cache_llm_sorting(file_hash, destination, confidence, reason, model)
        except Exception:
            pass

        return {
            "destination": destination,
            "confidence": round(confidence, 2),
            "reason": reason,
        }

    except requests.exceptions.ConnectionError:
        return None  # Fallback to heuristics
    except Exception:
        return None  # Fallback to heuristics

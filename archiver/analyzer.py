"""Content analysis: generate tags and classify document type."""

import re
from pathlib import Path

# Keywords für doc_type Klassifikation
DOC_TYPE_KEYWORDS = {
    "Prompt": ["prompt", "system prompt", "user prompt", "assistant", "chatgpt", "claude", "gpt-4"],
    "Anleitung": ["anleitung", "bedienanleitung", "how to", "schritt für schritt", "tutorial", "guide"],
    "Tutorial": ["tutorial", "einführung", "grundlagen", "basics", "lernen", "kurs"],
    "Übung": ["übung", "aufgabe", "worksheet", "exercise", "lösung", "auflösung"],
    "Fallstudie": ["fallstudie", "case study", "beispiel", "praxisbeispiel", "szenario"],
    "Vorlage": ["vorlage", "template", "muster", "schema", "blueprint"],
    "Notiz": ["notiz", "note", "memo", "zusammenfassung", "summary"],
    "Artikel": ["artikel", "paper", "studie", "research", "analyse", "bericht"],
}

# Keywords für Tag-Generierung (Themenbereiche)
TAG_KEYWORDS = {
    "LLM": ["llm", "large language model", "sprachmodell", "language model"],
    "ChatGPT": ["chatgpt", "gpt-4", "gpt-3", "openai"],
    "Claude": ["claude", "anthropic"],
    "Prompt-Engineering": ["prompt", "prompting", "prompt engineering", "system prompt"],
    "KI-Strategie": ["strategie", "roadmap", "planung", "konzept", "geschäftsfeld"],
    "Prozessanalyse": ["prozess", "workflow", "ablauf", "optimierung", "analyse"],
    "Datenschutz": ["datenschutz", "dsgvo", "gdpr", "privacy", "personenbezogen"],
    "EU-AI-Act": ["eu ai act", "ai act", "ki-verordnung", "regulierung", "compliance"],
    "Automatisierung": ["automatisierung", "automation", "n8n", "workflow", "integration"],
    "API": ["api", "schnittstelle", "endpoint", "rest", "webhook"],
    "Training": ["training", "fine-tuning", "finetuning", "modell trainieren"],
    "RAG": ["rag", "retrieval", "embedding", "vektor", "knowledge base"],
    "Agenten": ["agent", "agenten", "multi-agent", "autonomous"],
    "Ethik": ["ethik", "bias", "fairness", "verantwortung", "responsible ai"],
    "Use-Case": ["use case", "anwendungsfall", "einsatz", "implementierung"],
    "KPIs": ["kpi", "metrik", "monitoring", "messung", "erfolgsmessung"],
    "Retouren": ["retoure", "rückgabe", "return", "rücksendung"],
    "Logistik": ["logistik", "lager", "versand", "lieferkette", "supply chain"],
    "LEMA": ["lema", "lema logistik"],
    "Bildgenerierung": ["bild", "image", "dall-e", "midjourney", "stable diffusion"],
}


def extract_tags(text: str, filename: str, max_tags: int = 10) -> list[str]:
    """Extract up to max_tags tags based on keyword matching."""
    combined = f"{filename} {text}".lower()
    found_tags = []

    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                found_tags.append(tag)
                break

    return found_tags[:max_tags]


def classify_doc_type(text: str, filename: str) -> str:
    """Classify document type based on keywords."""
    combined = f"{filename} {text}".lower()

    # Priorität: spezifischere Typen zuerst
    priority_order = ["Prompt", "Übung", "Fallstudie", "Vorlage", "Anleitung", "Tutorial", "Notiz", "Artikel"]

    for doc_type in priority_order:
        keywords = DOC_TYPE_KEYWORDS[doc_type]
        for kw in keywords:
            if kw in combined:
                return doc_type

    return "Sonstiges"


def analyze_content(text_path: Path, original_path: str) -> dict:
    """Analyze content and return tags + doc_type."""
    filename = Path(original_path).name

    text = ""
    if text_path.exists():
        try:
            text = text_path.read_text(encoding="utf-8")[:5000]  # First 5000 chars
        except Exception:
            pass

    tags = extract_tags(text, filename)
    doc_type = classify_doc_type(text, filename)

    return {
        "tags": tags,
        "doc_type": doc_type,
    }

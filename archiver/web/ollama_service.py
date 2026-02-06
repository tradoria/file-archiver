"""Ollama API integration with caching."""

import requests

from archiver.web.database import get_cached_summary, cache_summary

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"
PROMPT_TEMPLATE = "Fasse diesen Text in 2-3 deutschen Satzen zusammen:\n\n{text}"


def generate_summary(file_hash: str, text_content: str) -> str:
    """
    Generate LLM summary with caching.

    1. Check cache (summaries table)
    2. If cached, return immediately
    3. If not cached, call Ollama API
    4. Cache and return result
    """
    # Check cache first
    cached = get_cached_summary(file_hash)
    if cached:
        return cached

    # Truncate text to first 2000 characters
    truncated_text = text_content[:2000]
    if len(text_content) > 2000:
        truncated_text += "\n\n[... Text gekurzt ...]"

    prompt = PROMPT_TEMPLATE.format(text=truncated_text)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        summary = result.get("response", "Zusammenfassung konnte nicht erstellt werden.")
    except requests.exceptions.ConnectionError:
        summary = "Fehler: Ollama ist nicht erreichbar. Stellen Sie sicher, dass Ollama lauft (ollama serve)."
    except requests.exceptions.Timeout:
        summary = "Fehler: Zeituberschreitung bei der Anfrage. Der Text ist moglicherweise zu lang."
    except requests.exceptions.RequestException as e:
        summary = f"Fehler bei der Zusammenfassung: {e}"
    except Exception as e:
        summary = f"Unerwarteter Fehler: {e}"

    # Cache result (even errors, to avoid repeated failures)
    cache_summary(file_hash, summary, MODEL)

    return summary


def check_ollama_status() -> tuple[bool, str]:
    """Check if Ollama is running and model is available."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]

        if MODEL in model_names or f"{MODEL}:latest" in model_names:
            return True, f"Ollama lauft, Model '{MODEL}' verfugbar."

        return False, f"Ollama lauft, aber Model '{MODEL}' nicht gefunden. Verfugbar: {', '.join(model_names)}"
    except requests.exceptions.ConnectionError:
        return False, "Ollama ist nicht erreichbar. Starten Sie Ollama mit 'ollama serve'."
    except Exception as e:
        return False, f"Fehler beim Prufen von Ollama: {e}"


def chat_with_context(
    user_message: str,
    file_context: dict,
    chat_history: list[dict],
) -> str:
    """
    Chat with LLM about a specific file.

    Args:
        user_message: The user's question
        file_context: Dict with filename, text_content, tags, doc_type, suggested_destination, reason
        chat_history: List of previous messages [{role, content}, ...]
    """
    # Build system context
    text_excerpt = file_context.get("text_content", "")[:1500]
    if len(file_context.get("text_content", "")) > 1500:
        text_excerpt += "\n[... Text gekurzt ...]"

    system_context = f"""Du bist ein hilfreicher Assistent fur ein Datei-Archivierungssystem.
Du hilfst dem Benutzer, Dateien richtig einzusortieren und beantwortest Fragen zum Inhalt.

AKTUELLE DATEI:
- Dateiname: {file_context.get('filename', 'Unbekannt')}
- Erkannte Tags: {file_context.get('tags', 'Keine')}
- Dokumenttyp: {file_context.get('doc_type', 'Unbekannt')}
- Vorgeschlagener Zielordner: {file_context.get('suggested_destination', 'Unbekannt')}
- Begrundung: {file_context.get('reason', 'Keine')}
- Confidence: {file_context.get('confidence', 'Unbekannt')}

DATEIINHALT (Auszug):
{text_excerpt}

VERFUGBARE ZIELORDNER:
- 01 Grundwissen LLM
- 02 Analyse Unternehmensstruktur und Prozesse
- 03 KI Konzepte und Geschaeftsfeldentwicklung
- 04 Prompt Engineering
- 05 KI Tools und Plattformen
- 06 Datenschutz und Compliance
- 07 Implementierung und Rollout
- 08 KPIs und Erfolgsmessung
- Prompts-Sammlung
- Tools-und-Workflows
- Rechtliches
- Sonstiges
- Schrottplatz/Systemdateien

Antworte auf Deutsch, kurz und praezise."""

    # Build conversation history for prompt
    conversation = []
    for msg in chat_history[-6:]:  # Last 6 messages for context
        role_label = "Benutzer" if msg["role"] == "user" else "Assistent"
        conversation.append(f"{role_label}: {msg['content']}")

    conversation.append(f"Benutzer: {user_message}")

    full_prompt = f"{system_context}\n\nGESPRAECHSVERLAUF:\n" + "\n".join(conversation) + "\n\nAssistent:"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": full_prompt,
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        return result.get("response", "Keine Antwort erhalten.").strip()
    except requests.exceptions.ConnectionError:
        return "Fehler: Ollama ist nicht erreichbar. Stellen Sie sicher, dass Ollama lauft."
    except requests.exceptions.Timeout:
        return "Fehler: Zeituberschreitung bei der Anfrage."
    except Exception as e:
        return f"Fehler: {e}"

"""
Zentrale Konfiguration des Reisebot-Prototyps.

Liest Umgebungsvariablen aus einer lokalen `.env`-Datei (siehe `.env.example`
für die erwarteten Schlüssel). Es werden bewusst KEINE Schlüssel im Code
hinterlegt (Vorgabe aus CLAUDE.md: "Key in .env, nie im Code/Repo").
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# python-dotenv lädt die .env-Datei in die Prozessumgebung, falls vorhanden.
# Der Import ist optional, damit das Projekt auch ohne installiertes Paket
# startet (z.B. wenn Variablen bereits über das System gesetzt sind).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _bool_env(name: str, default: bool) -> bool:
    """Liest eine Umgebungsvariable als Wahrheitswert (z.B. 'true'/'false')."""
    wert = os.getenv(name)
    if wert is None:
        return default
    return wert.strip().lower() in {"1", "true", "yes", "ja"}


@dataclass(frozen=True)
class Einstellungen:
    """Bündelt alle zur Laufzeit benötigten Konfigurationswerte."""

    # Solange kein Google-Maps-Key eingetragen ist, läuft der API-Layer
    # ausschließlich mit Beispieldaten (siehe src/api/mock_data.py).
    mock_modus: bool = _bool_env("MOCK_MODE", True)

    google_maps_api_key: str | None = os.getenv("GOOGLE_MAPS_API_KEY") or None
    mailjet_api_key: str | None = os.getenv("MAILJET_API_KEY") or None
    mailjet_secret_key: str | None = os.getenv("MAILJET_SECRET_KEY") or None
    # Bei Mailjet verifizierte Absenderadresse (Pflicht für den Send-API-
    # Aufruf, siehe src/ausgabe/reiseplan.py::sende_mail).
    mailjet_absender: str | None = os.getenv("MAILJET_ABSENDER") or None

    # Tagesbudget INKL. Fahrzeit (siehe Projektkonversation: "maximal acht Stunden mit Fahrzeit" –
    # vorher 600 Minuten/10h, was an einem Tag spürbar zu viel eingeplant hat). Reine AKTIVITÄTSZEIT
    # (ohne Fahrzeit) wird zusätzlich separat über `max_aktivitaetszeit_minuten` begrenzt (enger als
    # dieses Gesamtbudget, siehe toptw.py `TOPTWInstanz`).
    standard_tagesbudget_minuten: int = int(os.getenv("STANDARD_TAGESBUDGET_MINUTEN", "480"))
    # Reine Besuchszeit (Summe `required_time` der eingeplanten POIs, OHNE Fahrzeit dazwischen) – die
    # bisherige Optimierung füllte allein mit dem Gesamtbudget einen ganzen Tag mit Aktivitäten,
    # ohne Rücksicht darauf, ob das für einen Menschen überhaupt zumutbar ist (siehe Projekt-
    # konversation: "da wurden zehn Stunden Aktivitäten geplant, das macht ja keiner"). Harte
    # Nebenbedingung in `toptw.py::simuliere_route`, zusätzlich zum Gesamtbudget inkl. Fahrzeit.
    max_aktivitaetszeit_minuten: int = int(os.getenv("MAX_AKTIVITAETSZEIT_MINUTEN", "360"))

    # Modell für die Claude-Agent-SDK-Dialogsession (chat.py). Explizit
    # gesetzt statt das Modell der umgebenden Claude-Code-Session zu erben:
    # "Fable 5" (Session-Default) lief bei einem Testlauf ins Nutzungs-
    # kontingent (siehe Projektkonversation) – Opus 5 als bewusste Wahl.
    llm_modell: str = os.getenv("LLM_MODELL", "claude-opus-5")

    # Sprachmodus (chat.py): Mikrofon statt Tastatur, Stimme statt Konsolentext.
    # Benötigt die Zusatzpakete aus requirements-audio.txt (siehe dort).
    audio_modus: bool = _bool_env("AUDIO_MODUS", False)
    # "google_cloud" (bessere Qualität, braucht API-Key, siehe google_speech.py)
    # oder "lokal" (Whisper + pyttsx3, kein Key nötig, siehe spracheingabe.py/
    # sprachausgabe.py). Default auf google_cloud, siehe Projektkonversation.
    audio_anbieter: str = os.getenv("AUDIO_ANBIETER", "google_cloud")
    whisper_modellgroesse: str = os.getenv("WHISPER_MODELL_GROESSE", "base")
    # Für den Anbieter "google_cloud": eigener Key, sonst Fallback auf den
    # Google-Maps-Key (meist dasselbe Cloud-Projekt) – dafür müssen dort
    # zusätzlich "Cloud Text-to-Speech API" und "Cloud Speech-to-Text API"
    # aktiviert sein (siehe google_speech.py).
    google_cloud_speech_api_key: str | None = (
        os.getenv("GOOGLE_CLOUD_SPEECH_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or None
    )


EINSTELLUNGEN = Einstellungen()

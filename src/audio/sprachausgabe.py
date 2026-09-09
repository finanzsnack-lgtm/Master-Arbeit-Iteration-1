"""
Sprachausgabe: Text -> Stimme, lokal über `pyttsx3` (nutzt unter Windows die
eingebauten SAPI5-Stimmen, kein API-Key/Internet nötig). Ersetzt in chat.py
die `print(f"Bot: ...")`-Ausgabe, wenn `AUDIO_MODUS=true` und
`AUDIO_ANBIETER=lokal` (siehe config.py). Alternative: google_speech.py
(Google Cloud Text-to-Speech, natürlicher klingende Stimmen, braucht API-Key).

BEKANNTER STOLPERSTEIN (siehe Projektkonversation: nur die erste Frage
wurde vorgelesen, danach blieb es stumm): der SAPI5-Treiber von pyttsx3
unter Windows verträgt es oft nicht, dieselbe Engine-Instanz über mehrere
`say()`+`runAndWait()`-Zyklen hinweg wiederzuverwenden – nach dem ersten
Aufruf bleibt die Engine "hängen" und spricht stillschweigend nichts mehr.
Deshalb baut `sage()` bewusst PRO Aufruf eine frische Engine-Instanz auf
(geringer Mehraufwand, aber zuverlässig) statt eine einzige über die ganze
Sitzung wiederzuverwenden.
"""
from __future__ import annotations

import pyttsx3


class Sprachausgabe:
    """Spricht Text laut vor. Wählt automatisch eine deutsche Stimme, falls vorhanden."""

    def __init__(self):
        self._stimme_id = self._finde_deutsche_stimme_id()

    def sage(self, text: str) -> None:
        """Spricht `text` synchron (blockiert, bis die Ausgabe fertig ist)."""
        engine = pyttsx3.init()  # siehe Moduldoku: bewusst neu pro Aufruf, nicht wiederverwendet
        if self._stimme_id is not None:
            engine.setProperty("voice", self._stimme_id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()

    @staticmethod
    def _finde_deutsche_stimme_id() -> str | None:
        engine = pyttsx3.init()
        try:
            for stimme in engine.getProperty("voices"):
                sprachen = [
                    sprache.decode("utf-8", errors="ignore") if isinstance(sprache, bytes) else str(sprache)
                    for sprache in (stimme.languages or [])
                ]
                treffer_ueber_sprachcode = any(sprache.lower().startswith("de") for sprache in sprachen)
                treffer_ueber_id = "de-de" in stimme.id.lower() or "german" in stimme.name.lower()
                if treffer_ueber_sprachcode or treffer_ueber_id:
                    return stimme.id
            return None  # keine deutsche Stimme gefunden -> Systemstandard bleibt aktiv
        finally:
            engine.stop()

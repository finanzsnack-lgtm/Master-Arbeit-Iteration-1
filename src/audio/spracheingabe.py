"""
Spracheingabe: Mikrofon -> Text, lokal über `openai-whisper` (Transkription,
läuft komplett offline auf diesem Rechner, kein API-Key nötig). Ersetzt in
chat.py die `input("Du:  ")`-Abfrage, wenn `AUDIO_MODUS=true` und
`AUDIO_ANBIETER=lokal` (siehe config.py). Alternative: google_speech.py
(Google Cloud Speech-to-Text, bessere Erkennungsqualität, braucht API-Key).

HINWEIS zur Modellwahl: `faster-whisper` (schneller, weniger RAM) wurde
bewusst NICHT verwendet, weil dessen Abhängigkeit `av` (PyAV) auf diesem
Rechner an einer Windows-Anwendungssteuerungsrichtlinie scheiterte (DLL-
Ladefehler beim Import). `openai-whisper` kommt ohne PyAV/ffmpeg aus, wenn
man ihm – wie hier – direkt ein numpy-Array statt eines Dateipfads übergibt.
"""
from __future__ import annotations

import whisper

from src.audio.aufnahme import nimm_sprache_auf


class Spracheingabe:
    """Nimmt eine gesprochene Antwort auf und transkribiert sie zu Text (lokal, Whisper)."""

    def __init__(self, modellgroesse: str = "base", sprache: str = "de"):
        self._modell = whisper.load_model(modellgroesse)
        self._sprache = sprache

    def hoere_zu(
        self, max_dauer_sekunden: float = 15.0, stille_schwelle: float = 0.01, stille_dauer_sekunden: float = 1.5
    ) -> str:
        """Nimmt Mikrofonaudio auf (bis Sprechpause/Timeout) und gibt den transkribierten Text zurück."""
        audio = nimm_sprache_auf(max_dauer_sekunden, stille_schwelle, stille_dauer_sekunden)
        if audio.size == 0:
            return ""
        ergebnis = self._modell.transcribe(audio, language=self._sprache, fp16=False)
        return ergebnis["text"].strip()

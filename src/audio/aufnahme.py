"""
Mikrofonaufnahme über `sounddevice`, unabhängig vom Transkriptions-Anbieter
(lokal via Whisper oder Google Cloud Speech-to-Text, siehe spracheingabe.py
bzw. google_speech.py) – beide nutzen dieselbe Aufnahme-Funktion, damit die
Sprachaktivitätserkennung nur an einer Stelle gepflegt werden muss.

Aufnahme-Ende wird über eine einfache lautstärkebasierte Sprachaktivitäts-
erkennung (RMS-Schwellenwert) bestimmt, keine ausgefeilte VAD-Bibliothek:
Aufnahme läuft, bis nach erkannter Sprache `stille_dauer_sekunden` lang
Stille herrscht, oder spätestens nach `max_dauer_sekunden`.
"""
from __future__ import annotations

import time

import numpy as np
import sounddevice as sd

SAMPLERATE = 16000  # von Whisper UND Google Cloud STT (siehe google_speech.py) erwartete Abtastrate


def nimm_sprache_auf(
    max_dauer_sekunden: float = 15.0, stille_schwelle: float = 0.01, stille_dauer_sekunden: float = 1.5
) -> np.ndarray:
    """Nimmt Mikrofonaudio auf (bis Sprechpause/Timeout) und gibt es als float32-Array (16kHz, mono) zurück."""
    bloecke: list[np.ndarray] = []
    zustand = {"stille_seit": None, "sprache_erkannt": False}

    def callback(indata, frames, zeit_info, status):
        block = indata[:, 0].copy()
        bloecke.append(block)
        lautstaerke = float(np.sqrt(np.mean(np.square(block))))
        if lautstaerke > stille_schwelle:
            zustand["sprache_erkannt"] = True
            zustand["stille_seit"] = None
        elif zustand["sprache_erkannt"] and zustand["stille_seit"] is None:
            zustand["stille_seit"] = time.monotonic()

    start = time.monotonic()
    with sd.InputStream(samplerate=SAMPLERATE, channels=1, dtype="float32", callback=callback):
        while True:
            time.sleep(0.05)
            if time.monotonic() - start >= max_dauer_sekunden:
                break
            stille_seit = zustand["stille_seit"]
            if stille_seit is not None and time.monotonic() - stille_seit >= stille_dauer_sekunden:
                break

    if not bloecke:
        return np.array([], dtype=np.float32)
    return np.concatenate(bloecke)

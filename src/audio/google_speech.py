"""
Sprachein-/ausgabe über die Google Cloud Speech-APIs (REST, per `requests` –
analog zu src/api/google_maps.py, bewusst KEIN google-cloud-* SDK, um nicht
zusätzlich die schwergewichtige grpc/protobuf-Abhängigkeitskette einzuziehen
und um denselben einfachen API-Key wie bei Maps weiterzuverwenden). Aktiv,
wenn `AUDIO_MODUS=true` und `AUDIO_ANBIETER=google_cloud` (siehe config.py).

Voraussetzung in der Google Cloud Console (selbes Projekt wie Maps): "Cloud
Text-to-Speech API" UND "Cloud Speech-to-Text API" aktivieren. Falls der
API-Key auf bestimmte APIs eingeschränkt ist, müssen beide dort ergänzt
werden – sonst kommt ein 403-Fehler ("... API has not been used ...").

Kosten: beide Dienste haben ein monatliches Gratis-Kontingent (Stand siehe
Projektkonversation: TTS Neural2-Stimmen 1 Mio. Zeichen/Monat frei, STT 60
Minuten/Monat frei) – für Testgespräche in diesem Prototyp bei Weitem
ausreichend, aber KEIN unbegrenztes Freikontingent; bei sehr intensiver
Nutzung können Kosten entstehen.
"""
from __future__ import annotations

import base64
import io
import wave

import numpy as np
import requests
import sounddevice as sd

from src.audio.aufnahme import SAMPLERATE, nimm_sprache_auf


def _google_fehlermeldung(antwort: requests.Response) -> str:
    try:
        return antwort.json().get("error", {}).get("message", antwort.text)
    except ValueError:
        return antwort.text


class GoogleSprachausgabe:
    """Spricht Text laut vor, über die Google Cloud Text-to-Speech REST API."""

    _URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def __init__(self, api_key: str, stimme: str = "de-DE-Neural2-F", sprache: str = "de-DE"):
        if not api_key:
            raise ValueError(
                "GoogleSprachausgabe benötigt einen API-Key "
                "(siehe .env: GOOGLE_CLOUD_SPEECH_API_KEY oder GOOGLE_MAPS_API_KEY)."
            )
        self._api_key = api_key
        self._stimme = stimme
        self._sprache = sprache

    def sage(self, text: str) -> None:
        """Synthetisiert `text` und spielt ihn synchron über die Standard-Audioausgabe ab."""
        antwort = requests.post(
            self._URL,
            params={"key": self._api_key},
            json={
                "input": {"text": text},
                "voice": {"languageCode": self._sprache, "name": self._stimme},
                "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
            },
            timeout=15,
        )
        if not antwort.ok:
            raise RuntimeError(f"Google-Cloud-TTS-Fehler ({antwort.status_code}): {_google_fehlermeldung(antwort)}")

        audio_bytes = base64.b64decode(antwort.json()["audioContent"])
        with wave.open(io.BytesIO(audio_bytes)) as wav_datei:
            samplerate = wav_datei.getframerate()
            kanaele = wav_datei.getnchannels()
            frames = wav_datei.readframes(wav_datei.getnframes())

        samples = np.frombuffer(frames, dtype=np.int16)
        if kanaele > 1:
            samples = samples.reshape(-1, kanaele)
        sd.play(samples, samplerate)
        sd.wait()


class GoogleSpracheingabe:
    """Nimmt eine gesprochene Antwort auf und transkribiert sie über die Google Cloud Speech-to-Text REST API."""

    _URL = "https://speech.googleapis.com/v1/speech:recognize"

    def __init__(self, api_key: str, sprache: str = "de-DE"):
        if not api_key:
            raise ValueError(
                "GoogleSpracheingabe benötigt einen API-Key "
                "(siehe .env: GOOGLE_CLOUD_SPEECH_API_KEY oder GOOGLE_MAPS_API_KEY)."
            )
        self._api_key = api_key
        self._sprache = sprache

    def hoere_zu(
        self, max_dauer_sekunden: float = 15.0, stille_schwelle: float = 0.01, stille_dauer_sekunden: float = 1.5
    ) -> str:
        """Nimmt Mikrofonaudio auf (bis Sprechpause/Timeout) und gibt den transkribierten Text zurück."""
        audio = nimm_sprache_auf(max_dauer_sekunden, stille_schwelle, stille_dauer_sekunden)
        if audio.size == 0:
            return ""

        pcm16_bytes = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        audio_base64 = base64.b64encode(pcm16_bytes).decode("ascii")

        antwort = requests.post(
            self._URL,
            params={"key": self._api_key},
            json={
                "config": {"encoding": "LINEAR16", "sampleRateHertz": SAMPLERATE, "languageCode": self._sprache},
                "audio": {"content": audio_base64},
            },
            timeout=15,
        )
        if not antwort.ok:
            raise RuntimeError(f"Google-Cloud-STT-Fehler ({antwort.status_code}): {_google_fehlermeldung(antwort)}")

        ergebnisse = antwort.json().get("results", [])
        if not ergebnisse:
            return ""  # z.B. Stille oder nicht verstanden – kein Fehler, das LLM fragt bei leerer Antwort einfach nach
        return ergebnisse[0]["alternatives"][0]["transcript"].strip()

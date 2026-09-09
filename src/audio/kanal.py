"""
Ein-/Ausgabe-Abstraktion für chat.py: Text (Tastatur/Konsole, Standard),
gesprochene Sprache (Mikrofon/Lautsprecher, wenn AUDIO_MODUS=true) oder ein
Browser-Chat über WebSocket (webapp.py, siehe WebIOKanal dort). Der Rest der
Dialogsteuerung (Fragekatalog, Gateways, LLM-Interpretation) muss den
Unterschied nicht kennen – chat.py ruft ausschließlich `bot_sagt`/
`nutzer_antwortet` auf, unabhängig vom aktiven Kanal.

Für den Sprachkanal gibt es zwei Anbieter (siehe config.py: AUDIO_ANBIETER):
"google_cloud" (Google Cloud Speech-APIs, natürlicher, braucht API-Key,
siehe google_speech.py) oder "lokal" (Whisper + pyttsx3, kein Key nötig,
aber schlechtere Qualität – siehe spracheingabe.py/sprachausgabe.py).

`IOKanal` ist bewusst ASYNC (`async def`), obwohl Text-/Audio-Ein-/Ausgabe
selbst rein synchron/blockierend sind (Konsolen-`input()`, Mikrofonaufnahme):
der Browser-Chat (WebIOKanal, webapp.py) muss auf eine WebSocket-Nachricht
warten können, ohne die laufende Event-Loop zu blockieren – das geht nur mit
einem echten `await`. TextKanal/AudioKanal bleiben innerhalb ihrer async-
Methoden weiterhin synchron blockierend (unproblematisch: chat.py läuft als
einzelner Konsolen-Prozess ohne Nebenläufigkeit, die dabei verpasst würde).
"""
from __future__ import annotations

from typing import Protocol

from src.api.typen import Unterkunft


class _SprachausgabeProtokoll(Protocol):
    def sage(self, text: str) -> None: ...


class _SpracheingabeProtokoll(Protocol):
    def hoere_zu(self) -> str: ...


class IOKanal(Protocol):
    async def bot_sagt(self, text: str) -> None: ...
    async def nutzer_antwortet(self) -> str: ...
    async def zeige_karte(self, unterkunft: Unterkunft) -> None: ...


class TextKanal:
    """Standard-Kanal: Konsolen-Ein-/Ausgabe."""

    async def bot_sagt(self, text: str) -> None:
        print(f"Bot: {text}")

    async def nutzer_antwortet(self) -> str:
        return input("Du:  ").strip()

    async def zeige_karte(self, unterkunft: Unterkunft) -> None:
        # Kein Bildschirm für Fotos in der Konsole – Name/Preisniveau nennt das LLM ohnehin schon
        # im gesprochenen/gedruckten Vorschlagstext, siehe vorschlaege.py::suche_unterkunft.
        pass


class AudioKanal:
    """
    Sprachkanal: Bot-Text wird vorgelesen (Sprachausgabe), Nutzerantwort wird
    per Mikrofon aufgenommen und transkribiert (Spracheingabe) – unabhängig
    davon, ob lokal (Whisper/pyttsx3) oder über Google Cloud (siehe
    google_speech.py). Gibt zusätzlich alles als Text auf der Konsole aus –
    als Transkript für Protokoll (src/protokoll.py), Barrierefreiheit und
    Debugging.
    """

    def __init__(self, spracheingabe: _SpracheingabeProtokoll, sprachausgabe: _SprachausgabeProtokoll):
        self._spracheingabe = spracheingabe
        self._sprachausgabe = sprachausgabe

    async def bot_sagt(self, text: str) -> None:
        print(f"Bot: {text}")
        self._sprachausgabe.sage(text)

    async def nutzer_antwortet(self) -> str:
        print("Du:  (jetzt sprechen ...)")
        text = self._spracheingabe.hoere_zu()
        print(f"Du:  {text}")
        return text

    async def zeige_karte(self, unterkunft: Unterkunft) -> None:
        pass  # siehe TextKanal.zeige_karte


def erzeuge_kanal(
    audio_modus: bool,
    audio_anbieter: str = "google_cloud",
    whisper_modellgroesse: str = "base",
    google_cloud_speech_api_key: str | None = None,
) -> IOKanal:
    """
    Wählt anhand der Konfiguration den Text- oder den Audio-Kanal (und bei
    Audio: welchen Anbieter). Die Audio-Abhängigkeiten (siehe
    requirements-audio.txt) werden bewusst erst HIER importiert, nicht auf
    Modulebene – wer AUDIO_MODUS=false lässt (Standard), braucht sie gar
    nicht installiert zu haben.
    """
    if not audio_modus:
        return TextKanal()

    if audio_anbieter == "google_cloud":
        from src.audio.google_speech import GoogleSpracheingabe, GoogleSprachausgabe

        if not google_cloud_speech_api_key:
            raise ValueError(
                "AUDIO_ANBIETER=google_cloud, aber kein API-Key gefunden "
                "(GOOGLE_CLOUD_SPEECH_API_KEY oder GOOGLE_MAPS_API_KEY in .env). "
                "Alternativ AUDIO_ANBIETER=lokal setzen (kein Key nötig, siehe .env.example)."
            )
        return AudioKanal(
            GoogleSpracheingabe(google_cloud_speech_api_key), GoogleSprachausgabe(google_cloud_speech_api_key)
        )

    from src.audio.spracheingabe import Spracheingabe
    from src.audio.sprachausgabe import Sprachausgabe

    return AudioKanal(Spracheingabe(modellgroesse=whisper_modellgroesse), Sprachausgabe())

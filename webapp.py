"""
Web-Oberfläche für den Reisebot: dieselbe Dialoglogik wie chat.py (siehe dort – `hauptablauf`
bleibt unverändert die zentrale Ablaufsteuerung), nur über einen Browser-Chat statt die Konsole
angesteuert.

Transport: WebSocket (`/ws/chat`), siehe `WebIOKanal` unten – implementiert dieselbe `IOKanal`-
Schnittstelle wie TextKanal/AudioKanal (src/audio/kanal.py), nur über Browser-Nachrichten statt
Konsole/Mikrofon. Der eigentliche Dialog (welche Frage wann, Werkzeuge, Validierung, Optimierung)
läuft dadurch UNVERÄNDERT über chat.py::hauptablauf – webapp.py fügt nur einen neuen Kanal sowie
eine abschließende Karten-Ansicht (Foto, Kurzbeschreibung, Maps-Link je Unterkunft/POI) hinzu, NUR
im fertigen Reiseplan am Ende, nicht live während des Gesprächs.

Fotos werden ERST NACH Abschluss der Planung serverseitig heruntergeladen (siehe
src/ausgabe/fotos.py) und als statische Dateien ausgeliefert – der Google-Maps-API-Key bleibt
dadurch ausschließlich serverseitig (siehe google_maps.py `lade_foto`), der Browser bekommt ihn
nie zu Gesicht.

Aufruf: uvicorn webapp:app  (siehe README.md)

KEIN --reload unter Windows: Uvicorns Reload-Modus wechselt dort intern von der ProactorEventLoop
auf die SelectorEventLoop (uvicorn/loops/asyncio.py, `use_subprocess`-Zweig) – die
SelectorEventLoop kann unter Windows aber keine Subprozesse starten, und genau das braucht das
Claude Agent SDK beim Verbindungsaufbau (startet die Claude-Code-CLI als Subprozess). Ergebnis ohne
diesen Hinweis: `NotImplementedError` beim ersten Chat-Aufruf. Code-Änderungen erfordern mit dieser
Einstellung einen manuellen Neustart des Servers statt Auto-Reload.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from chat import hauptablauf
from src.api.google_maps import erzeuge_client
from src.api.typen import Unterkunft
from src.audio.kanal import IOKanal
from src.ausgabe.fotos import lade_fotos_fuer_plan
from src.ausgabe.reiseplan import als_kartendaten, als_text, maps_link
from src.optimierung.kostenschaetzung import schaetze_unterkunft_preis_pro_nacht

_WURZEL_VERZEICHNIS = Path(__file__).resolve().parent
# Eigenes fotos/-Unterverzeichnis in ergebnisse/ (nicht direkt darin), damit die pro Sitzung
# heruntergeladenen Bilder nicht mit den Text-/JSON-/CSV-Ausgaben von agent_tools.py kollidieren.
_FOTO_VERZEICHNIS = _WURZEL_VERZEICHNIS / "ergebnisse" / "fotos"
_FOTO_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
_STATIC_VERZEICHNIS = _WURZEL_VERZEICHNIS / "static"

app = FastAPI(title="Reisebot")
app.mount("/fotos", StaticFiles(directory=str(_FOTO_VERZEICHNIS)), name="fotos")
app.mount("/static", StaticFiles(directory=str(_STATIC_VERZEICHNIS)), name="static")


class WebIOKanal:
    """
    `IOKanal`-Implementierung für den Browser-Chat: `bot_sagt` schickt eine Nachricht über die
    WebSocket-Verbindung, `nutzer_antwortet` wartet (async, ohne die Event-Loop zu blockieren) auf
    die nächste Nachricht vom Browser. Ersetzt TextKanal/AudioKanal 1:1 für chat.py::hauptablauf –
    der Dialogablauf selbst weiß nichts von WebSockets.

    `zeige_karte` (Nutzerwunsch: Hotel-Foto+Preis schon bei der F15-Bestätigungsfrage MITTEN im
    Gespräch, nicht erst im fertigen Reiseplan) lädt das Foto der vorgeschlagenen Unterkunft SOFORT
    herunter (eigener `MapsClient`, eigener Sitzungsordner – unabhängig vom Batch-Download am Ende
    in `websocket_chat`, da der Reiseplan zu diesem Zeitpunkt noch gar nicht existiert).
    """

    def __init__(self, websocket: WebSocket, foto_verzeichnis: Path):
        self._websocket = websocket
        self._foto_verzeichnis = foto_verzeichnis
        self._maps_client = erzeuge_client()

    async def bot_sagt(self, text: str) -> None:
        await self._websocket.send_json({"typ": "bot", "text": text})

    async def nutzer_antwortet(self) -> str:
        nachricht = await self._websocket.receive_json()
        return str(nachricht.get("text", ""))

    async def zeige_karte(self, unterkunft: Unterkunft) -> None:
        foto_url = None
        if unterkunft.foto_referenz and unterkunft.place_id:
            self._foto_verzeichnis.mkdir(parents=True, exist_ok=True)
            dateiname = f"{unterkunft.place_id}.jpg"
            ziel_pfad = self._foto_verzeichnis / dateiname
            if self._maps_client.lade_foto(unterkunft.foto_referenz, str(ziel_pfad)):
                foto_url = f"/fotos/{self._foto_verzeichnis.name}/{dateiname}"
        await self._websocket.send_json(
            {
                "typ": "hotel_karte",
                "name": unterkunft.name,
                "preis_pro_nacht_euro": schaetze_unterkunft_preis_pro_nacht(unterkunft.preisniveau),
                "foto_url": foto_url,
                "maps_link": maps_link(unterkunft.place_id),
            }
        )


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (_STATIC_VERZEICHNIS / "index.html").read_text(encoding="utf-8")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    sitzung_id = uuid.uuid4().hex[:8]
    kanal: IOKanal = WebIOKanal(websocket, _FOTO_VERZEICHNIS / sitzung_id)

    try:
        state = await hauptablauf(
            io_kanal=kanal, protokoll_praefix="web", ausgabe_basisname=f"reiseplan_web_{sitzung_id}"
        )
    except WebSocketDisconnect:
        return  # Browser-Tab/Verbindung wurde vom Nutzer geschlossen, nichts weiter zu tun.
    except RuntimeError as fehler:
        # uvicorn meldet einen mitten im Gespräch abgebrochenen Verbindung (Tab zu, Reload,
        # Netzwerkaussetzer) nicht immer als WebSocketDisconnect – manchmal erst beim NÄCHSTEN
        # Sendeversuch des Bots als roher RuntimeError ("Unexpected ASGI message 'websocket.send',
        # after sending 'websocket.close'"), siehe uvicorn/protocols/websockets/*. Nur DIESES
        # spezifische Muster abfangen (Verbindung ist weg, nichts mehr zu tun) – ein "echter"
        # RuntimeError (z.B. ein Google-Maps-API-Fehler mitten in der Planung) soll weiterhin als
        # Fehler sichtbar bleiben statt stillschweigend zu verschwinden.
        if "websocket" in str(fehler).lower():
            return
        raise

    if state is None or not (state.abgeschlossen and state.reiseplan is not None):
        # LLMVerbindungsFehler (state is None) ODER abgebrochen (breche_planung_ab) – hauptablauf
        # hat die passende Meldung bereits über den Kanal an den Browser geschickt.
        try:
            await websocket.close()
        except RuntimeError:
            pass
        return

    fotos = lade_fotos_fuer_plan(state.reiseplan, state.maps_client, _FOTO_VERZEICHNIS / sitzung_id)

    def foto_url(place_id: str | None) -> str | None:
        dateiname = fotos.get(place_id) if place_id else None
        return f"/fotos/{sitzung_id}/{dateiname}" if dateiname else None

    try:
        await websocket.send_json(
            {
                "typ": "ergebnis",
                "text": als_text(state.reiseplan),
                "nachhaltigkeits_nudge": state.nachhaltigkeits_nudge,
                "meldungen": state.abschluss_meldungen,
                "karten": als_kartendaten(state.reiseplan, foto_url),
            }
        )
    except WebSocketDisconnect:
        return

    try:
        await websocket.close()
    except RuntimeError:
        pass


if __name__ == "__main__":
    import uvicorn

    # KEIN reload=True unter Windows – siehe Moduldoku oben (Subprozess-Konflikt mit dem Claude
    # Agent SDK).
    uvicorn.run("webapp:app", host="127.0.0.1", port=8000)

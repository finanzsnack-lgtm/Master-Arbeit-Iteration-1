"""
Tests für die deterministische Logik in webapp.py (WebIOKanal.zeige_karte, Hotel-Vorschau-Karte
mitten im Chat) – kein echter Server/WebSocket, nur Fake-Objekte für Websocket/MapsClient. Der
restliche WebSocket-/FastAPI-Verdrahtungscode (Routing, Verbindungsaufbau) wird wie bei chat.py
manuell verifiziert, nicht per pytest (siehe tests/conftest.py-Philosophie).
"""
import asyncio

import webapp
from src.api.typen import Unterkunft


class _FakeWebSocket:
    def __init__(self):
        self.gesendete_nachrichten: list[dict] = []

    async def send_json(self, daten: dict) -> None:
        self.gesendete_nachrichten.append(daten)


class _FakeMapsClient:
    def __init__(self, erfolgreich: bool):
        self._erfolgreich = erfolgreich

    def lade_foto(self, foto_referenz: str, ziel_pfad: str, max_breite: int = 640) -> bool:
        if self._erfolgreich:
            with open(ziel_pfad, "w", encoding="utf-8") as datei:
                datei.write("fake")
        return self._erfolgreich


def test_zeige_karte_sendet_foto_url_bei_erfolgreichem_download(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "erzeuge_client", lambda: _FakeMapsClient(erfolgreich=True))
    websocket = _FakeWebSocket()
    kanal = webapp.WebIOKanal(websocket, tmp_path / "sitzung123")
    unterkunft = Unterkunft(id=1, name="Hotel Zentral", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=False,
                             place_id="hz1", foto_referenz="ref1")

    asyncio.run(kanal.zeige_karte(unterkunft))

    [nachricht] = websocket.gesendete_nachrichten
    assert nachricht["typ"] == "hotel_karte"
    assert nachricht["name"] == "Hotel Zentral"
    assert nachricht["foto_url"] == "/fotos/sitzung123/hz1.jpg"
    assert nachricht["preis_pro_nacht_euro"] is not None
    assert "query_place_id=hz1" in nachricht["maps_link"]


def test_zeige_karte_ohne_foto_referenz_sendet_keine_foto_url(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "erzeuge_client", lambda: _FakeMapsClient(erfolgreich=True))
    websocket = _FakeWebSocket()
    kanal = webapp.WebIOKanal(websocket, tmp_path / "sitzung123")
    unterkunft = Unterkunft(id=1, name="Hotel Zentral", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=False, place_id="hz1")

    asyncio.run(kanal.zeige_karte(unterkunft))

    [nachricht] = websocket.gesendete_nachrichten
    assert nachricht["foto_url"] is None


def test_zeige_karte_bei_fehlgeschlagenem_download_sendet_keine_foto_url(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "erzeuge_client", lambda: _FakeMapsClient(erfolgreich=False))
    websocket = _FakeWebSocket()
    kanal = webapp.WebIOKanal(websocket, tmp_path / "sitzung123")
    unterkunft = Unterkunft(id=1, name="Hotel Zentral", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=False,
                             place_id="hz1", foto_referenz="ref1")

    asyncio.run(kanal.zeige_karte(unterkunft))

    [nachricht] = websocket.gesendete_nachrichten
    assert nachricht["foto_url"] is None


def test_zeige_karte_ohne_preisniveau_sendet_keinen_preis(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "erzeuge_client", lambda: _FakeMapsClient(erfolgreich=True))
    websocket = _FakeWebSocket()
    kanal = webapp.WebIOKanal(websocket, tmp_path / "sitzung123")
    unterkunft = Unterkunft(id=1, name="Hotel Zentral", x=0, y=0, preisniveau=None, zertifiziert_nachhaltig=False, place_id="hz1")

    asyncio.run(kanal.zeige_karte(unterkunft))

    [nachricht] = websocket.gesendete_nachrichten
    assert nachricht["preis_pro_nacht_euro"] is None

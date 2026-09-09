"""
Lädt Places-Fotos (Foto-Referenzen aus google_maps.py, siehe `POI.foto_referenz`/
`Unterkunft.foto_referenz`) für die Unterkunft und alle im fertigen Reiseplan eingeplanten POIs
serverseitig herunter – NUR von der Web-UI (webapp.py) aufgerufen, NICHT von chat.py oder
pruefe_planung.py, damit im normalen Konsolen-Chat keine zusätzlichen, ungewollten API-Aufrufe/
Kosten entstehen. Der API-Key bleibt dabei serverseitig (siehe google_maps.py `lade_foto`); der
Browser bekommt nur die fertigen Bilddateien ausgeliefert, nie den Key selbst.
"""
from __future__ import annotations

from pathlib import Path

from src.api.google_maps import MapsClient
from src.ausgabe.reiseplan import Reiseplan


def lade_fotos_fuer_plan(plan: Reiseplan, client: MapsClient, zielordner: Path) -> dict[str, str]:
    """
    Lädt ein Foto für die Unterkunft (falls `unterkunft_foto_referenz` vorhanden) sowie für jeden
    tatsächlich EINGEPLANTEN POI (Tagesrouten – bewusst NICHT `weitere_aktivitaeten_empfehlungen`,
    die sind nur lose Zusatzvorschläge, kein Teil des konkreten Vorschlags).

    Rückgabe: dict `place_id -> Dateiname` (relativ zu `zielordner`), NUR für Downloads, die
    tatsächlich geklappt haben (`MapsClient.lade_foto` liefert False statt zu werfen, siehe dort) –
    kein Eintrag für fehlgeschlagene oder fehlende Fotos, statt einen kaputten Bildverweis
    auszugeben (Grundprinzip 1: ehrliches Fehlen statt eines erfundenen Platzhalters).
    """
    zielordner.mkdir(parents=True, exist_ok=True)
    dateiname_je_place_id: dict[str, str] = {}

    if plan.unterkunft_foto_referenz and plan.unterkunft_place_id:
        dateiname = f"{plan.unterkunft_place_id}.jpg"
        if client.lade_foto(plan.unterkunft_foto_referenz, str(zielordner / dateiname)):
            dateiname_je_place_id[plan.unterkunft_place_id] = dateiname

    for tagesroute in plan.tagesrouten:
        for besuch in tagesroute.besuche:
            poi = besuch.poi
            if not poi.foto_referenz or not poi.place_id or poi.place_id in dateiname_je_place_id:
                continue
            dateiname = f"{poi.place_id}.jpg"
            if client.lade_foto(poi.foto_referenz, str(zielordner / dateiname)):
                dateiname_je_place_id[poi.place_id] = dateiname

    return dateiname_je_place_id

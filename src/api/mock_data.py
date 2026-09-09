"""
Beispieldaten für den Mock-Modus (siehe CLAUDE.md: "Entwicklung immer mit
Mock-Modus"). Diese Daten sind frei erfunden und dienen ausschließlich dazu,
den Prototyp ohne Google-Maps-Key entwickeln und testen zu können. Sobald ein
echter Key vorliegt, ersetzt `GoogleMapsClient` (siehe google_maps.py) diese
Werte durch reale API-Antworten – der Rest des Programms muss dafür nicht
angepasst werden (gleiche Schnittstelle `MapsClient`).
"""
from __future__ import annotations

from src.api.typen import POI, ReiseAlternative, Unterkunft

# Score wird hier bewusst neutral mit 1.0 vorbelegt: Die eigentliche
# Bewertung (Präferenz-Matching gegen die Nutzerantworten) übernimmt
# src/datenaufbereitung/aufbereitung.py::berechne_poi_score.
#
# `opening`/`closing` sind – wie in typen.py dokumentiert – relativ zum
# Start der jeweiligen Tagesroute (t=0), nicht zu Mitternacht, und liegen
# daher bewusst innerhalb des Standard-Tagesbudgets (600 Minuten, siehe
# .env.example: STANDARD_TAGESBUDGET_MINUTEN).
BEISPIEL_POIS: list[POI] = [
    POI(id=1, name="Altstadt-Museum", kategorie="kultur", x=48.1372, y=11.5755,
        score=1.0, required_time=90, opening=30, closing=540, place_id="mock-poi-1"),
    POI(id=2, name="Stadtpark", kategorie="natur", x=48.1400, y=11.5800,
        score=1.0, required_time=60, opening=0, closing=580),
    POI(id=3, name="Streetfood-Markt", kategorie="kulinarik", x=48.1350, y=11.5700,
        score=1.0, required_time=45, opening=120, closing=560, place_id="mock-poi-3"),
    POI(id=4, name="Aussichtsturm", kategorie="natur", x=48.1450, y=11.5650,
        score=1.0, required_time=50, opening=0, closing=500),
    POI(id=5, name="Kunstgalerie", kategorie="kultur", x=48.1320, y=11.5820,
        score=1.0, required_time=75, opening=60, closing=520),
    POI(id=6, name="Kochkurs", kategorie="kulinarik", x=48.1380, y=11.5900,
        score=1.0, required_time=120, opening=180, closing=560),
    POI(id=7, name="Dom", kategorie="kultur", x=48.1385, y=11.5735,
        score=1.0, required_time=45, opening=0, closing=540),
    POI(id=8, name="Biergarten", kategorie="kulinarik", x=48.1410, y=11.5690,
        score=1.0, required_time=90, opening=200, closing=580, place_id="mock-poi-8"),
    POI(id=9, name="Botanischer Garten", kategorie="natur", x=48.1460, y=11.5820,
        score=1.0, required_time=70, opening=0, closing=550),
    POI(id=10, name="Stadtmuseum", kategorie="kultur", x=48.1300, y=11.5680,
        score=1.0, required_time=80, opening=30, closing=530),
    # Für die Verleih-Suche bei erkanntem lokalem Fahrzeugwechsel (siehe vorschlaege.py
    # `_VERLEIH_KATEGORIE_JE_FAHRZEUG`, aufbereitung.py `erkenne_leihwunsch`) – `kategorie` entspricht
    # hier bewusst dem SUCHBEGRIFF ("Autoverleih"/"Fahrradverleih"), den MockGoogleMapsClient.
    # suche_pois als Freitext-Interesse erhält (Mock bildet KEINE echte Text-Search-Relevanz nach,
    # siehe google_maps.py), NICHT einem Google-Place-Type wie beim echten Client. Tauchen bei jeder
    # anderen Interessensuche automatisch nicht auf (kein Teilstring-Treffer), nur bei gezielter
    # Verleih-Suche.
    POI(id=11, name="Autoverleih City", kategorie="autoverleih", x=48.1365, y=11.5770,
        score=1.0, required_time=15, opening=0, closing=600, place_id="mock-poi-11"),
    POI(id=12, name="Rad-Verleih Zentrum", kategorie="fahrradverleih", x=48.1375, y=11.5745,
        score=1.0, required_time=15, opening=0, closing=600, place_id="mock-poi-12"),
]

BEISPIEL_UNTERKUENFTE: list[Unterkunft] = [
    Unterkunft(id=1, name="Hotel Zentral", x=48.1370, y=11.5760, preisniveau=2,
               zertifiziert_nachhaltig=True, place_id="mock-unterkunft-1"),
    Unterkunft(id=2, name="Hostel Backpacker", x=48.1330, y=11.5680, preisniveau=1,
               zertifiziert_nachhaltig=False, place_id="mock-unterkunft-2"),
]

# Demo-Zuordnung für MockGoogleMapsClient.ist_barrierefrei (siehe google_maps.py) –
# `wheelchair_accessible_entrance` kommt in echt aus Google Place Details, hier
# fest vorbelegt, um alle drei möglichen Zustände zeigen zu können: True
# (mock-poi-1), False (mock-poi-8), "keine Angabe" (jede nicht gelistete
# place_id, inkl. mock-poi-3/mock-unterkunft-1/2 – bewusst NICHT erfunden).
BEISPIEL_BARRIEREFREIHEIT: dict[str, bool] = {
    "mock-poi-1": True,
    "mock-poi-8": False,
}

BEISPIEL_REISEALTERNATIVEN: list[ReiseAlternative] = [
    ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=360, kosten_euro=89.0, distanz_km=650),
    ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=300, kosten_euro=110.0, distanz_km=650),
    ReiseAlternative(verkehrsmittel="Fernbus", dauer_minuten=480, kosten_euro=45.0, distanz_km=650),
]

BEISPIEL_KOORDINATEN: dict[str, tuple[float, float]] = {
    "Wohnort": (52.5200, 13.4050),
    "Zielregion": (48.1372, 11.5755),
}

# Beispieldaten für den Mock-Modus von src/api/overpass.py::MockOverpassClient
# (Spezialrecherche für Aktivitäten wie Klettern/Wandern, siehe dort). Frei
# erfunden, `kategorie` entspricht dem Schlüsselwort aus
# overpass.py::_AKTIVITAET_ALIASE.
BEISPIEL_SPEZIAL_POIS: list[POI] = [
    POI(id=101, name="Klettergarten Musterfelsen", kategorie="klettern", x=48.1500, y=11.6000,
        score=1.0, required_time=180, opening=0, closing=1320,
        quelle="osm_overpass", schwierigkeitsgrad="6a"),
    POI(id=102, name="Wanderweg Panoramasteig", kategorie="wandern", x=48.1550, y=11.5500,
        score=1.0, required_time=240, opening=0, closing=1320,
        quelle="osm_overpass", schwierigkeitsgrad="T3"),
]

"""Datentypen, die zwischen dem API-Layer und der Optimierung ausgetauscht werden."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class POI:
    """Ein Point of Interest, wie er für Optimierung 1 (TOPTW) benötigt wird."""

    id: int
    name: str
    kategorie: str
    x: float  # geographische Koordinate (Breite oder umgerechnete Ortskoordinate)
    y: float  # geographische Koordinate (Länge)
    score: float  # wird erst in der Datenaufbereitung per Präferenz-Matching gesetzt
    required_time: int  # Besuchsdauer in Minuten
    # WICHTIG: `opening`/`closing` sind relativ zum Start JEDER Tagesroute
    # (t=0 = Aufbruch an diesem Tag, z.B. Check-out-Zeit), NICHT relativ zu
    # Mitternacht. `simuliere_route` (toptw.py) setzt für jeden Tag erneut
    # uhrzeit=0 – ein POI mit opening=540 öffnet also 540 Minuten NACH
    # Tagesbeginn, unabhängig von der echten Uhrzeit.
    opening: int  # Öffnungszeit in Minuten ab Start der jeweiligen Tagesroute
    closing: int  # Schließzeit in Minuten ab Start der jeweiligen Tagesroute
    # Places-API `place_id`, für einen klickbaren Google-Maps-Link in der
    # Reiseplan-Ausgabe (siehe reiseplan.py::maps_link). None im Mock-Modus,
    # da MockGoogleMapsClient keine echte place_id liefert.
    place_id: str | None = None
    # Woher dieser POI stammt: "google_places" (Standard) oder "osm_overpass"
    # (siehe src/api/overpass.py – Spezialrecherche für Aktivitäten, die
    # Google Places nicht sinnvoll abdeckt, z.B. Kletterrouten mit
    # Schwierigkeitsgrad). Für Transparenz in Ausgabe/Auswertung, siehe
    # Projektkonversation.
    quelle: str = "google_places"
    # Fachlicher Schwierigkeitsgrad, falls die Quelle einen liefert (z.B.
    # OSM-Tag `climbing:grade:french`, `piste:difficulty`, `sac_scale`).
    # None, wenn nicht vorhanden – wird NIE erfunden (CLAUDE.md Grundprinzip 1).
    schwierigkeitsgrad: str | None = None
    # Der WORTLAUT des Nutzerinteresses, für das dieser Treffer gefunden wurde (z.B. "Klettern",
    # "über Brücken spazieren gehen") – siehe google_maps.py `suche_pois`/overpass.py
    # `suche_spezial_pois`: JEDES Interesse wird als eigene Suche (Places Text Search bzw. Overpass-
    # Abfrage) ausgeführt, dieser POI ist also PER KONSTRUKTION ein Treffer für genau dieses
    # Interesse. BEHOBENER BUG (siehe Projektkonversation: "ich möchte klettern, nicht ins Gym"):
    # vorher wurde jedes Interesse zwangsweise auf einen von ~100 festen Google-Place-Types gepresst
    # (z.B. "Klettern" -> "gym"), was strukturell falsch/zu grob war UND nachträglich per
    # Schlüsselwort-Heuristik wieder zurückgematcht werden musste. Jetzt übernimmt Googles eigene
    # Textsuche die Interpretation des Freitexts, `nutzerinteresse` hält nur noch fest, WOFÜR gesucht
    # wurde – aufbereitung.py::berechne_poi_score muss dadurch nichts mehr raten. None nur bei Quellen
    # außerhalb der interessengebundenen Suche (aktuell keine, siehe Moduldoku dort).
    nutzerinteresse: str | None = None
    # Grobe Einordnung für den Mindestabstand zwischen thematisch ähnlichen Besuchen AM SELBEN TAG
    # (siehe optimierung/toptw.py `simuliere_route`/`_STANDARD_MINDESTABSTAND_MINUTEN`, z.B.
    # "mahlzeit" für Restaurants). Aus Googles eigenem zurückgelieferten Typ abgeleitet (siehe
    # google_maps.py `besuchsklasse_fuer_typ`), NICHT vom Nutzerinteresse-Wortlaut – die Frage "ist
    # das ein Restaurant/Café/Bar" beantwortet Google zuverlässiger als der Suchbegriff selbst
    # (siehe Projektkonversation: "zwei Restaurants hintereinander macht keinen Sinn, aber Kaffee
    # nach dem Restaurant ist okay"). None = keine Beschränkung (Standardfall für die meisten POIs).
    besuchsklasse: str | None = None
    # Places-Foto-Referenz (`photos[0].photo_reference`, siehe google_maps.py) für die Bild-Karte
    # in der Web-UI (webapp.py/src/ausgabe/fotos.py) – None im Mock-Modus (MockGoogleMapsClient
    # liefert keine echte Referenz) oder wenn Places kein Foto zu diesem Ort hat.
    foto_referenz: str | None = None
    # Google-Places-`price_level` (0-4), NUR falls Places ihn für diesen Ort liefert (siehe
    # google_maps.py) – None NICHT gleichbedeutend mit "kostenlos", aber bei den meisten POIs ohne
    # Preisniveau (Parks, Aussichtspunkte, Plätze) faktisch zutreffend (siehe
    # src/optimierung/kostenschaetzung.py, das diese Annahme für die informative Kostenschätzung
    # im Reiseplan trifft). Fließt NICHT in Optimierung 1 selbst ein (nur Anzeige).
    preisniveau: int | None = None


@dataclass
class Unterkunft:
    id: int
    name: str
    x: float
    y: float
    preisniveau: int  # 0-4, wie von der Places API geliefert
    zertifiziert_nachhaltig: bool
    place_id: str | None = None  # siehe POI.place_id
    foto_referenz: str | None = None  # siehe POI.foto_referenz


@dataclass
class Teilstrecke:
    """
    EIN Abschnitt einer ÖPNV-Route (eine Zugfahrt ODER ein Fußweg/Umstieg),
    aus Google Directions `legs[0].steps` (siehe google_maps.py `_hole_route`).

    Ersetzt die vorherige Praxis, von einer Bahn-/Fernbus-Route nur die
    GESAMTDAUER zu übernehmen und den Rest (Umstiege, Linien, Wartezeiten)
    wegzuwerfen (Projektkonversation: "nicht nur sagen 'mit Bahn brauchst du
    eine Stunde', sondern 30 min dahin, dann umsteigen mit 5 min Wartezeit,
    dann 25 min Fahrzeit").
    """

    modus: str  # "TRANSIT" oder "WALKING" (Google Directions `travel_mode`)
    linie: str | None  # z.B. "ICE 123", nur bei modus="TRANSIT"
    von: str  # Abfahrtshaltestelle bzw. "Fußweg" bei modus="WALKING"
    nach: str
    dauer_minuten: int
    # Wartezeit VOR diesem Abschnitt (Lücke zwischen Ankunft der vorherigen
    # und Abfahrt dieser Teilstrecke), NUR wenn Google beide Zeitstempel
    # geliefert hat – sonst None statt eine Wartezeit zu erfinden
    # (Grundprinzip 1: keine erfundenen Fakten).
    wartezeit_minuten: int | None = None


@dataclass
class ReiseAlternative:
    """Eine An-/Abreisealternative für Optimierung 2 (z.B. Bahn vs. Auto vs. Fernbus)."""

    verkehrsmittel: str
    dauer_minuten: int
    kosten_euro: float
    distanz_km: float
    # Detaillierte Teilstrecken (Umstiege, Linien, Wartezeiten) – NUR bei
    # Bahn/Fernbus (mode=transit) gefüllt, siehe google_maps.py `_hole_route`.
    # Leer bei Auto (eine einzige Teilstrecke ohne Umstieg) oder wenn Google
    # keine Schritt-Details geliefert hat.
    teilstrecken: list[Teilstrecke] = field(default_factory=list)

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
    # Reiseplan-Ausgabe (siehe reiseplan.py::_maps_link). None im Mock-Modus,
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


@dataclass
class Unterkunft:
    id: int
    name: str
    x: float
    y: float
    preisniveau: int  # 0-4, wie von der Places API geliefert
    zertifiziert_nachhaltig: bool
    place_id: str | None = None  # siehe POI.place_id
    # Verpflegungsart, NUR gesetzt für über die externe Hotelsuche (Hotelbeds,
    # siehe src/api/hotelbeds.py) gefundene Unterkünfte (z.B. "ALL INCLUSIVE")
    # – Google Places liefert diese Information nicht, bleibt dort None statt
    # erfunden zu werden (CLAUDE.md Grundprinzip 1).
    board_type: str | None = None
    # Property-Code der externen Hotelsuche (Hotelbeds, siehe src/api/
    # hotelbeds.py), NUR bei Treffern von dort gesetzt – ermöglicht spätere
    # Nachfragen zu GENAU diesem Hotel (z.B. Amenity-Abgleich für
    # Aktivitäten, siehe vorschlaege.py) ohne erneute Suche.
    externe_hotel_id: str | None = None
    # Realer Preis/Nacht in EUR, NUR bei Treffern der externen Hotelsuche
    # gesetzt (aus dem Angebot, siehe src/api/hotelbeds.py) – Google Places
    # liefert nur die grobe `preisniveau`-Stufe (0-4), keinen echten Preis.
    # Dient als reales Budget-Signal beim Ranking mehrerer Kandidaten (siehe pipeline.py).
    preis_pro_nacht: float | None = None


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

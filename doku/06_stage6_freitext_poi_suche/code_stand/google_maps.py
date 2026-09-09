"""
Kapselt den Zugriff auf die Google Maps Platform (Places, Distance Matrix,
Directions, Geocoding) – siehe CLAUDE.md, Abschnitt "APIs & Dienste".

Zwei Implementierungen der gleichen Schnittstelle (`MapsClient`):
- `MockGoogleMapsClient`: liefert Beispieldaten, kostenlos und ohne Key.
  Aktiv, solange `Einstellungen.mock_modus` True ist (Default, bis ein
  echter API-Key eingetragen wird).
- `GoogleMapsClient`: ruft die echte API über `requests` auf. Benötigt
  `GOOGLE_MAPS_API_KEY` in der `.env` (siehe .env.example).

`erzeuge_client()` wählt anhand der Konfiguration automatisch die passende
Implementierung – der Rest des Programms muss den Unterschied nicht kennen.

STATUS `GoogleMapsClient`: implementiert, aber noch NICHT gegen die echte API
getestet (kein Key verfügbar, siehe Projektkonversation). Bitte nach dem
Eintragen eines echten Keys einmal `python main.py` mit `MOCK_MODE=false`
laufen lassen und Auffälligkeiten melden. Bekannte, bewusste
Vereinfachungen (siehe auch Kommentare unten):
- POI-Öffnungszeiten: Places Nearby Search liefert keine vollständigen
  Öffnungszeiten (`opening_hours.periods`); eine zusätzliche Place-Details-
  Anfrage PRO Ort wäre nötig, kostet aber zusätzliche API-Aufrufe/Zeit. Für
  den Prototyp wird daher ein großzügiges Standard-Zeitfenster angenommen
  (ganztägig geöffnet) statt echter Öffnungszeiten – TODO, falls das für die
  Auswertung zu ungenau ist: Place Details ergänzen.
- Unterkunft `zertifiziert_nachhaltig`: Places liefert kein Nachhaltigkeits-
  Zertifikat; Feld bleibt konservativ auf False, statt es zu erfinden
  (CLAUDE.md, Grundprinzip 1).
- Reisekosten (`kosten_euro`): Google Directions liefert Fahrpreise nur für
  einzelne Nahverkehrsanbieter/Regionen zuverlässig (`fare`-Feld). Wo nicht
  vorhanden, wird eine grobe, klar gekennzeichnete Kosten-je-km-Schätzung
  verwendet statt eines erfundenen Festpreises.

BEHOBENE BUGS (erster Live-Test mit echtem Nutzergespräch, siehe
Projektkonversation):
- Fehlender `language`-Parameter: Places lieferte Ortsnamen in der jeweils
  lokalen Sprache des Ergebnisses zurück (z.B. litauisch, arabisch,
  russisch statt deutsch) statt konsistent auf Deutsch. `_get` setzt jetzt
  `language=de` für JEDE Anfrage.
- `suche_pois` fragte nur EINE Google-Place-Type pro Aufruf ab (die erste
  Kategorie, die im starren `_KATEGORIE_ZU_PLACE_TYPE`-Mapping exakt
  passte) – z.B. "essen gehen" oder "Wellness" trafen nie, weil die Nutzer-
  formulierung nicht exakt "kulinarik"/"wellness" lautete, und selbst bei
  mehreren Interessen wurde nur die erste Kategorie überhaupt gesucht.
  Ersetzt durch `_KATEGORIE_ALIASE` (Schlüsselwort-Teilstring-Suche, mehrere
  Treffer möglich) + eine Nearby-Search-Anfrage PRO erkannter Kategorie.
"""
from __future__ import annotations

import math
from itertools import zip_longest
from typing import Protocol

import requests

from src.api import mock_data
from src.api.typen import POI, ReiseAlternative, Teilstrecke, Unterkunft
from src.config import EINSTELLUNGEN


class MapsClient(Protocol):
    def suche_pois(self, ort: str, kategorien: list[str], radius_meter: int = 3000) -> list[POI]: ...
    def suche_unterkuenfte(self, ort: str, praeferenz_text: str | None = None) -> list[Unterkunft]: ...
    def distanzmatrix(self, orte: list[tuple[float, float]], modus: str = "walking") -> list[list[int]]: ...
    def anfahrtszeiten_minuten(
        self, ursprung: tuple[float, float], ziele: list[tuple[float, float]], modus: str = "walking"
    ) -> list[int]: ...
    def reisealternativen(self, von: str, nach: str) -> list[ReiseAlternative]: ...
    def geocode(self, adresse: str) -> tuple[float, float]: ...
    def ist_barrierefrei(self, place_id: str | None) -> bool | None: ...


class MockGoogleMapsClient:
    """Liefert deterministische Beispieldaten aus `mock_data.py`."""

    def suche_pois(self, ort: str, kategorien: list[str], radius_meter: int = 3000) -> list[POI]:
        # Der Mock liefert bewusst immer alle Beispiel-POIs zurück; die
        # inhaltliche Filterung/Gewichtung nach Nutzerpräferenzen übernimmt
        # das Scoring in der Datenaufbereitung, nicht die API-Anfrage selbst.
        # `radius_meter` wird hier bewusst ignoriert (keine echte Umkreissuche im Mock-Modus).
        return list(mock_data.BEISPIEL_POIS)

    def suche_unterkuenfte(self, ort: str, praeferenz_text: str | None = None) -> list[Unterkunft]:
        # Mock liefert immer dieselben Beispiele – `praeferenz_text` wird hier bewusst
        # ignoriert (keine echte Relevanz-Suche im Mock-Modus möglich/nötig).
        return list(mock_data.BEISPIEL_UNTERKUENFTE)

    def distanzmatrix(self, orte: list[tuple[float, float]], modus: str = "walking") -> list[list[int]]:
        # Vereinfachte Luftlinien-Schätzung für den Mock-Modus (Minuten).
        # In der echten Implementierung ersetzt die Google Distance Matrix
        # diese Schätzung durch tatsächliche Reisezeiten (siehe CLAUDE.md,
        # "Zentrale Anpassung" unter Optimierung 1).
        geschwindigkeit_kmh = 4.5 if modus == "walking" else 40.0
        matrix: list[list[int]] = []
        for a in orte:
            zeile = []
            for b in orte:
                distanz_km = math.dist(a, b) * 111  # grobe Umrechnung Grad -> km
                zeile.append(round(distanz_km / geschwindigkeit_kmh * 60))
            matrix.append(zeile)
        return matrix

    def anfahrtszeiten_minuten(
        self, ursprung: tuple[float, float], ziele: list[tuple[float, float]], modus: str = "walking"
    ) -> list[int]:
        # Vereinfachte Luftlinien-Schätzung wie `distanzmatrix`, aber EIN
        # Ursprung -> viele Ziele statt einer vollen NxN-Matrix (siehe
        # Moduldoku bei `GoogleMapsClient.anfahrtszeiten_minuten`).
        geschwindigkeit_kmh = _GESCHWINDIGKEIT_KMH_JE_MODUS.get(modus, 4.5)
        return [round(math.dist(ursprung, ziel) * 111 / geschwindigkeit_kmh * 60) for ziel in ziele]

    def reisealternativen(self, von: str, nach: str) -> list[ReiseAlternative]:
        return list(mock_data.BEISPIEL_REISEALTERNATIVEN)

    def geocode(self, adresse: str) -> tuple[float, float]:
        return mock_data.BEISPIEL_KOORDINATEN.get(adresse, (0.0, 0.0))

    def ist_barrierefrei(self, place_id: str | None) -> bool | None:
        # Feste, kleine Demo-Zuordnung (siehe mock_data.py) statt eines echten
        # Places-Details-Aufrufs – zeigt alle drei möglichen Zustände (True/
        # False/None="keine Angabe") auch ohne echten API-Key demonstrierbar.
        return mock_data.BEISPIEL_BARRIEREFREIHEIT.get(place_id) if place_id else None


# Schlüsselwort -> Google Place Type (https://developers.google.com/maps/
# documentation/places/web-service/place-types). Absichtlich TEILSTRING-
# Suche (nicht exakter Match): Nutzerantworten kommen als Freitext übers LLM
# ("essen gehen", "Wellness/Entspannung", ...), nicht als feste Labels.
# Mehrere Schlüsselwörter dürfen auf denselben Place Type zeigen.
_KATEGORIE_ALIASE: dict[str, str] = {
    "kultur": "museum",
    "museum": "museum",
    "sehenswürdigkeit": "tourist_attraction",
    "natur": "park",
    "park": "park",
    "kulinarik": "restaurant",
    "essen": "restaurant",
    "restaurant": "restaurant",
    "café": "cafe",
    "cafe": "cafe",
    "bar": "bar",
    "sport": "gym",
    # Google Places kennt KEINEN eigenen Place Type für Kletterhallen oder gar
    # Outdoor-Kletterrouten/Felsen (siehe https://developers.google.com/maps/
    # documentation/places/web-service/place-types – vollständige Liste).
    # "gym" ist der einzige halbwegs passende Typ und liefert bestenfalls
    # Fitnessstudios/Kletterhallen, NIE echte Outdoor-Routen mit Schwierig-
    # keitsgrad. Diese Grenze ist bewusst NICHT über einen erfundenen
    # Place Type kaschiert (CLAUDE.md Grundprinzip 1: keine erfundenen
    # Fakten) – der Dialog (siehe katalog.py F16) fragt Schwierigkeitsgrad/
    # Zugang trotzdem ab, weil das für den Nutzer relevanter Gesprächs-
    # kontext ist, auch wenn keine API das exakt beliefern kann.
    "klettern": "gym",
    "kletterhalle": "gym",
    "bouldern": "gym",
    "climbing": "gym",
    "nightlife": "night_club",
    "club": "night_club",
    "wellness": "spa",
    "spa": "spa",
    "entspannung": "spa",
    "shopping": "shopping_mall",
    # Für die Verleih-Suche bei einem erkannten lokalen Fahrzeugwechsel (siehe
    # Projektkonversation: "wenn ich mitm Auto hinfahre und vor Ort Fahrrad
    # fahren möchte, musst du gucken, ob's einen Verleih gibt" – aufbereitung.py
    # `erkenne_leihwunsch`/pipeline.py). "car_rental" ist ein exakter, echter
    # Google Place Type (verifiziert). Für Fahrräder liefert Google KEINEN
    # eigenen "Verleih"-Typ, nur "bicycle_store" (Laden, keine Garantie für
    # Verleih) – wird bewusst als solcher benannt/mit Hinweis ausgegeben statt
    # einen nicht existierenden Typ vorzutäuschen (Grundprinzip 1).
    "autoverleih": "car_rental",
    "mietwagen": "car_rental",
    "fahrradverleih": "bicycle_store",
}


def alias_place_types_fuer(praeferenz: str) -> list[str]:
    """
    Reine Alias-Auflösung (Teilstring-Suche) für EINE Präferenz, OHNE
    Fallback auf `_STANDARD_PLACE_TYPE` (der ist nur für die Places-SUCHE
    gedacht, nicht fürs Scoring – siehe `_waehle_place_types`). Öffentlich,
    weil `berechne_poi_score`
    (src/datenaufbereitung/aufbereitung.py) dieselbe Zuordnung braucht, um zu
    prüfen, ob ein gefundener POI (roher, englischer Google Place Type wie
    "museum") zu einer deutschen Freitext-Präferenz wie "Kultur" passt –
    vorher gab es dafür nur einen rohen Substring-Vergleich, der bei echten
    (nicht-Mock-)Daten praktisch nie traf (siehe Projektkonversation).
    """
    praeferenz_klein = praeferenz.lower()
    return [place_type for schluesselwort, place_type in _KATEGORIE_ALIASE.items() if schluesselwort in praeferenz_klein]


def kategorie_alias_eintraege() -> list[tuple[str, str]]:
    """
    Rohe (Schlüsselwort, Place-Type)-Paare aus `_KATEGORIE_ALIASE`, öffentlich für
    aufbereitung.py::_kategorie_passt_zu_praeferenz – anders als `alias_place_types_fuer` (das nur
    die Ziel-Place-Types liefert) wird hier auch das MATCHENDE Schlüsselwort selbst gebraucht, um
    strukturell zu breite Zuordnungen zu erkennen (z.B. "klettern"->"gym": "gym" deckt auch normale
    Fitnessstudios ab, siehe dortiger Kommentar zum behobenen "wieso wird mir ein Gym vorgeschlagen"-Bug).
    """
    return list(_KATEGORIE_ALIASE.items())


# NUR noch Fallback, falls KEINE genannte Präferenz einem bekannten Place
# Type zugeordnet werden kann (siehe _waehle_place_types) – KEIN "immer
# zusätzlich suchen" mehr für Restaurant/Bar/Spa. Frühere Version suchte
# diese drei IMMER zusätzlich, unabhängig von der Nutzerantwort (siehe
# Projektkonversation, damalige Begründung) – das führte dazu, dass z.B. bei
# "ich möchte klettern" trotzdem Spas/Gyms/sogar branchenfremde Google-
# Treffer (ein Physiotherapeut) mitgesucht und vorgeschlagen wurden. Jetzt
# gilt strikt: gesucht wird NUR, was der Nutzer im Chat tatsächlich genannt
# hat (siehe Projektkonversation: "nur danach soll er auch suchen").
_STANDARD_PLACE_TYPE = "tourist_attraction"

# Grobe, literaturunabhängige Annahme der Besuchsdauer je Place Type (Minuten).
# Ersetzt keine echte Datenquelle; dient nur als Startwert für Optimierung 1.
_BESUCHSDAUER_JE_TYP_MINUTEN: dict[str, int] = {
    "museum": 90,
    "art_gallery": 75,
    "park": 60,
    "restaurant": 45,
    "cafe": 30,
    "bar": 60,
    "tourist_attraction": 60,
    "shopping_mall": 90,
    "night_club": 120,
    "spa": 90,
    "gym": 60,
    "church": 30,
    "zoo": 120,
}
_STANDARD_BESUCHSDAUER_MINUTEN = 60

# Großzügiges Standard-Zeitfenster (siehe Moduldoku: keine Place-Details-
# Anfrage für echte Öffnungszeiten, um API-Aufrufe/Kosten zu sparen).
_STANDARD_OEFFNUNG_MINUTEN = 0
_STANDARD_SCHLIESSUNG_MINUTEN = 22 * 60  # 22:00 relativ zum Tagesbeginn

# Grobe, literaturunabhängige Annahme, ab wie vielen Minuten NACH Tagesbeginn ein Place Type
# thematisch sinnvoll ist (siehe Projektkonversation: "ich sollte nicht direkt nach dem Aufstehen
# in die Bar gehen – das soll dem Tagesablauf logisch angepasst werden"). Ersetzt keine echte
# Öffnungszeiten-Quelle (siehe `_STANDARD_OEFFNUNG_MINUTEN` oben) – wirkt als ZUSÄTZLICHE,
# kategoriebezogene Mindestwartezeit relativ zum jeweiligen Tagesbeginn (egal ob Tagesbeginn die
# tatsächliche Ankunft an Tag 1 oder eine spätere, angegebene Startuhrzeit ist, siehe
# aufbereitung.py `wende_tageszeitfenster_an`) – dadurch bleibt die Regel gültig, OHNE eine
# absolute Uhrzeit zu kennen/erfinden zu müssen. Kein Eintrag -> keine zusätzliche Einschränkung
# (0 Minuten, wie bisher).
_MINDEST_TAGESZEIT_MINUTEN_JE_TYP: dict[str, int] = {
    "bar": 8 * 60,
    "night_club": 9 * 60,
    "restaurant": 3 * 60,
    "shopping_mall": 1 * 60,
    "spa": 1 * 60,
}


def mindest_tageszeit_fuer_typ(place_type: str) -> int:
    """Öffentlich für aufbereitung.py `wende_tageszeitfenster_an` (siehe Kommentar oben)."""
    return _MINDEST_TAGESZEIT_MINUTEN_JE_TYP.get(place_type, 0)

# Grobe Kostenschätzung, falls Directions kein `fare`-Feld liefert (siehe Moduldoku).
_KOSTEN_JE_KM_SCHAETZUNG_EURO = {"driving": 0.20, "transit": 0.12}

# Nur für den Mock-Modus von `anfahrtszeiten_minuten` (grobe Luftlinien-
# Schätzung, analog zu `distanzmatrix`) – im Live-Modus liefert die Google
# Distance Matrix API die echte Dauer je nach `mode`-Parameter direkt.
_GESCHWINDIGKEIT_KMH_JE_MODUS = {"walking": 4.5, "bicycling": 15.0, "transit": 25.0, "driving": 40.0}


def _teilstrecken_aus_steps(steps: list[dict]) -> list[Teilstrecke]:
    """
    Baut aus `legs[0].steps` der Google-Directions-Antwort die echte
    Umstiegs-Kette (Linie, Ein-/Ausstiegshaltestelle, Fahrzeit je Abschnitt,
    Wartezeit beim Umstieg) statt nur der Gesamtdauer (siehe `Teilstrecke`-
    Doku in typen.py für den Hintergrund).

    Wartezeit = Lücke zwischen der Ankunftszeit der vorherigen TRANSIT-
    Teilstrecke und der Abfahrtszeit der nächsten (beide als Unix-Zeitstempel
    in `transit_details.arrival_time.value`/`departure_time.value`) – NUR
    wenn Google beide Zeitstempel liefert, sonst bleibt sie None statt
    geraten zu werden (Grundprinzip 1).
    """
    teilstrecken: list[Teilstrecke] = []
    vorherige_ankunft_sekunden: int | None = None
    for step in steps:
        dauer_minuten = round(step.get("duration", {}).get("value", 0) / 60)
        if step.get("travel_mode") == "TRANSIT":
            details = step.get("transit_details", {})
            linie_info = details.get("line", {})
            linie = linie_info.get("short_name") or linie_info.get("name")
            abfahrt_sekunden = details.get("departure_time", {}).get("value")
            ankunft_sekunden = details.get("arrival_time", {}).get("value")
            wartezeit_minuten = None
            if vorherige_ankunft_sekunden is not None and abfahrt_sekunden is not None:
                wartezeit_minuten = max(0, round((abfahrt_sekunden - vorherige_ankunft_sekunden) / 60))
            teilstrecken.append(
                Teilstrecke(
                    modus="TRANSIT",
                    linie=linie,
                    von=details.get("departure_stop", {}).get("name", "?"),
                    nach=details.get("arrival_stop", {}).get("name", "?"),
                    dauer_minuten=dauer_minuten,
                    wartezeit_minuten=wartezeit_minuten,
                )
            )
            vorherige_ankunft_sekunden = ankunft_sekunden
        elif dauer_minuten >= 1:
            # Fußwege (Anreise zur Haltestelle, Umstieg zwischen Bahnsteigen,
            # Weg vom Ziel-Bahnhof) – nur ab 1 Minute, um triviale Trippel-
            # schritte nicht aufzublähen.
            teilstrecken.append(
                Teilstrecke(modus="WALKING", linie=None, von="Fußweg", nach="Fußweg", dauer_minuten=dauer_minuten)
            )
    return teilstrecken


class GoogleMapsClient:
    """
    Echte Anbindung an die Google Maps Platform via `requests`. Wird aktiv,
    sobald ein Key in der `.env` hinterlegt und `MOCK_MODE=false` gesetzt ist
    (siehe `erzeuge_client`). Siehe Moduldoku für den Teststatus und bewusste
    Vereinfachungen.
    """

    BASIS_URL = "https://maps.googleapis.com/maps/api"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GoogleMapsClient benötigt einen API-Key (siehe .env: GOOGLE_MAPS_API_KEY).")
        self._api_key = api_key

    def suche_pois(self, ort: str, kategorien: list[str], radius_meter: int = 3000) -> list[POI]:
        """
        `radius_meter` (siehe aufbereitung.py `parameter_fuer_lokalen_
        transport`): der Umkreis richtet sich nach dem gewünschten lokalen
        Fortbewegungsmittel (F14) – zu Fuß erreichbare POIs liegen näher
        beieinander als mit dem Auto sinnvoll erreichbare (siehe Projekt-
        konversation).
        """
        lat, lng = self.geocode(ort)

        # Pro erkannter Kategorie eine eigene Nearby-Search (siehe Moduldoku).
        ergebnis_je_kategorie: list[list[dict]] = []
        for place_type in self._waehle_place_types(kategorien):
            parameter = {"location": f"{lat},{lng}", "radius": radius_meter, "type": place_type}
            if place_type == "gym" and self._ist_klettern_gesucht(kategorien):
                # "gym" ist der einzige verfügbare Google-Place-Type für Kletterhallen, deckt aber
                # GENAUSO normale Fitnessstudios ab (siehe _KATEGORIE_ALIASE-Kommentar) – ein Keyword
                # lenkt Googles eigene Relevanzsuche zusätzlich in Richtung Kletter-/Boulderhallen
                # (siehe Projektkonversation: "wieso wird mir da ein Gym rausgesucht?"). Ersetzt NICHT
                # die harte Namensprüfung in aufbereitung.py::_kategorie_passt_zu_praeferenz, verbessert
                # nur die TREFFERQUOTE der Suche selbst.
                parameter["keyword"] = "Kletterhalle Boulderhalle Klettern"
            antwort = self._get("place/nearbysearch/json", parameter)
            ergebnis_je_kategorie.append(antwort.get("results", []))

        # Kategorien im Round-Robin mischen statt hintereinanderzuhängen: sonst
        # würde eine spätere Kürzung (siehe vorschlaege.py) fast nur Treffer
        # der ERSTEN Kategorie behalten und z.B. Restaurants/Wellness wieder
        # verschwinden lassen, obwohl sie korrekt gefunden wurden.
        pois: list[POI] = []
        naechste_id = 1
        gesehene_namen: set[str] = set()
        for ergebnisse_dieser_runde in zip_longest(*ergebnis_je_kategorie):
            for ergebnis in ergebnisse_dieser_runde:
                if ergebnis is None:  # eine Kategorie hatte weniger Treffer als andere
                    continue
                name = ergebnis.get("name", "Unbekannter Ort")
                if name in gesehene_namen:  # Kategorien können sich überlappen (z.B. Hotel mit Spa)
                    continue
                gesehene_namen.add(name)

                standort = ergebnis["geometry"]["location"]
                haupttyp = next(iter(ergebnis.get("types", [])), _STANDARD_PLACE_TYPE)
                pois.append(
                    POI(
                        id=naechste_id,
                        name=name,
                        kategorie=haupttyp,
                        x=standort["lat"],
                        y=standort["lng"],
                        score=1.0,  # wird in der Datenaufbereitung per Präferenz-Matching neu gesetzt
                        required_time=_BESUCHSDAUER_JE_TYP_MINUTEN.get(haupttyp, _STANDARD_BESUCHSDAUER_MINUTEN),
                        opening=_STANDARD_OEFFNUNG_MINUTEN,
                        closing=_STANDARD_SCHLIESSUNG_MINUTEN,
                        place_id=ergebnis.get("place_id"),
                    )
                )
                naechste_id += 1
        return pois

    def suche_unterkuenfte(self, ort: str, praeferenz_text: str | None = None) -> list[Unterkunft]:
        """
        `praeferenz_text` (z.B. die Freitext-Antwort auf F15, siehe
        vorschlaege.py) wird als `keyword` an die Places Nearby Search
        übergeben (echter, dokumentierter Parameter für Text-Relevanz, siehe
        https://developers.google.com/maps/documentation/places/web-service/
        search-nearby) – Google sortiert die Treffer dann nach Relevanz zur
        genannten Präferenz statt nur nach Nähe/Prominenz (siehe Projekt-
        konversation: "die Top 5, die zu Budget/Vorstellungen/Lage passen").
        """
        lat, lng = self.geocode(ort)
        parameter = {"location": f"{lat},{lng}", "radius": 3000, "type": "lodging"}
        if praeferenz_text:
            parameter["keyword"] = praeferenz_text
        antwort = self._get("place/nearbysearch/json", parameter)
        unterkuenfte: list[Unterkunft] = []
        for i, ergebnis in enumerate(antwort.get("results", []), start=1):
            standort = ergebnis["geometry"]["location"]
            unterkuenfte.append(
                Unterkunft(
                    id=i,
                    name=ergebnis.get("name", "Unbekannte Unterkunft"),
                    x=standort["lat"],
                    y=standort["lng"],
                    preisniveau=ergebnis.get("price_level", 2),
                    # Places liefert kein Nachhaltigkeitszertifikat, siehe Moduldoku.
                    zertifiziert_nachhaltig=False,
                    place_id=ergebnis.get("place_id"),
                )
            )
        return unterkuenfte

    def distanzmatrix(self, orte: list[tuple[float, float]], modus: str = "walking") -> list[list[int]]:
        koordinaten = "|".join(f"{lat},{lng}" for lat, lng in orte)
        antwort = self._get(
            "distancematrix/json",
            {"origins": koordinaten, "destinations": koordinaten, "mode": modus},
        )
        matrix: list[list[int]] = []
        for zeile in antwort.get("rows", []):
            werte = []
            for element in zeile.get("elements", []):
                sekunden = element.get("duration", {}).get("value")
                werte.append(round(sekunden / 60) if sekunden is not None else -1)
            matrix.append(werte)
        return matrix

    def anfahrtszeiten_minuten(
        self, ursprung: tuple[float, float], ziele: list[tuple[float, float]], modus: str = "walking"
    ) -> list[int]:
        # EIN Ursprung -> N Ziele in einem einzigen Distance-Matrix-Aufruf
        # (statt `distanzmatrix`, das eine volle NxN-Matrix für dieselbe
        # Ortsliste berechnet) – für die Anfahrtsempfehlung je Aktivität
        # (siehe vorschlaege.py) würde die NxN-Variante bei vielen POIs
        # unnötig viele/teure Distance-Matrix-Elemente anfragen.
        if not ziele:
            return []
        origin = f"{ursprung[0]},{ursprung[1]}"
        destinations = "|".join(f"{lat},{lng}" for lat, lng in ziele)
        antwort = self._get(
            "distancematrix/json",
            {"origins": origin, "destinations": destinations, "mode": modus},
        )
        zeilen = antwort.get("rows", [])
        elemente = zeilen[0].get("elements", []) if zeilen else []
        dauern = []
        for element in elemente:
            sekunden = element.get("duration", {}).get("value")
            dauern.append(round(sekunden / 60) if sekunden is not None else -1)
        return dauern

    def reisealternativen(self, von: str, nach: str) -> list[ReiseAlternative]:
        alternativen: list[ReiseAlternative] = []
        # Bahn und Fernbus werden beide über mode=transit mit unterschiedlichem
        # transit_mode angefragt (Google Directions kennt keinen eigenen
        # "Fernbus"-Modus); Auto über mode=driving.
        konfiguration = [
            ("Bahn", {"mode": "transit", "transit_mode": "rail"}),
            ("Fernbus", {"mode": "transit", "transit_mode": "bus"}),
            ("Auto", {"mode": "driving"}),
        ]
        for verkehrsmittel, zusatzparameter in konfiguration:
            route = self._hole_route(von, nach, verkehrsmittel, zusatzparameter)
            if route is not None:
                alternativen.append(route)
        return alternativen

    def geocode(self, adresse: str) -> tuple[float, float]:
        antwort = self._get("geocode/json", {"address": adresse})
        ergebnisse = antwort.get("results", [])
        if not ergebnisse:
            raise ValueError(f"Geocoding lieferte keinen Treffer für '{adresse}'.")
        standort = ergebnisse[0]["geometry"]["location"]
        return standort["lat"], standort["lng"]

    def ist_barrierefrei(self, place_id: str | None) -> bool | None:
        """
        `wheelchair_accessible_entrance` (Boolean, Basic-Feldkategorie) steht
        NICHT in der Nearby-Search-Antwort (siehe suche_pois/suche_
        unterkuenfte), sondern nur über einen separaten Place-Details-Aufruf
        (verifiziert gegen https://developers.google.com/maps/documentation/
        places/web-service/legacy/details – Basic-Feld, kein zusätzliches SKU
        nötig). Daher bewusst NICHT für jeden Treffer automatisch abgefragt
        (zusätzliche Aufrufe/Kosten pro Kandidat), sondern nur, wenn der
        Nutzer Barrierefreiheit explizit als wichtig genannt hat (siehe
        vertraeglichkeit.py, schema.py `barrierefreiheit_wichtig`). Fehlt das
        Feld in der Antwort (Places hat dazu keine Angabe), wird `None`
        zurückgegeben statt eine Aussage zu erfinden (Grundprinzip 1).
        """
        if not place_id:
            return None
        antwort = self._get("place/details/json", {"place_id": place_id, "fields": "wheelchair_accessible_entrance"})
        return antwort.get("result", {}).get("wheelchair_accessible_entrance")

    # -- Interne Hilfsmethoden -----------------------------------------------

    def _hole_route(
        self, von: str, nach: str, verkehrsmittel: str, zusatzparameter: dict
    ) -> ReiseAlternative | None:
        parameter = {"origin": von, "destination": nach, **zusatzparameter}
        antwort = self._get("directions/json", parameter)
        routen = antwort.get("routes", [])
        if not routen or not routen[0].get("legs"):
            return None  # z.B. keine Bahnverbindung zwischen den Orten vorhanden

        leg = routen[0]["legs"][0]
        dauer_minuten = round(leg["duration"]["value"] / 60)
        distanz_km = leg["distance"]["value"] / 1000

        fahrpreis = leg.get("fare")
        if fahrpreis is not None:
            kosten_euro = fahrpreis["value"]  # von Google geliefert (selten verfügbar)
        else:
            modus = zusatzparameter.get("mode", "driving")
            kosten_euro = distanz_km * _KOSTEN_JE_KM_SCHAETZUNG_EURO.get(modus, 0.15)

        # Teilstrecken (Umstiege/Linien) nur bei Bahn/Fernbus sinnvoll: Google liefert bei
        # mode=driving KEINE Umstiege, sondern Abbiege-Kleinschritte ("links abbiegen", ...)
        # als `steps` – als "Fußweg"-Liste dargestellt wäre das Unsinn (live verifiziert).
        ist_transit = zusatzparameter.get("mode") == "transit"
        teilstrecken = _teilstrecken_aus_steps(leg.get("steps", [])) if ist_transit else []

        return ReiseAlternative(
            verkehrsmittel=verkehrsmittel,
            dauer_minuten=dauer_minuten,
            kosten_euro=kosten_euro,
            distanz_km=distanz_km,
            teilstrecken=teilstrecken,
        )

    @staticmethod
    def _waehle_place_types(kategorien: list[str]) -> list[str]:
        """
        Findet ALLE zu den Nutzerinteressen passenden Place Types (siehe
        `alias_place_types_fuer`) – NUR die, sonst nichts (siehe Projekt-
        konversation: "nur danach soll er auch suchen", kein "immer
        zusätzlich" mehr für Restaurant/Bar/Spa, siehe Moduldoku dort). Ohne
        JEDE erkannte Kategorie (z.B. völlig generische Aussage) Fallback auf
        `_STANDARD_PLACE_TYPE` ("tourist_attraction") statt einer leeren
        Suche – das ist ein Fallback für den Fall "nichts erkannt", NICHT
        eine zusätzliche Immer-Suche.
        """
        treffer: list[str] = []
        for kategorie in kategorien:
            for place_type in alias_place_types_fuer(kategorie):
                if place_type not in treffer:
                    treffer.append(place_type)
        if not treffer:
            treffer.append(_STANDARD_PLACE_TYPE)
        return treffer

    @staticmethod
    def _ist_klettern_gesucht(kategorien: list[str]) -> bool:
        """Erkennt, ob EINE der genannten Kategorien speziell auf Klettern/Bouldern zielt (siehe
        `suche_pois`: löst dann ein Keyword für die "gym"-Suche aus, statt generische Fitnessstudios
        gleichberechtigt mitzusuchen)."""
        schluesselwoerter = ("kletter", "boulder", "climbing")
        return any(any(sw in kategorie.lower() for sw in schluesselwoerter) for kategorie in kategorien)

    def _get(self, pfad: str, parameter: dict) -> dict:
        parameter = {"language": "de", **parameter}  # siehe Moduldoku: sonst Ortsnamen in Zufallssprache
        antwort = requests.get(f"{self.BASIS_URL}/{pfad}", params={**parameter, "key": self._api_key}, timeout=10)
        antwort.raise_for_status()
        daten = antwort.json()
        status = daten.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            fehlermeldung = daten.get("error_message", "")
            raise RuntimeError(f"Google-Maps-API-Fehler ({status}) bei '{pfad}': {fehlermeldung}")
        return daten


def erzeuge_client() -> MapsClient:
    """Wählt anhand der Konfiguration die Mock- oder die echte Implementierung."""
    if EINSTELLUNGEN.mock_modus or not EINSTELLUNGEN.google_maps_api_key:
        return MockGoogleMapsClient()
    return GoogleMapsClient(EINSTELLUNGEN.google_maps_api_key)

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
- `suche_pois` fragte ursprünglich nur EINE Google-Place-Type pro Aufruf ab
  (exaktes Mapping), dann (Zwischenstand) über eine feste Schlüsselwort ->
  Place-Type-Tabelle mehrere Typen gleichzeitig. BEIDE Zwischenstände
  presste Interessen auf einen von Googles ~100 FESTEN Place Types – bei
  "Klettern" z.B. auf "gym" (Google kennt keinen Kletter-Typ), was echte
  Kletterhallen mit gewöhnlichen Fitnessstudios vermischte, und versagte
  komplett bei allem außerhalb dieser festen Kategorien ("über Brücken
  spazieren gehen"). AKTUELL: `suche_pois` nutzt Places Text Search mit dem
  genannten Interesse WÖRTLICH als Suchtext (kein fester Typ mehr nötig) –
  siehe `doku/06_stage6_freitext_poi_suche/` für die volle Herleitung.
"""
from __future__ import annotations

import math
from dataclasses import replace
from itertools import zip_longest
from typing import Protocol

import requests

from src.api import mock_data
from src.api.typen import POI, ReiseAlternative, Teilstrecke, Unterkunft
from src.config import EINSTELLUNGEN


class MapsClient(Protocol):
    def suche_pois(self, ort: str, interessen: list[str], radius_meter: int = 3000) -> list[POI]: ...
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

    def suche_pois(self, ort: str, interessen: list[str], radius_meter: int = 3000) -> list[POI]:
        """
        Bildet dieselbe "eine Suche pro Interesse, Treffer tragen das Interesse"-Struktur wie
        `GoogleMapsClient.suche_pois` nach (siehe dort), nur gegen die statischen Beispieldaten statt
        einer echten Text Search: ein Mock-POI "passt", wenn sein (deutscher Bucket-)`kategorie`-Wert
        Teilstring-Überschneidung mit dem gesuchten Interesse hat (z.B. Interesse "Kultur" <->
        Mock-Kategorie "kultur"). `radius_meter` wird ignoriert (keine echte Umkreissuche im
        Mock-Modus).
        """
        treffer: list[POI] = []
        for interesse in interessen:
            interesse_klein = interesse.lower()
            for poi in mock_data.BEISPIEL_POIS:
                if poi.kategorie.lower() in interesse_klein or interesse_klein in poi.kategorie.lower():
                    treffer.append(replace(poi, nutzerinteresse=interesse))
        return treffer

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


# ENTFERNT (siehe Projektkonversation, "ich möchte klettern, nicht ins Gym"): die frühere feste
# Schlüsselwort -> Google-Place-Type-Tabelle (`_KATEGORIE_ALIASE`) presste jedes Interesse zwangsweise
# auf einen von Googles ~100 FESTEN Place Types – strukturell zu grob/teils falsch (z.B. "Klettern"
# -> "gym"), UND unbrauchbar für alles, was sich keiner dieser Kategorien zuordnen lässt. Ersetzt durch
# `suche_pois`s Google Places Text Search (Freitext-Query pro Interesse, siehe dort) – die einzigen
# noch echten Places-TYP-Konstanten unten (`_BESUCHSDAUER_JE_TYP_MINUTEN`, `_MINDEST_TAGESZEIT_
# MINUTEN_JE_TYP`) lesen weiterhin Googles EIGENEN zurückgelieferten Typ, ordnen aber nichts mehr selbst zu.


# Fallback für `haupttyp` (siehe `suche_pois`), falls eine Text-Search-Antwort ausnahmsweise KEIN
# `types`-Array liefert – reiner Sicherheitsnetz-Wert für die Besuchsdauer-/Tageszeit-Heuristiken
# unten, beeinflusst NICHT, wonach gesucht wird (das steuert allein `interessen`, siehe suche_pois).
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

    def suche_pois(self, ort: str, interessen: list[str], radius_meter: int = 3000) -> list[POI]:
        """
        Sucht für JEDES genannte Interesse eine eigene Google Places Text
        Search (`place/textsearch/json`, `query="{interesse} in {ort}"`,
        `location`/`radius` als Ortsbezug).

        BEHOBENER BUG (siehe Projektkonversation: "ich möchte klettern, nicht
        ins Gym – das darf auf gar keinen Fall passieren"): Die Vorgänger-
        Version presste jedes genannte Interesse über eine selbst gepflegte
        Schlüsselwort-Tabelle (`_KATEGORIE_ALIASE`, ENTFERNT) zwangsweise auf
        einen von Googles ~100 FESTEN Place Types (Nearby Search verlangt
        genau so einen Typ) – z.B. "Klettern" -> "gym", obwohl Google dafür
        gar keinen passenden Typ kennt. Das lieferte strukturell falsche
        Ergebnisse (normale Fitnessstudios statt Kletterhallen) UND versagte
        komplett bei allem, was sich keiner der ~100 Kategorien zuordnen
        lässt (z.B. "über Brücken spazieren gehen", "eine Runde laufen
        gehen"). Places Text Search verlangt dagegen KEINEN festen Typ,
        sondern akzeptiert beliebigen Freitext als `query` – Googles eigene
        Suchrelevanz übernimmt die Interpretation, statt dass wir selbst
        (falsch) raten müssen, welcher feste Typ am ehesten passt.

        Jeder Treffer trägt in `POI.nutzerinteresse` GENAU den Text, für den
        er gefunden wurde – das Präferenz-Matching (aufbereitung.py
        `berechne_poi_score`) muss dadurch nichts mehr nachträglich zuordnen,
        ein Treffer aus der Suche "Klettern" IST per Konstruktion ein
        Klettern-Treffer.

        `radius_meter` (siehe aufbereitung.py `parameter_fuer_lokalen_
        transport`): der Umkreis richtet sich nach dem gewünschten lokalen
        Fortbewegungsmittel (F14) – zu Fuß erreichbare POIs liegen näher
        beieinander als mit dem Auto sinnvoll erreichbare. Bei Text Search
        (anders als Nearby Search) ist das nur ein WEICHER Bezug, kein
        harter Ausschluss (Google-Dokumentation) – für seltene/verstreute
        Interessen (z.B. "über Brücken spazieren gehen") ist das
        erwünscht, statt bei null strengen Treffern leer zu bleiben.
        """
        if not interessen:
            return []
        lat, lng = self.geocode(ort)

        # Pro genanntem Interesse eine eigene Text Search (siehe Moduldoku).
        ergebnis_je_interesse: list[list[dict]] = []
        for interesse in interessen:
            parameter = {"query": f"{interesse} in {ort}", "location": f"{lat},{lng}", "radius": radius_meter}
            antwort = self._get("place/textsearch/json", parameter)
            ergebnis_je_interesse.append(antwort.get("results", []))

        # Interessen im Round-Robin mischen statt hintereinanderzuhängen: sonst
        # würde eine spätere Kürzung (siehe vorschlaege.py) fast nur Treffer
        # des ERSTEN Interesses behalten und andere genannte Interessen
        # verdrängen, obwohl sie korrekt gefunden wurden.
        pois: list[POI] = []
        naechste_id = 1
        gesehene_namen: set[str] = set()
        for runde in zip_longest(*ergebnis_je_interesse):
            for interesse, ergebnis in zip(interessen, runde):
                if ergebnis is None:  # dieses Interesse hatte in dieser Runde keinen weiteren Treffer
                    continue
                name = ergebnis.get("name", "Unbekannter Ort")
                if name in gesehene_namen:  # Interessen können sich überlappen (z.B. Park bei "Natur" + "Laufen")
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
                        nutzerinteresse=interesse,
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

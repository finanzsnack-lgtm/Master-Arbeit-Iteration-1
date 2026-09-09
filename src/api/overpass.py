"""
Zusatz-Datenquelle für Aktivitäten, die Google Places strukturell nicht
sinnvoll abdeckt (siehe Projektkonversation: "Aktivitätsurlaube müssen
vernünftig eingeschätzt werden" – Klettern, Wandern mit Schwierigkeitsgrad,
Skifahren, Tauchen, ...). Google Places kennt für diese Aktivitäten keine
brauchbaren Place Types (siehe google_maps.py-Kommentar bei "klettern");
OpenStreetMap taggt sie dagegen strukturiert (`sport=climbing`,
`route=hiking` + `sac_scale`, `piste:type`+`piste:difficulty`, ...) und ist
über die kostenlose, schlüssel-freie Overpass API abfragbar.

WICHTIG (CLAUDE.md, Grundprinzip 1): Diese Anbindung wird NUR aufgerufen,
wenn der LLM-Agent (siehe agent_tools.py `hole_api_daten`, Argument
`spezialrecherche_aktivitaeten`) eine genannte Aktivität als recherche-
bedürftig einstuft – das LLM entscheidet NUR, OB nachgefragt/nachrecherchiert
wird, nicht WAS als Ergebnis geliefert wird. Die eigentliche Abfrage bleibt
regelbasierter, deterministischer Code ohne LLM-Beteiligung, exakt wie bei
`google_maps.py`/`vorschlaege.py`.

STATUS: gegen die echte Overpass-API verifiziert (siehe Projektkonversation:
manueller Testabruf lieferte reale Kletterorte samt Tags rund um München).
Zwei dabei behobene Stolpersteine:
- Der Server lehnt den Standard-User-Agent von `requests` mit "406 Not
  Acceptable" ab – `_HEADERS` setzt deshalb einen eigenen.
- OSM-Schwierigkeitsgrad-Tags sind uneinheitlich (z.B. Klettern meist
  `climbing:grade:uiaa*`, seltener `:french`) – `_AKTIVITAET_ALIASE` prüft
  daher mehrere Tag-Kandidaten der Reihe nach statt nur einen.
Öffentlicher Endpunkt ohne Authentifizierung, aber mit Fair-Use-Rate-Limit –
siehe https://wiki.openstreetmap.org/wiki/Overpass_API.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

import requests

from src.api import mock_data
from src.api.typen import POI
from src.config import EINSTELLUNGEN

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Ohne eigenen User-Agent lehnt der Server mit "406 Not Acceptable" ab (siehe
# Moduldoku) – der Overpass-Nutzungshinweis empfiehlt ohnehin, Anwendungen
# über den User-Agent zu identifizieren statt anonym als "python-requests".
_HEADERS = {"User-Agent": "reisebot-prototyp/1.0 (Masterarbeit, siehe CLAUDE.md)"}

# Umkreis der Nearby-Suche um den geokodierten Zielort (Meter). Deutlich
# größer als bei Google Places (google_maps.py: 3000m), weil Kletterfelsen/
# Skigebiete/Tauchspots typischerweise außerhalb der Stadt liegen.
_SUCHRADIUS_METER = 30_000

# Schlüsselwort -> (Overpass-Tag-Filter, OSM-Tag-Kandidaten für den
# Schwierigkeitsgrad, der Reihe nach geprüft – siehe Moduldoku: OSM tagged
# uneinheitlich). Teilstring-Suche, da Nutzerantworten als Freitext über das
# LLM kommen. ANDERS als die (entfernte) google_maps.py::_KATEGORIE_ALIASE
# bleibt diese Tabelle bestehen: OSM selbst tagged nur eine FESTE, uneinheit-
# liche Menge an Aktivitäts-/Schwierigkeitsgrad-Schlüsseln – hier gibt es
# keine freie Textsuche, die das ersetzen könnte (Overpass ist eine reine
# strukturierte Tag-Datenbank, kein Textsuchindex wie Places). Leeres Tupel,
# wenn OSM dafür keine verbreitete Konvention hat – dann bleibt
# POI.schwierigkeitsgrad None statt etwas zu erfinden (Grundprinzip 1).
_AKTIVITAET_ALIASE: dict[str, tuple[str, tuple[str, ...]]] = {
    "klettern": ('"sport"="climbing"', ("climbing:grade:uiaa", "climbing:grade:uiaa:min", "climbing:grade:french")),
    "kletterhalle": ('"sport"="climbing"', ("climbing:grade:uiaa", "climbing:grade:uiaa:min", "climbing:grade:french")),
    "bouldern": ('"sport"="climbing"', ("climbing:grade:uiaa", "climbing:grade:uiaa:min", "climbing:grade:french")),
    "climbing": ('"sport"="climbing"', ("climbing:grade:uiaa", "climbing:grade:uiaa:min", "climbing:grade:french")),
    "wandern": ('"route"="hiking"', ("sac_scale",)),
    "hiking": ('"route"="hiking"', ("sac_scale",)),
    "trekking": ('"route"="hiking"', ("sac_scale",)),
    "skifahren": ('"piste:type"="downhill"', ("piste:difficulty",)),
    "ski": ('"piste:type"="downhill"', ("piste:difficulty",)),
    "snowboard": ('"piste:type"="downhill"', ("piste:difficulty",)),
    "skitour": ('"piste:type"="skitour"', ("piste:difficulty",)),
    "tauchen": ('"sport"="scuba_diving"', ()),
    "diving": ('"sport"="scuba_diving"', ()),
    "surfen": ('"sport"="surfing"', ()),
    "mountainbike": ('"route"="mtb"', ("mtb:scale",)),
    "radfahren": ('"route"="bicycle"', ()),
}

# Grobe, literaturunabhängige Annahme der Besuchsdauer (Minuten) – analog zu
# google_maps.py::_STANDARD_BESUCHSDAUER_MINUTEN, aber höher, da diese
# Aktivitäten typischerweise einen Groß-/Ganztagesausflug darstellen.
_STANDARD_BESUCHSDAUER_MINUTEN = 180
_STANDARD_OEFFNUNG_MINUTEN = 0
_STANDARD_SCHLIESSUNG_MINUTEN = 22 * 60


class SpezialAktivitaetenClient(Protocol):
    def suche_spezial_pois(self, koordinaten: tuple[float, float], aktivitaet: str) -> list[POI]: ...


class MockOverpassClient:
    """Liefert deterministische Beispieldaten aus `mock_data.py` (siehe CLAUDE.md: Mock-Modus)."""

    def suche_spezial_pois(self, koordinaten: tuple[float, float], aktivitaet: str) -> list[POI]:
        treffer = _waehle_alias(aktivitaet)
        if treffer is None:
            return []
        return [
            replace(poi, nutzerinteresse=aktivitaet)
            for poi in mock_data.BEISPIEL_SPEZIAL_POIS
            if poi.kategorie == _kategorie_fuer(aktivitaet)
        ]


class OverpassClient:
    """Echte Anbindung an die Overpass API via `requests` (kein Key nötig)."""

    def suche_spezial_pois(self, koordinaten: tuple[float, float], aktivitaet: str) -> list[POI]:
        treffer = _waehle_alias(aktivitaet)
        if treffer is None:
            return []
        tag_filter, schwierigkeits_tags = treffer
        lat, lng = koordinaten

        abfrage = (
            "[out:json][timeout:25];\n"
            "(\n"
            f"  node[{tag_filter}](around:{_SUCHRADIUS_METER},{lat},{lng});\n"
            f"  way[{tag_filter}](around:{_SUCHRADIUS_METER},{lat},{lng});\n"
            ");\n"
            "out center tags;"
        )
        try:
            antwort = requests.post(_OVERPASS_URL, data={"data": abfrage}, headers=_HEADERS, timeout=30)
            antwort.raise_for_status()
        except requests.exceptions.RequestException:
            # Der öffentliche Overpass-Server ist ein geteilter, rate-limitierter Dienst und antwortet
            # unter Last auch mal mit 504/Timeout (live beobachtet, siehe Projektkonversation) – das darf
            # NICHT die gesamte Planung crashen. Ehrlicher Fallback: keine Spezial-POIs für diese
            # Aktivität, Places-Ergebnisse (falls vorhanden) bleiben trotzdem erhalten (siehe
            # poi_sammlung.py). KEIN erfundener Ersatz-Treffer (Grundprinzip 1).
            return []
        elemente = antwort.json().get("elements", [])

        pois: list[POI] = []
        for i, element in enumerate(elemente, start=1):
            tags = element.get("tags", {})
            name = tags.get("name")
            if not name:
                continue  # unbenannte OSM-Elemente sind für einen Reisevorschlag nicht nutzbar
            if element["type"] == "node":
                lat_wert, lng_wert = element["lat"], element["lon"]
            else:  # way/relation: Overpass liefert bei "out center" einen Mittelpunkt statt Einzelkoordinaten
                mitte = element.get("center")
                if mitte is None:
                    continue
                lat_wert, lng_wert = mitte["lat"], mitte["lon"]

            pois.append(
                POI(
                    id=i,
                    name=name,
                    kategorie=_kategorie_fuer(aktivitaet),
                    x=lat_wert,
                    y=lng_wert,
                    score=1.0,  # wird wie bei Places erst in der Datenaufbereitung per Präferenz-Matching gesetzt
                    required_time=_STANDARD_BESUCHSDAUER_MINUTEN,
                    opening=_STANDARD_OEFFNUNG_MINUTEN,
                    closing=_STANDARD_SCHLIESSUNG_MINUTEN,
                    quelle="osm_overpass",
                    schwierigkeitsgrad=_erster_vorhandener_tag(tags, schwierigkeits_tags),
                    nutzerinteresse=aktivitaet,
                )
            )
        return pois


def _erster_vorhandener_tag(tags: dict, kandidaten: tuple[str, ...]) -> str | None:
    """Erster der Reihe nach geprüfte OSM-Tag, der in `tags` tatsächlich vorkommt (siehe Moduldoku: uneinheitliche Konventionen)."""
    for kandidat in kandidaten:
        if kandidat in tags:
            return tags[kandidat]
    return None


def _waehle_alias(aktivitaet: str) -> tuple[str, tuple[str, ...]] | None:
    aktivitaet_klein = aktivitaet.lower()
    for schluesselwort, wert in _AKTIVITAET_ALIASE.items():
        if schluesselwort in aktivitaet_klein:
            return wert
    return None


def _kategorie_fuer(aktivitaet: str) -> str:
    """Kurzform der erkannten Aktivität als POI.kategorie (für Anzeige/Scoring)."""
    aktivitaet_klein = aktivitaet.lower()
    for schluesselwort in _AKTIVITAET_ALIASE:
        if schluesselwort in aktivitaet_klein:
            return schluesselwort
    return "spezialaktivitaet"


def erzeuge_overpass_client() -> SpezialAktivitaetenClient:
    """Wählt anhand der Konfiguration die Mock- oder die echte Implementierung (siehe google_maps.py::erzeuge_client)."""
    if EINSTELLUNGEN.mock_modus:
        return MockOverpassClient()
    return OverpassClient()

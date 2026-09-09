"""Tests für src/datenaufbereitung/poi_sammlung.py (Google Places + optionale Overpass-Spezialrecherche)."""
from src.api.overpass import MockOverpassClient
from src.api.typen import POI
from src.datenaufbereitung.poi_sammlung import sammle_pois


class _FakeMapsClient:
    """Minimaler Stub: nur die von sammle_pois genutzten Methoden."""

    def __init__(self, pois: list[POI]):
        self._pois = pois

    def suche_pois(self, ort: str, kategorien: list[str], radius_meter: int = 3000, ernaehrung_einschraenkungen: list[str] | None = None) -> list[POI]:
        return list(self._pois)

    def geocode(self, adresse: str) -> tuple[float, float]:
        return (48.0, 11.0)


def test_sammle_pois_ruft_overpass_nicht_auf_ohne_spezialrecherche():
    client = _FakeMapsClient([POI(id=1, name="Museum", kategorie="museum", x=1, y=1, score=1.0,
                                   required_time=60, opening=0, closing=600)])
    ergebnis = sammle_pois("Rom", ["Kultur"], [], client)
    assert [poi.name for poi in ergebnis] == ["Museum"]


def test_sammle_pois_ergaenzt_overpass_treffer_bei_spezialrecherche():
    client = _FakeMapsClient([POI(id=1, name="Museum", kategorie="museum", x=1, y=1, score=1.0,
                                   required_time=60, opening=0, closing=600)])
    ergebnis = sammle_pois("Rom", ["Kultur", "Klettern"], ["Klettern"], client, overpass_client=MockOverpassClient())
    namen = [poi.name for poi in ergebnis]
    assert "Museum" in namen
    assert "Klettergarten Musterfelsen" in namen
    treffer = next(poi for poi in ergebnis if poi.name == "Klettergarten Musterfelsen")
    assert treffer.quelle == "osm_overpass"
    assert treffer.schwierigkeitsgrad == "6a"


def test_sammle_pois_dedupliziert_gleichnamige_treffer():
    # Places und Overpass könnten denselben Ort liefern (z.B. Kletterhalle als "gym").
    client = _FakeMapsClient([POI(id=1, name="Klettergarten Musterfelsen", kategorie="gym", x=1, y=1,
                                   score=1.0, required_time=60, opening=0, closing=600)])
    ergebnis = sammle_pois("Rom", ["Klettern"], ["Klettern"], client, overpass_client=MockOverpassClient())
    namen = [poi.name for poi in ergebnis]
    assert namen.count("Klettergarten Musterfelsen") == 1

"""Tests für src/pipeline.py – bislang nur die reinen, clientlosen Hilfsfunktionen (die
gesamte plane_reise() wird weiterhin nur indirekt über main.py/chat.py live geprüft, siehe
tests/conftest.py)."""
from src.api.google_maps import ist_lernaktivitaet_bezogenes_interesse, ist_markt_bezogenes_interesse, ist_tour_bezogenes_interesse
from src.api.typen import POI, ReiseAlternative
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative
from src.pipeline import (
    _nur_bestaetigte_verkehrsmittel,
    _trenne_beispielrestaurants_ab,
    _trenne_markt_beispiele_ab,
    _trenne_sonderkategorie_ab,
)

# `_trenne_sonderkategorie_ab` prüft ein Prädikat gegen den GANZEN POI (siehe pipeline.py) – die
# Erkennungsfunktionen selbst prüfen nur den `nutzerinteresse`-Text, hier entsprechend gekapselt.
def _ist_tour(poi: POI) -> bool:
    return bool(poi.nutzerinteresse) and ist_tour_bezogenes_interesse(poi.nutzerinteresse)


def _ist_lernaktivitaet(poi: POI) -> bool:
    return bool(poi.nutzerinteresse) and ist_lernaktivitaet_bezogenes_interesse(poi.nutzerinteresse)

_BAHN = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    co2_kg=9.5, score=0.1,
)
_AUTO = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=250, kosten_euro=120, distanz_km=500),
    co2_kg=25.0, score=0.5,
)
_FERNBUS = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Fernbus", dauer_minuten=450, kosten_euro=45, distanz_km=500),
    co2_kg=12.0, score=0.3,
)
_ALLE = [_BAHN, _AUTO, _FERNBUS]  # bewerte_alternativen sortiert nach Score, Bahn hier "objektiv beste"


def test_nur_bestaetigte_verkehrsmittel_respektiert_explizite_wahl():
    # Regression (siehe Projektkonversation: "ich habe Auto bestätigt, aber am Ende steht Bahn –
    # das darf nie passieren"): obwohl Bahn den besten Score hat, muss bei bestätigtem "Auto" NUR
    # Auto übrig bleiben.
    ergebnis = _nur_bestaetigte_verkehrsmittel(_ALLE, ["Auto"])
    assert [b.alternative.verkehrsmittel for b in ergebnis] == ["Auto"]


def test_nur_bestaetigte_verkehrsmittel_erkennt_freitext():
    ergebnis = _nur_bestaetigte_verkehrsmittel(_ALLE, ["am liebsten mit dem Fernbus"])
    assert [b.alternative.verkehrsmittel for b in ergebnis] == ["Fernbus"]


def test_nur_bestaetigte_verkehrsmittel_ohne_treffer_faellt_auf_alle_zurueck():
    # Kein Absturz/keine leere Auswahl bei unklarem Freitext – lieber die volle (weiterhin
    # objektiv bewertete) Liste behalten als eine erfundene Einschränkung.
    ergebnis = _nur_bestaetigte_verkehrsmittel(_ALLE, ["bin mir noch unsicher"])
    assert ergebnis == _ALLE


def test_nur_bestaetigte_verkehrsmittel_mehrere_genannte_bleiben_erhalten():
    ergebnis = _nur_bestaetigte_verkehrsmittel(_ALLE, ["Auto oder Fernbus, beides ok"])
    assert {b.alternative.verkehrsmittel for b in ergebnis} == {"Auto", "Fernbus"}


def _poi(id: int, name: str, x: float, y: float, besuchsklasse: str | None) -> POI:
    return POI(
        id=id, name=name, kategorie="restaurant" if besuchsklasse == "mahlzeit" else "museum",
        x=x, y=y, score=1.0, required_time=60, opening=0, closing=600, besuchsklasse=besuchsklasse,
    )


def test_trenne_beispielrestaurants_ab_entfernt_mahlzeit_pois_aus_der_kandidatenliste():
    # "ich möchte nicht, dass das als gesondertes POI gesehen wird" (Nutzerwunsch, revidiert):
    # Restaurants dürfen NICHT mehr in der Liste landen, die an Optimierung 1 geht.
    museum = _poi(1, "Museum", 0.0, 0.0, None)
    restaurant = _poi(2, "Restaurant", 0.0, 0.001, "mahlzeit")
    uebrige, beispielrestaurants = _trenne_beispielrestaurants_ab([museum, restaurant], depot_koordinaten=(0.0, 0.0))
    assert uebrige == [museum]
    assert [p.name for p in beispielrestaurants] == ["Restaurant"]


def test_trenne_beispielrestaurants_ab_laesst_cafe_unangetastet():
    cafe = _poi(1, "Café", 0.0, 0.0, "kaffee")
    uebrige, beispielrestaurants = _trenne_beispielrestaurants_ab([cafe], depot_koordinaten=(0.0, 0.0))
    assert uebrige == [cafe]
    assert beispielrestaurants == []


def test_trenne_beispielrestaurants_ab_erfasst_auch_bars():
    # Ergänzt für lokalen Kontakt (F19, Rückfrage-Ergebnis): eine "urige Kneipe" landet bei Google
    # häufig unter dem Typ "bar", nicht "restaurant" – ohne diese Ergänzung würden genau die dafür
    # typischen Treffer nicht erscheinen.
    bar = _poi(2, "Kneipe", 0.0, 0.0, "bar")
    uebrige, beispielrestaurants = _trenne_beispielrestaurants_ab([bar], depot_koordinaten=(0.0, 0.0))
    assert uebrige == []
    assert [p.name for p in beispielrestaurants] == ["Kneipe"]


def test_trenne_beispielrestaurants_ab_sortiert_nach_entfernung_zur_unterkunft():
    nah = _poi(1, "Nahes Restaurant", 0.0, 0.001, "mahlzeit")
    fern = _poi(2, "Fernes Restaurant", 0.0, 0.05, "mahlzeit")
    _, beispielrestaurants = _trenne_beispielrestaurants_ab([fern, nah], depot_koordinaten=(0.0, 0.0))
    assert [p.name for p in beispielrestaurants] == ["Nahes Restaurant", "Fernes Restaurant"]


class _FakeClient:
    """Minimaler Fake für `client.ist_barrierefrei(place_id)` (siehe vertraeglichkeit.py-Tests für
    dasselbe Muster)."""

    def __init__(self, status_je_place_id: dict[str, bool | None]):
        self._status = status_je_place_id

    def ist_barrierefrei(self, place_id):
        return self._status.get(place_id)


def _sonder_poi(id: int, name: str, x: float, y: float, nutzerinteresse: str, place_id: str | None = None) -> POI:
    return POI(
        id=id, name=name, kategorie="travel_agency", x=x, y=y, score=1.0, required_time=120,
        opening=0, closing=600, nutzerinteresse=nutzerinteresse, place_id=place_id,
    )


def _tour_poi(id: int, name: str, x: float, y: float, place_id: str | None = None) -> POI:
    return _sonder_poi(id, name, x, y, "geführte Tour", place_id)


def test_trenne_sonderkategorie_ab_entfernt_passende_pois_aus_der_kandidatenliste():
    museum = _poi(1, "Museum", 0.0, 0.0, None)
    tour = _tour_poi(2, "Stadtführung", 0.0, 0.001)
    uebrige, tour_beispiele = _trenne_sonderkategorie_ab(
        [museum, tour], depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe=None,
        client=_FakeClient({}), gehoert_zur_kategorie=_ist_tour,
    )
    assert uebrige == [museum]
    assert [p.name for p in tour_beispiele] == ["Stadtführung"]


def test_trenne_sonderkategorie_ab_ohne_treffer_leer():
    museum = _poi(1, "Museum", 0.0, 0.0, None)
    uebrige, tour_beispiele = _trenne_sonderkategorie_ab(
        [museum], depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe=None,
        client=_FakeClient({}), gehoert_zur_kategorie=_ist_tour,
    )
    assert uebrige == [museum]
    assert tour_beispiele == []


def test_trenne_sonderkategorie_ab_stufe_leicht_prueft_nicht_und_nimmt_naechste_drei():
    touren = [_tour_poi(i, f"Tour {i}", 0.0, i * 0.001) for i in range(1, 6)]  # 5 Kandidaten
    _, tour_beispiele = _trenne_sonderkategorie_ab(
        touren, depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe="leicht",
        client=_FakeClient({}), gehoert_zur_kategorie=_ist_tour,
    )
    assert [p.name for p in tour_beispiele] == ["Tour 1", "Tour 2", "Tour 3"]  # nächste drei, ungeprüft


def test_trenne_sonderkategorie_ab_stufe_stark_verlangt_alle_bestaetigt_barrierefrei():
    touren = [_tour_poi(i, f"Tour {i}", 0.0, i * 0.001, place_id=f"p{i}") for i in range(1, 6)]
    # Nur Tour 2 und Tour 4 sind eindeutig bestätigt barrierefrei, der Rest unbekannt/nicht bestätigt.
    client = _FakeClient({"p2": True, "p4": True})
    _, tour_beispiele = _trenne_sonderkategorie_ab(
        touren, depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe="stark",
        client=client, gehoert_zur_kategorie=_ist_tour,
    )
    # Weniger als 3 werden gezeigt, statt eine nicht bestätigte Tour zu erfinden (Grundprinzip 1).
    assert {p.name for p in tour_beispiele} == {"Tour 2", "Tour 4"}


def test_trenne_sonderkategorie_ab_stufe_mittel_verlangt_mindestens_haelfte_barrierefrei():
    touren = [_tour_poi(i, f"Tour {i}", 0.0, i * 0.001, place_id=f"p{i}") for i in range(1, 6)]
    client = _FakeClient({"p1": True})  # nur die nächste ist bestätigt barrierefrei
    _, tour_beispiele = _trenne_sonderkategorie_ab(
        touren, depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe="mittel",
        client=client, gehoert_zur_kategorie=_ist_tour,
    )
    assert len(tour_beispiele) == 3
    barrierefreie = [p for p in tour_beispiele if p.name == "Tour 1"]
    assert len(barrierefreie) == 1  # die eine bestätigte ist dabei, Rest zur Auffüllung erlaubt


def test_trenne_sonderkategorie_ab_pool_begrenzt_barrierefreiheits_abfragen():
    # Rückfrage-Ergebnis nach Live-Vorfall: NICHT jeder Roh-Treffer wird einzeln geprüft, nur der
    # nächstgelegene, begrenzte Pool.
    touren = [_tour_poi(i, f"Tour {i}", 0.0, i * 0.001, place_id=f"p{i}") for i in range(1, 21)]  # 20 Treffer
    abgefragte_ids: list[str] = []

    class _ZaehlenderClient:
        def ist_barrierefrei(self, place_id):
            abgefragte_ids.append(place_id)
            return True

    _trenne_sonderkategorie_ab(
        touren, depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe="stark",
        client=_ZaehlenderClient(), gehoert_zur_kategorie=_ist_tour,
    )
    assert len(abgefragte_ids) <= 8  # _SONDERKATEGORIE_KANDIDATEN_POOL, NICHT alle 20 Roh-Treffer


def test_trenne_sonderkategorie_ab_erkennt_lernaktivitaeten_getrennt_von_touren():
    kochkurs = _sonder_poi(1, "Kochkurs Wien", 0.0, 0.0, "Kochkurs")
    tour = _tour_poi(2, "Stadtführung", 0.0, 0.001)
    uebrige, lernaktivitaet_beispiele = _trenne_sonderkategorie_ab(
        [kochkurs, tour], depot_koordinaten=(0.0, 0.0), mobilitaetseinschraenkung_stufe=None,
        client=_FakeClient({}), gehoert_zur_kategorie=_ist_lernaktivitaet,
    )
    # Die Tour bleibt übrig – sie gehört NICHT zur Lernaktivitäts-Kategorie, wird hier also nicht abgetrennt.
    assert [p.name for p in uebrige] == ["Stadtführung"]
    assert [p.name for p in lernaktivitaet_beispiele] == ["Kochkurs Wien"]


def _markt_poi(id: int, name: str, x: float, y: float) -> POI:
    return _sonder_poi(id, name, x, y, "Wochenmarkt")


def _cafe_poi(id: int, name: str, x: float, y: float) -> POI:
    return POI(
        id=id, name=name, kategorie="cafe", x=x, y=y, score=1.0, required_time=45,
        opening=0, closing=600, besuchsklasse="kaffee",
    )


def test_trenne_markt_beispiele_ab_erfasst_maerkte_und_cafes():
    museum = _poi(1, "Museum", 0.0, 0.0, None)
    markt = _markt_poi(2, "Wochenmarkt Zentrum", 0.0, 0.001)
    cafe = _cafe_poi(3, "Café Central", 0.0, 0.002)
    uebrige, markt_beispiele = _trenne_markt_beispiele_ab([museum, markt, cafe], depot_koordinaten=(0.0, 0.0))
    assert uebrige == [museum]
    assert {p.name for p in markt_beispiele} == {"Wochenmarkt Zentrum", "Café Central"}


def test_trenne_markt_beispiele_ab_sortiert_nach_entfernung():
    fern = _markt_poi(1, "Ferner Markt", 0.0, 0.05)
    nah = _markt_poi(2, "Naher Markt", 0.0, 0.001)
    _, markt_beispiele = _trenne_markt_beispiele_ab([fern, nah], depot_koordinaten=(0.0, 0.0))
    assert [p.name for p in markt_beispiele] == ["Naher Markt", "Ferner Markt"]


def test_ist_markt_bezogenes_interesse_erkennt_wochenmarkt():
    assert ist_markt_bezogenes_interesse("Wochenmarkt") is True
    assert ist_markt_bezogenes_interesse("Flohmarkt") is True
    assert ist_markt_bezogenes_interesse("Museum") is False

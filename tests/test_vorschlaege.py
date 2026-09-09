"""Tests für den Datenabruf der Typ-C-Fragen (src/fragekatalog/vorschlaege.py)."""
from src.api.typen import POI, ReiseAlternative, Unterkunft
from src.datenaufbereitung.aufbereitung import max_pois_fuer_reise
from src.fragekatalog.katalog import FRAGEKATALOG
from src.fragekatalog.schema import ReiseAnfrage
from src.fragekatalog.vorschlaege import hole_echte_daten_fuer_vorschlag, suche_unterkunft, suche_verleih_nahe_unterkunft

_FRAGE_AKTIVITAETEN = next(f for f in FRAGEKATALOG if f.feld == "aktivitaeten_interessen")
_FRAGE_VERKEHRSMITTEL = next(f for f in FRAGEKATALOG if f.feld == "verkehrsmittel_praeferenz")


class _FakeClient:
    """Liefert eine konfigurierbare Anzahl POIs, um Warnschwelle und Kappung zu testen."""

    def __init__(self, anzahl_pois: int, anfahrtszeiten_je_modus: dict[str, int] | None = None):
        self._anzahl_pois = anzahl_pois
        # {modus: dauer_minuten} für ALLE angefragten Ziele (reicht für die Tests hier).
        self._anfahrtszeiten_je_modus = anfahrtszeiten_je_modus or {}

    def suche_pois(self, ort, kategorien, radius_meter=3000, ernaehrung_einschraenkungen=None):
        return [
            POI(id=i, name=f"POI {i}", kategorie="tourist_attraction", x=0.0, y=0.0,
                score=1.0, required_time=60, opening=0, closing=600)
            for i in range(self._anzahl_pois)
        ]

    def geocode(self, ort):
        return (0.0, 0.0)

    def anfahrtszeiten_minuten(self, ursprung, ziele, modus="walking"):
        dauer = self._anfahrtszeiten_je_modus.get(modus, -1)
        return [dauer for _ in ziele]


def test_hole_echte_daten_ohne_warnhinweis_wenn_wenige_treffer():
    # 8 Rohtreffer, Warnschwelle liegt bei 10 -> keine Warnung, einfache Liste.
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=8))
    assert "HINWEIS AN DICH" not in text
    assert len(text.splitlines()) == 8


def test_hole_echte_daten_ohne_anfahrtszeile_wenn_keine_route_gefunden():
    # _FakeClient liefert ohne Konfiguration -1 (= keine Route) für jeden Modus.
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=3))
    assert "Anfahrt" not in text


def test_hole_echte_daten_nennt_anfahrtsempfehlung_je_aktivitaet():
    # Bis zu 2 Optionen, sortiert nach Dauer, mit dauer-basierter Begründung.
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", zielregionen=["Musterstadt"])
    client = _FakeClient(anzahl_pois=2, anfahrtszeiten_je_modus={"walking": 10, "transit": 15, "driving": 5})
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, client)
    assert (
        "Anfahrt ab Musterstadt: mit dem Auto ca. 5 Min. (schnellste Option) "
        "oder zu Fuß ca. 10 Min. (kurze Strecke, gut zu Fuß machbar)" in text
    )
    # Fernbus/Öffentliche taucht nicht auf, weil bereits 2 (bessere) Optionen gefunden wurden.
    assert text.count("Anfahrt ab Musterstadt:") == 2  # eine Zeile pro POI (2 POIs)


def test_hole_echte_daten_warnt_und_kappt_wenn_ueber_schwelle():
    # 50 Rohtreffer (weit über der Warnschwelle 10) -> Hinweistext fürs LLM,
    # Vorschau gekappt auf max_pois_fuer_reise() (3 Tage * 4 = 12, aber Obergrenze 10 greift).
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=50))

    ziel_max = max_pois_fuer_reise(anfrage)
    assert ziel_max == 10
    assert "HINWEIS AN DICH" in text
    assert "50" in text  # Gesamtzahl der Rohtreffer wird genannt
    assert str(ziel_max) in text  # angebotene Auswahlgröße wird genannt
    # Vorschau enthält genau ziel_max POI-Zeilen (an "- POI " erkennbar).
    assert sum(1 for zeile in text.splitlines() if zeile.startswith("- POI ")) == ziel_max


def test_hole_echte_daten_kappt_immer_auf_max_pois_fuer_reise():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="10 Tage")  # -> 10 (Obergrenze, siehe Kosten-Vorfall)
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=50))
    assert sum(1 for zeile in text.splitlines() if zeile.startswith("- POI ")) == 10


class _FakeVerkehrsmittelClient:
    """Für die verkehrsmittel_praeferenz-Tests: konfigurierbare Bahn/Auto/Fernbus-Dauer."""

    def __init__(self, alternativen: list[ReiseAlternative]):
        self._alternativen = alternativen

    def reisealternativen(self, von, nach):
        return self._alternativen

    def geocode(self, ort):
        return (48.0, 11.0)


_NAHE_ALTERNATIVEN = [
    ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=280, kosten_euro=90, distanz_km=500),
]
_FERNE_ALTERNATIVEN = [
    ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=900, kosten_euro=200, distanz_km=3000),
    ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=1500, kosten_euro=250, distanz_km=3000),
]
# Auto klar schneller UND günstiger, aber deutlich mehr CO2 (168 vs 19 g/Pkm) -> Auto gewinnt die
# Gewichtung, Bahn ist NICHT die beste Alternative -> Nachhaltigkeits-Nudge muss greifen.
_NUDGE_ALTERNATIVEN = [
    ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=200, kosten_euro=60, distanz_km=500),
]


def test_verkehrsmittel_ohne_hinweis_wenn_ziel_nah_genug():
    anfrage = ReiseAnfrage(wohnort="Berlin", zielregionen=["München"])
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_VERKEHRSMITTEL, anfrage, _FakeVerkehrsmittelClient(_NAHE_ALTERNATIVEN))
    assert "HINWEIS AN DICH" not in text
    assert "- Bahn: 300 Minuten, 80 €" in text


def test_verkehrsmittel_zeigt_nachhaltigkeits_nudge_wenn_bahn_nicht_beste():
    anfrage = ReiseAnfrage(wohnort="Berlin", zielregionen=["München"])
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_VERKEHRSMITTEL, anfrage, _FakeVerkehrsmittelClient(_NUDGE_ALTERNATIVEN))
    assert "NACHHALTIGKEITS-HINWEIS FÜR DICH (LLM)" in text
    assert "CO2" in text


def test_verkehrsmittel_schlaegt_alternativziel_vor_wenn_zu_weit():
    # Bahn/Auto beide > 12h (siehe _MAX_REISEZEIT_MINUTEN) -> Hinweis statt stillschweigend zu
    # akzeptieren; noch KEIN Alternativziel-Verzicht (ziel_trotzdem_gewuenscht=False).
    anfrage = ReiseAnfrage(wohnort="Berlin", zielregionen=["Türkei"], reiseerlebnis_beschreibung="türkisblaues Meer")
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_VERKEHRSMITTEL, anfrage, _FakeVerkehrsmittelClient(_FERNE_ALTERNATIVEN))
    assert "HINWEIS AN DICH" in text
    assert "türkisblaues Meer" in text


def test_verkehrsmittel_zeigt_alternativen_wenn_ziel_trotzdem_gewuenscht():
    anfrage = ReiseAnfrage(wohnort="Berlin", zielregionen=["Türkei"])
    text = hole_echte_daten_fuer_vorschlag(
        _FRAGE_VERKEHRSMITTEL, anfrage, _FakeVerkehrsmittelClient(_FERNE_ALTERNATIVEN), ziel_trotzdem_gewuenscht=True,
    )
    assert "HINWEIS AN DICH" not in text  # kein erneuter Alternativ-Vorschlag
    assert "- Bahn: 900 Minuten, 200 €" in text


class _FakeUnterkunftClient:
    def __init__(self, unterkuenfte=None):
        self._unterkuenfte = unterkuenfte or []
        self.letzter_praeferenz_text = None

    def suche_unterkuenfte(self, ort, praeferenz_text=None):
        self.letzter_praeferenz_text = praeferenz_text
        return self._unterkuenfte

    def geocode(self, ort):
        return (36.9, 30.7)


def test_suche_unterkunft_gibt_ersten_treffer_zurueck():
    anfrage = ReiseAnfrage(zielregionen=["Italien"])
    client = _FakeUnterkunftClient([
        Unterkunft(id=1, name="Hotel X", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=True),
        Unterkunft(id=2, name="Hotel Y", x=0, y=0, preisniveau=1, zertifiziert_nachhaltig=False),
    ])
    text, gefunden = suche_unterkunft(anfrage, client, "ein gemütliches B&B")
    assert "Hotel X" in text
    assert "Hotel Y" not in text
    assert gefunden is not None and gefunden.name == "Hotel X"


def test_suche_unterkunft_gibt_antwort_als_praeferenz_text_an_places_weiter():
    anfrage = ReiseAnfrage(zielregionen=["Italien"])
    client = _FakeUnterkunftClient([Unterkunft(id=1, name="Hotel X", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=True)])
    suche_unterkunft(anfrage, client, "ruhige Lage mit Balkon")
    assert client.letzter_praeferenz_text == "ruhige Lage mit Balkon"


def test_suche_unterkunft_ohne_treffer_meldet_das_ehrlich():
    anfrage = ReiseAnfrage(zielregionen=["Italien"])
    text, gefunden = suche_unterkunft(anfrage, _FakeUnterkunftClient([]), "Hotel")
    assert "KEINE Unterkünfte gefunden" in text
    assert gefunden is None


class _FakeBarrierefreiClient(_FakeUnterkunftClient):
    def __init__(self, unterkuenfte, status_je_place_id):
        super().__init__(unterkuenfte)
        self._status_je_place_id = status_je_place_id

    def ist_barrierefrei(self, place_id):
        return self._status_je_place_id.get(place_id)


def test_suche_unterkunft_filtert_nicht_barrierefreie_hotels_bei_bedarf():
    anfrage = ReiseAnfrage(zielregionen=["Italien"], unterkunft_anforderungen="bitte barrierefrei", mobilitaetseinschraenkung_stufe="mittel")
    unterkuenfte = [
        Unterkunft(id=1, name="Hotel A", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=True, place_id="a"),
        Unterkunft(id=2, name="Hotel B", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=True, place_id="b"),
    ]
    client = _FakeBarrierefreiClient(unterkuenfte, status_je_place_id={"a": False, "b": True})
    text, gefunden = suche_unterkunft(anfrage, client, "bitte barrierefrei")
    assert "Hotel A" not in text
    assert gefunden.name == "Hotel B"


class _FakeVerleihClient:
    def __init__(self, treffer):
        self._treffer = treffer

    def suche_pois(self, ort, kategorien, radius_meter=3000, ernaehrung_einschraenkungen=None):
        return list(self._treffer)

    def geocode(self, ort):
        return (0.0, 0.0)


def test_suche_verleih_nahe_unterkunft_ohne_leihwunsch_sucht_nicht():
    anfrage = ReiseAnfrage(lokaler_transport_praeferenz="ich laufe alles zu Fuß", unterkunft_koordinaten=(48.0, 11.0))
    text, gefunden = suche_verleih_nahe_unterkunft(anfrage, _FakeVerleihClient([]))
    assert gefunden is None
    assert "kein Wunsch" in text or "nichts zu suchen" in text


def test_suche_verleih_nahe_unterkunft_ohne_bestaetigte_unterkunft_wartet():
    anfrage = ReiseAnfrage(lokaler_transport_praeferenz="ich möchte vor Ort ein Fahrrad ausleihen")
    text, gefunden = suche_verleih_nahe_unterkunft(anfrage, _FakeVerleihClient([]))
    assert gefunden is None
    assert "noch nicht bestätigt" in text


def test_suche_verleih_nahe_unterkunft_waehlt_naechstgelegenen():
    anfrage = ReiseAnfrage(
        lokaler_transport_praeferenz="ich möchte vor Ort ein Fahrrad ausleihen",
        zielregionen=["Musterstadt"], unterkunft_koordinaten=(0.0, 0.0),
    )
    treffer = [
        POI(id=1, name="Verleih Fern", kategorie="fahrradverleih", x=1.0, y=1.0, score=1.0, required_time=15, opening=0, closing=600),
        POI(id=2, name="Verleih Nah", kategorie="fahrradverleih", x=0.01, y=0.0, score=1.0, required_time=15, opening=0, closing=600),
    ]
    text, gefunden = suche_verleih_nahe_unterkunft(anfrage, _FakeVerleihClient(treffer))
    assert gefunden.name == "Verleih Nah"
    assert "Fahrrad-Verleihe:" in text
    assert "Verleih Nah" in text


def test_suche_verleih_nahe_unterkunft_ohne_treffer_meldet_das_ehrlich():
    anfrage = ReiseAnfrage(
        lokaler_transport_praeferenz="ich möchte vor Ort ein Auto ausleihen",
        zielregionen=["Musterstadt"], unterkunft_koordinaten=(0.0, 0.0),
    )
    text, gefunden = suche_verleih_nahe_unterkunft(anfrage, _FakeVerleihClient([]))
    assert gefunden is None
    assert "kein Autoverleih" in text.lower() or "gefunden" in text


class _FakeNamedPoiClient:
    """Wie _FakeClient, liefert aber konkrete POI-Namen statt generischer "POI {i}" – nötig, um die
    namensbasierte Ernährungskonflikt-Erkennung (siehe vertraeglichkeit.py) zu testen."""

    def __init__(self, pois):
        self._pois = pois

    def suche_pois(self, ort, kategorien, radius_meter=3000, ernaehrung_einschraenkungen=None):
        return list(self._pois)

    def geocode(self, ort):
        return (0.0, 0.0)

    def anfahrtszeiten_minuten(self, ursprung, ziele, modus="walking"):
        return [-1 for _ in ziele]


def test_aktivitaeten_chat_vorschau_filtert_fischrestaurant_bei_fischallergie():
    pois = [
        POI(id=1, name="Fischers Fritz", kategorie="restaurant", x=0.0, y=0.0, score=1.0, required_time=60, opening=0, closing=600),
        POI(id=2, name="Trattoria Roma", kategorie="restaurant", x=0.0, y=0.0, score=1.0, required_time=60, opening=0, closing=600),
    ]
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", ernaehrung_einschraenkungen=["Fischallergie"])
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeNamedPoiClient(pois))
    assert "Fischers Fritz" not in text
    assert "Trattoria Roma" in text


class _KategorieAufzeichnenderClient:
    """Zeichnet auf, mit welchen Kategorien suche_pois aufgerufen wurde (siehe behobener Bug unten)."""

    def __init__(self):
        self.letzte_kategorien: list[str] | None = None

    def suche_pois(self, ort, kategorien, radius_meter=3000, ernaehrung_einschraenkungen=None):
        self.letzte_kategorien = list(kategorien)
        return []

    def geocode(self, ort):
        return (0.0, 0.0)

    def anfahrtszeiten_minuten(self, ursprung, ziele, modus="walking"):
        return [-1 for _ in ziele]


def test_aktivitaeten_ohne_aktivitaeten_aktuell_faellt_auf_leere_anfrage_zurueck():
    # Regression: BEIM ERSTEN Durchlauf ist anfrage.aktivitaeten_interessen noch leer (wird erst
    # nach Zustimmung über speichere_feld gesetzt) – ohne aktivitaeten_aktuell wird dadurch mit
    # einer LEEREN Kategorienliste gesucht statt mit den tatsächlich genannten Interessen.
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", zielregionen=["Italien"])
    client = _KategorieAufzeichnenderClient()

    hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, client)

    assert client.letzte_kategorien == []


def test_aktivitaeten_zeigt_hinweis_bei_mehreren_zielregionen():
    # Regression (Live-Test): der Bot hatte fälschlich behauptet, die finale Planung würde später
    # noch alle genannten Städte einzeln durchsuchen – stimmt nicht, siehe primaeres_reiseziel().
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", zielregionen=["Magdeburg", "Potsdam", "Berlin"])
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=3))
    assert "mehrere Regionen/Städte genannt" in text
    assert "Magdeburg" in text and "Potsdam" in text and "Berlin" in text
    assert "NIE, dass weitere Städte später noch durchsucht" in text


def test_aktivitaeten_ohne_hinweis_bei_einer_zielregion():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", zielregionen=["Magdeburg"])
    text = hole_echte_daten_fuer_vorschlag(_FRAGE_AKTIVITAETEN, anfrage, _FakeClient(anzahl_pois=3))
    assert "mehrere Regionen/Städte genannt" not in text


def test_suche_unterkunft_zeigt_hinweis_bei_mehreren_zielregionen():
    anfrage = ReiseAnfrage(zielregionen=["Magdeburg", "Potsdam"])
    client = _FakeUnterkunftClient([Unterkunft(id=1, name="Hotel X", x=0, y=0, preisniveau=2, zertifiziert_nachhaltig=True)])
    text, gefunden = suche_unterkunft(anfrage, client, "zentral")
    assert "mehrere Regionen/Städte genannt" in text
    assert gefunden is not None  # Hinweis blockiert die eigentliche Suche nicht


def test_aktivitaeten_aktuell_wird_fuer_die_suche_verwendet():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", zielregionen=["Italien"])
    client = _KategorieAufzeichnenderClient()

    hole_echte_daten_fuer_vorschlag(
        _FRAGE_AKTIVITAETEN, anfrage, client, aktivitaeten_aktuell=["Restaurants", "Kultur"]
    )

    assert client.letzte_kategorien == ["Restaurants", "Kultur"]

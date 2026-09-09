"""Tests für die Datenaufbereitung vor Optimierung 1 (src/datenaufbereitung/aufbereitung.py)."""
from src.api.typen import POI
from src.datenaufbereitung.aufbereitung import (
    berechne_poi_score,
    erkenne_leihwunsch,
    ergaenze_anfahrt_modus_je_etappe,
    erstelle_toptw_instanz,
    gewichte_nach_naehe_zum_depot,
    hole_reisezeitmatrix,
    max_pois_fuer_reise,
    max_pois_pro_tag_fuer_flexibilitaet,
    modi_fuer_lokalen_transport,
    parameter_fuer_lokalen_transport,
    pause_parameter_fuer_flexibilitaet,
    schaetze_reisedauer_tage,
    waehle_top_pois,
    wende_tageszeitfenster_an,
)
from src.optimierung.toptw import Besuch, Tagesroute
from src.fragekatalog.schema import ReiseAnfrage


def _poi(
    kategorie: str, score: float = 1.0, opening: int = 0, closing: int = 600, required_time: int = 60,
    nutzerinteresse: str | None = None,
) -> POI:
    return POI(id=1, name="x", kategorie=kategorie, x=0.0, y=0.0, score=score,
               required_time=required_time, opening=opening, closing=closing, nutzerinteresse=nutzerinteresse)


def test_max_pois_skaliert_mit_reisedauer():
    # Nach dem Kosten-Vorfall (siehe aufbereitung.py-Kommentar) liegt die Ober- und Untergrenze mit
    # 8-10 sehr eng beieinander – "kurz" muss daher wirklich sehr kurz sein, um noch unter der
    # Obergrenze zu bleiben.
    kurz = ReiseAnfrage(reisezeitraum_rohtext="1 Tag")
    lang = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    assert max_pois_fuer_reise(kurz) < max_pois_fuer_reise(lang)


def test_max_pois_hat_untergrenze_bei_sehr_kurzer_reise():
    sehr_kurz = ReiseAnfrage(reisezeitraum_rohtext="1 Tag")
    assert max_pois_fuer_reise(sehr_kurz) == 8  # _MIN_POIS_FUER_OPTIMIERUNG


def test_max_pois_hat_obergrenze_bei_sehr_langer_reise():
    # Obergrenze wurde nach einem echten Kosten-Vorfall (Distance-Matrix-Kosten skalieren
    # quadratisch mit dieser Zahl) zunächst von 30 auf 15, dann auf 10 gesenkt (hergeleitet aus
    # 3 Tage x 3 POIs/Tag bei strengster Flexibilitätsstufe + 1 Reserve-Kandidat).
    sehr_lang = ReiseAnfrage(reisezeitraum_rohtext="30 Tage")
    assert max_pois_fuer_reise(sehr_lang) == 10  # _MAX_POIS_FUER_OPTIMIERUNG


def test_schaetze_reisedauer_tage_erkennt_explizite_tagesangabe():
    assert schaetze_reisedauer_tage("15 Tage") == 15


def test_schaetze_reisedauer_tage_erkennt_datumsbereich_ohne_jahr():
    # Regression (Live-Vorfall, Nutzerfeedback nach einer echten 15-Tage-Testreise): "vom 21.8. bis
    # 1.9." wurde bisher NICHT erkannt (nur "X Tage"-Formulierungen), fiel auf standard_tage=5
    # zurück. Ohne Jahresangabe soll es trotzdem funktionieren.
    assert schaetze_reisedauer_tage("Ich reise vom 21.8. bis zum 1.9.") == 12


def test_schaetze_reisedauer_tage_datumsbereich_ist_inklusiv():
    # "vom 1. bis 15." = 15 Tage (Hin- und Rückreisetag zählen mit, siehe Projektkonversation).
    assert schaetze_reisedauer_tage("1.1. bis 15.1.") == 15


def test_schaetze_reisedauer_tage_datumsbereich_mit_jahr():
    assert schaetze_reisedauer_tage("21.8.2026 bis 1.9.2026") == 12


def test_schaetze_reisedauer_tage_datumsbereich_jahr_nur_am_ende():
    # Regression (Live-Vorfall): "15.09. - 18.09.2026" ergab ~700 Tage, weil das jahrlose
    # Startdatum auf ein Ankerjahr fiel statt das Jahr des Enddatums zu übernehmen.
    assert schaetze_reisedauer_tage("15.09. - 18.09.2026") == 4


def test_schaetze_reisedauer_tage_datumsbereich_jahr_nur_am_anfang():
    assert schaetze_reisedauer_tage("15.09.2026 - 18.09.") == 4


def test_schaetze_reisedauer_tage_datumsbereich_ueber_jahreswechsel():
    # Enddatum liegt "vor" dem Startdatum im Kalenderjahr -> muss als Folgejahr gelesen werden.
    assert schaetze_reisedauer_tage("28.12. bis 3.1.") == 7


def test_schaetze_reisedauer_tage_explizite_tagesangabe_geht_vor_datumsbereich():
    assert schaetze_reisedauer_tage("21.8. bis 1.9., ca. 20 Tage") == 20


def test_schaetze_reisedauer_tage_ohne_erkennbares_muster_nutzt_standard():
    assert schaetze_reisedauer_tage("irgendwann im Sommer") == 5


def test_schaetze_reisedauer_tage_ungueltiges_datum_nutzt_standard():
    assert schaetze_reisedauer_tage("32.13. bis 40.13.") == 5


def test_schaetze_reisedauer_tage_bevorzugt_iso_daten_vor_freitext():
    # Neue Architektur (Rückfrage-Ergebnis): die LLM liefert saubere ISO-Daten, der Freitext-Parser
    # ist nur noch Fallback – bei vorhandenen ISO-Daten hat er Vorrang, selbst wenn der Freitext
    # etwas anderes suggeriert.
    assert schaetze_reisedauer_tage(
        "irgendwas Unklares", start_datum="2026-09-15", end_datum="2026-09-18"
    ) == 4


def test_schaetze_reisedauer_tage_iso_daten_ohne_freitext():
    assert schaetze_reisedauer_tage(None, start_datum="2026-09-15", end_datum="2026-09-18") == 4


def test_schaetze_reisedauer_tage_ungueltige_iso_daten_fallen_auf_freitext_zurueck():
    assert schaetze_reisedauer_tage("15 Tage", start_datum="nicht-iso", end_datum="2026-09-18") == 15


def test_schaetze_reisedauer_tage_enddatum_vor_startdatum_faellt_auf_freitext_zurueck():
    assert schaetze_reisedauer_tage("15 Tage", start_datum="2026-09-18", end_datum="2026-09-15") == 15


def test_berechne_poi_score_matcht_ueber_nutzerinteresse_nicht_kategorie():
    # ARCHITEKTURWECHSEL (siehe Projektkonversation: "ich möchte klettern, nicht ins Gym – das darf
    # auf gar keinen Fall passieren"): Matching läuft nicht mehr über eine geratene Kategorie-Alias-
    # Zuordnung, sondern rein strukturell über `poi.nutzerinteresse` (den Wortlaut, für den der POI
    # gesucht wurde, siehe google_maps.py::suche_pois). `poi.kategorie` (Googles rohe Typ-Angabe)
    # spielt für das Matching selbst gar keine Rolle mehr.
    treffer = _poi("irrelevant_fuer_matching", nutzerinteresse="Klettern")
    assert berechne_poi_score(treffer, ["Klettern"]) > 1.0
    # Beliebiger Freitext funktioniert identisch – kein fester Kategorienkatalog mehr nötig.
    treffer_freitext = _poi("point_of_interest", nutzerinteresse="über Brücken spazieren gehen")
    assert berechne_poi_score(treffer_freitext, ["über Brücken spazieren gehen"]) > 1.0


def test_berechne_poi_score_ohne_passendes_nutzerinteresse_ist_null():
    # BEHOBENER BUG (siehe Projektkonversation: "er sucht einfach irgendwelche Aktivitäten raus,
    # auch Gym oder Spa, obwohl ich das nicht will"): ein POI ohne passendes Interesse bekommt NICHT
    # den neutralen Basis-Score, sondern 0.0 (wird von waehle_top_pois ausgefiltert).
    assert berechne_poi_score(_poi("museum", nutzerinteresse="Kultur"), ["Shopping"]) == 0.0


def test_berechne_poi_score_ohne_nutzerinteresse_ist_null_bei_genannten_praeferenzen():
    # Ein POI ganz ohne `nutzerinteresse` (z.B. aus einer Quelle außerhalb der interessengebundenen
    # Suche) darf nicht versehentlich als Treffer durchgehen, sobald Präferenzen genannt wurden.
    assert berechne_poi_score(_poi("museum"), ["Kultur"]) == 0.0


def test_berechne_poi_score_gewichtung_erhoeht_treffer_staerker():
    poi = _poi("museum", nutzerinteresse="Kultur")
    hoch = berechne_poi_score(poi, ["Kultur"], gewichtung={"Kultur": 3.0})
    neutral = berechne_poi_score(poi, ["Kultur"])
    assert hoch > neutral


def test_berechne_poi_score_gewichtung_ist_multiplikativ():
    # Regression (siehe Projektkonversation: "dem Nutzerkontext entsprechend gewichtet werden" –
    # die additive Formel (1.0 + gewichtung*2.0) differenzierte zu schwach, z.B. nur 3.0 -> 5.0 bei
    # doppeltem Gewicht). Jetzt: score = _BASIS_SCORE * gewichtung, doppeltes Gewicht verdoppelt
    # den Score tatsächlich.
    poi = _poi("museum", nutzerinteresse="Kultur")
    neutral = berechne_poi_score(poi, ["Kultur"])  # gewichtung fehlt -> Standard 1.0
    doppelt = berechne_poi_score(poi, ["Kultur"], gewichtung={"Kultur": 2.0})
    halb = berechne_poi_score(poi, ["Kultur"], gewichtung={"Kultur": 0.5})
    assert doppelt == neutral * 2
    assert halb == neutral * 0.5


def test_waehle_top_pois_behaelt_hoechste_scores_nicht_erste_reihenfolge():
    # Regression (siehe Projektkonversation): vorher wurde VOR dem Scoring
    # gekappt (beliebige Fund-Reihenfolge) statt die besten zu behalten.
    pois = [
        _poi("shopping_mall", nutzerinteresse="Shopping"), _poi("museum", nutzerinteresse="Kultur"),
        _poi("shopping_mall", nutzerinteresse="Shopping"), _poi("museum", nutzerinteresse="Kultur"),
    ]
    ausgewaehlt = waehle_top_pois(pois, ["Kultur"], max_anzahl=2)
    assert len(ausgewaehlt) == 2
    assert all(poi.nutzerinteresse == "Kultur" for poi in ausgewaehlt)


def test_waehle_top_pois_ohne_praeferenz_behaelt_erste_n():
    pois = [_poi("a"), _poi("b"), _poi("c")]
    ausgewaehlt = waehle_top_pois(pois, [], max_anzahl=2)
    assert len(ausgewaehlt) == 2


def test_waehle_top_pois_fuellt_nicht_mit_unpassenden_treffern_auf():
    # BEHOBENER BUG (siehe Projektkonversation: "er sucht einfach irgendwelche Aktivitäten raus,
    # auch Gym oder Spa"): früher füllten branchenfremde Treffer (z.B. ein von Google Places
    # mitgelieferter Physiotherapeut) mit neutralem Score bis zum Maximum auf. Jetzt: lieber
    # weniger als max_anzahl zurückgeben, statt mit Unpassendem aufzufüllen. Kann unter der neuen,
    # interessengebundenen Suche (siehe google_maps.py `suche_pois`) praktisch nicht mehr auftreten
    # (branchenfremde Treffer werden gar nicht erst gesucht) – der Test bleibt als Absicherung auf
    # Score-Ebene bestehen, falls doch mal ein POI ohne passendes Interesse im Pool landet.
    pois = [
        _poi("museum", nutzerinteresse="Kultur"), _poi("physiotherapist", nutzerinteresse="Shopping"),
        _poi("gym", nutzerinteresse="Sport"), _poi("spa", nutzerinteresse="Wellness"),
    ]
    ausgewaehlt = waehle_top_pois(pois, ["Kultur"], max_anzahl=4)
    assert len(ausgewaehlt) == 1  # NUR das Museum passt zu "Kultur"
    assert ausgewaehlt[0].nutzerinteresse == "Kultur"


def test_parameter_fuer_lokalen_transport_erkennt_fahrrad():
    geschwindigkeit, radius = parameter_fuer_lokalen_transport("am liebsten mit dem Fahrrad")
    assert geschwindigkeit == 15.0
    assert radius == 8000


def test_parameter_fuer_lokalen_transport_erkennt_auto():
    geschwindigkeit, radius = parameter_fuer_lokalen_transport("nur mit dem Auto")
    assert geschwindigkeit == 40.0
    assert radius == 15000


def test_parameter_fuer_lokalen_transport_ohne_angabe_ist_fusslaeufig():
    assert parameter_fuer_lokalen_transport(None) == (4.5, 3000)
    assert parameter_fuer_lokalen_transport("keine besondere Präferenz") == (4.5, 3000)


def test_wende_tageszeitfenster_an_hebt_opening_fuer_bar_an():
    # Regression (siehe Projektkonversation: "ich soll nicht direkt nach dem Aufstehen in die Bar
    # gehen") – Bar bekommt eine Mindest-Tageszeit von 8h relativ zum Tagesbeginn.
    bar = _poi("bar", opening=0, closing=600)
    ergebnis = wende_tageszeitfenster_an([bar])
    assert ergebnis[0].opening == 8 * 60


def test_wende_tageszeitfenster_an_laesst_unbeteiligte_kategorien_unveraendert():
    museum = _poi("museum", opening=0, closing=600)
    ergebnis = wende_tageszeitfenster_an([museum])
    assert ergebnis[0].opening == 0


def test_wende_tageszeitfenster_an_veraendert_original_pois_nicht():
    bar = _poi("bar", opening=0, closing=600)
    wende_tageszeitfenster_an([bar])
    assert bar.opening == 0  # Originalobjekt bleibt unverändert (siehe "weitere Empfehlungen")


def test_wende_tageszeitfenster_an_respektiert_bereits_spaetere_oeffnung():
    # Ein POI, der ohnehin schon später öffnet als die Mindest-Tageszeit, bleibt unverändert.
    bar = _poi("bar", opening=10 * 60, closing=20 * 60)
    ergebnis = wende_tageszeitfenster_an([bar])
    assert ergebnis[0].opening == 10 * 60


def test_erkenne_leihwunsch_ohne_angabe_none():
    assert erkenne_leihwunsch(None) is None
    assert erkenne_leihwunsch("") is None


def test_erkenne_leihwunsch_ohne_leih_schluesselwort_none():
    # Regression (siehe Projektkonversation): reine Fahrzeugnennung ohne erkennbaren Leihwunsch
    # (z.B. noch unbestätigte Erstantwort "Fahrrad") löst KEINE Suche aus - erst nach Bestätigung
    # eines tatsächlichen Leihwunschs im Dialog.
    assert erkenne_leihwunsch("am liebsten mit dem Fahrrad") is None
    assert erkenne_leihwunsch("mit dem Auto weiter") is None


def test_erkenne_leihwunsch_erkennt_fahrrad_und_auto():
    assert erkenne_leihwunsch("Fahrrad, ich möchte mir vor Ort eins ausleihen") == "Fahrrad"
    assert erkenne_leihwunsch("kein eigenes Rad dabei, bitte einen Verleih suchen") == "Fahrrad"
    assert erkenne_leihwunsch("ich möchte vor Ort ein Auto mieten") == "Auto"


def test_erstelle_toptw_instanz_setzt_geschwindigkeit_aus_lokalem_transport():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", lokaler_transport_praeferenz="Fahrrad")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=600, depot_koordinaten=(0.0, 0.0)
    )
    assert instanz.geschwindigkeit_kmh == 15.0


def test_erstelle_toptw_instanz_gibt_max_aktivitaetszeit_weiter():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
        max_aktivitaetszeit_minuten=360,
    )
    assert instanz.max_aktivitaetszeit_minuten == 360


def test_erstelle_toptw_instanz_max_aktivitaetszeit_default_ist_unbeschraenkt():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.max_aktivitaetszeit_minuten >= 10**9


def test_modi_fuer_lokalen_transport_erkennt_auto_und_fusslaeufigen_default():
    assert modi_fuer_lokalen_transport("nur mit dem Auto") == ["driving"]
    assert modi_fuer_lokalen_transport(None) == ["walking"]


def test_modi_fuer_lokalen_transport_erkennt_mehrere_genannte_verkehrsmittel():
    # Regression (siehe Nutzer-Feedback: "wenn er sagt Fahrrad und Bahn, dann werden Bahn UND
    # Fahrrad ausgegeben, und dann wird das genommen, was schneller ist") – vorher brach die
    # Erkennung beim ERSTEN Treffer ab und verlor das zweite genannte Verkehrsmittel.
    assert modi_fuer_lokalen_transport("am liebsten Fahrrad und Bahn") == ["bicycling", "transit"]


def test_modi_fuer_lokalen_transport_dedupliziert_gleichbedeutende_schluesselwoerter():
    # "Fahrrad" und "Rad" zeigen beide auf "bicycling" -> nur EIN Eintrag, kein doppelter Modus.
    assert modi_fuer_lokalen_transport("Fahrrad fahren, also mit dem Rad") == ["bicycling"]


def test_parameter_fuer_lokalen_transport_nimmt_groessten_radius_bei_mehreren_verkehrsmitteln():
    geschwindigkeit, radius = parameter_fuer_lokalen_transport("zu Fuß, aber auch mit dem Auto")
    assert geschwindigkeit == 4.5  # zuerst genanntes bestimmt weiterhin die Geschwindigkeit
    assert radius == 15000  # größter Suchradius unter den genannten Optionen (Auto)


def test_barrierefreiheit_oder_eingeschraenkt_liefert_llm_gesetztes_flag():
    # mobilitaetseinschraenkung_stufe wird vom LLM aus dem Gesprächskontext gesetzt (siehe
    # agent_tools.py), nicht mehr per Schlüsselwort-Suche über Freitextfelder hergeleitet – JEDE
    # der drei Stufen zählt als "eingeschränkt", nur None nicht.
    assert ReiseAnfrage(mobilitaetseinschraenkung_stufe="leicht").barrierefreiheit_oder_eingeschraenkt() is True
    assert ReiseAnfrage(mobilitaetseinschraenkung_stufe="stark").barrierefreiheit_oder_eingeschraenkt() is True
    assert ReiseAnfrage().barrierefreiheit_oder_eingeschraenkt() is False


def test_gewichte_nach_naehe_zum_depot_bevorzugt_naehere_pois():
    nah = _poi("museum", score=2.0)
    nah.x, nah.y = 0.001, 0.0
    fern = _poi("museum", score=2.0)
    fern.x, fern.y = 0.5, 0.0
    gewichtet = gewichte_nach_naehe_zum_depot([nah, fern], depot_koordinaten=(0.0, 0.0))
    nah_gewichtet, fern_gewichtet = gewichtet
    assert nah_gewichtet.score > fern_gewichtet.score
    # Ursprüngliche POIs bleiben unverändert (nicht-mutierend, siehe dataclasses.replace).
    assert nah.score == 2.0


def test_erstelle_toptw_instanz_reduziert_geschwindigkeit_nur_bei_gehschwierigkeit_und_fusslaeufig():
    anfrage_gehschwierigkeit = ReiseAnfrage(
        reisezeitraum_rohtext="3 Tage", gesundheitliche_einschraenkungen="Schwierigkeiten zu gehen",
        mobilitaetseinschraenkung_stufe="leicht",
    )
    instanz = erstelle_toptw_instanz(
        anfrage_gehschwierigkeit, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.geschwindigkeit_kmh == 2.0
    assert instanz.pause_intervall_minuten == 120

    # Bei bestätigtem Auto NICHT "verlangsamt" – die Person sitzt ja nicht zu Fuß in der Bahn.
    anfrage_mit_auto = ReiseAnfrage(
        reisezeitraum_rohtext="3 Tage", gesundheitliche_einschraenkungen="Schwierigkeiten zu gehen",
        lokaler_transport_praeferenz="Auto", mobilitaetseinschraenkung_stufe="leicht",
    )
    instanz_auto = erstelle_toptw_instanz(
        anfrage_mit_auto, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz_auto.geschwindigkeit_kmh == 40.0


def test_erstelle_toptw_instanz_ohne_gehschwierigkeit_bleibt_unveraendert():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.geschwindigkeit_kmh == 4.5
    assert instanz.pause_intervall_minuten is None


class _FakeMatrixClient:
    """Liefert eine feste Reisezeit-Matrix (Minuten) für `hole_reisezeitmatrix`."""

    def __init__(self, matrix: list[list[int]]):
        self._matrix = matrix
        self.aufgerufen_mit_modus: str | None = None

    def distanzmatrix(self, orte, modus="walking"):
        self.aufgerufen_mit_modus = modus
        return self._matrix


def test_hole_reisezeitmatrix_baut_id_lookup_aus_client_antwort():
    depot = POI(id=0, name="Depot", kategorie="depot", x=0.0, y=0.0, score=0.0, required_time=0, opening=0, closing=600)
    poi = _poi("museum")
    poi.id = 5
    client = _FakeMatrixClient(matrix=[[0, 7], [8, 0]])

    reisezeiten = hole_reisezeitmatrix(client, depot, [poi], modi=["driving"])

    assert reisezeiten[(0, 5)] == 7
    assert reisezeiten[(5, 0)] == 8
    assert client.aufgerufen_mit_modus == "driving"


def test_hole_reisezeitmatrix_laesst_fehlende_route_aus():
    depot = POI(id=0, name="Depot", kategorie="depot", x=0.0, y=0.0, score=0.0, required_time=0, opening=0, closing=600)
    poi = _poi("museum")
    poi.id = 5
    client = _FakeMatrixClient(matrix=[[0, -1], [-1, 0]])  # -1 = keine Route gefunden

    reisezeiten = hole_reisezeitmatrix(client, depot, [poi], modi=["walking"])

    assert reisezeiten == {}  # kein erfundener Wert (Grundprinzip 1), TOPTWInstanz fällt auf Luftlinie zurück


class _FakeMehrModusMatrixClient:
    """Liefert je Modus eine eigene Reisezeit-Matrix – für den Minimum-Vergleich bei mehreren genannten Verkehrsmitteln."""

    def __init__(self, matrix_je_modus: dict[str, list[list[int]]]):
        self._matrix_je_modus = matrix_je_modus

    def distanzmatrix(self, orte, modus="walking"):
        return self._matrix_je_modus[modus]


def test_hole_reisezeitmatrix_nimmt_bei_mehreren_modi_die_schnellere_zeit():
    depot = POI(id=0, name="Depot", kategorie="depot", x=0.0, y=0.0, score=0.0, required_time=0, opening=0, closing=600)
    poi = _poi("museum")
    poi.id = 5
    client = _FakeMehrModusMatrixClient({
        "bicycling": [[0, 20], [21, 0]],
        "transit": [[0, 12], [13, 0]],
    })

    reisezeiten = hole_reisezeitmatrix(client, depot, [poi], modi=["bicycling", "transit"])

    assert reisezeiten[(0, 5)] == 12  # transit ist auf dieser Etappe schneller
    assert reisezeiten[(5, 0)] == 13


def test_hole_reisezeitmatrix_nimmt_bei_fehlender_route_die_verfuegbare_alternative():
    depot = POI(id=0, name="Depot", kategorie="depot", x=0.0, y=0.0, score=0.0, required_time=0, opening=0, closing=600)
    poi = _poi("museum")
    poi.id = 5
    client = _FakeMehrModusMatrixClient({
        "bicycling": [[0, -1], [-1, 0]],  # keine Route gefunden
        "transit": [[0, 12], [13, 0]],
    })

    reisezeiten = hole_reisezeitmatrix(client, depot, [poi], modi=["bicycling", "transit"])

    assert reisezeiten[(0, 5)] == 12


def test_erstelle_toptw_instanz_nutzt_client_fuer_echte_reisezeiten():
    poi = _poi("museum")
    poi.id = 7
    client = _FakeMatrixClient(matrix=[[0, 12], [13, 0]])
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")

    instanz = erstelle_toptw_instanz(
        anfrage, pois=[poi], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0), client=client,
    )

    assert instanz.reisezeiten_minuten[(0, 7)] == 12


def test_erstelle_toptw_instanz_ohne_client_hat_keine_matrix():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.reisezeiten_minuten is None


class _FakeAnfahrtszeitenClient:
    """Liefert je Modus eine feste Dauer für JEDES angefragte Ziel – für
    `ergaenze_anfahrt_modus_je_etappe`."""

    def __init__(self, dauer_je_modus: dict[str, int]):
        self._dauer_je_modus = dauer_je_modus
        self.aufrufe: list[str] = []

    def anfahrtszeiten_minuten(self, ursprung, ziele, modus="walking"):
        self.aufrufe.append(modus)
        return [self._dauer_je_modus.get(modus, -1) for _ in ziele]


def test_ergaenze_anfahrt_modus_je_etappe_bei_einem_modus_ohne_api_aufruf():
    poi = _poi("museum")
    route = Tagesroute(besuche=[Besuch(poi=poi, ankunft=10, wartezeit=0, abfahrt=70)])
    client = _FakeAnfahrtszeitenClient({})

    ergaenze_anfahrt_modus_je_etappe(client, depot_koordinaten=(0.0, 0.0), tagesrouten=[route], modi=["walking"])

    assert route.besuche[0].anfahrt_modus == "walking"
    assert client.aufrufe == []  # kein API-Aufruf nötig, wenn nur EIN Verkehrsmittel genannt wurde


def test_ergaenze_anfahrt_modus_je_etappe_waehlt_schnelleres_verkehrsmittel_je_etappe():
    erster = _poi("museum")
    erster.id, erster.x, erster.y = 1, 0.01, 0.0
    zweiter = _poi("park")
    zweiter.id, zweiter.x, zweiter.y = 2, 0.02, 0.0
    route = Tagesroute(besuche=[
        Besuch(poi=erster, ankunft=10, wartezeit=0, abfahrt=70),
        Besuch(poi=zweiter, ankunft=80, wartezeit=0, abfahrt=140),
    ])
    client = _FakeAnfahrtszeitenClient({"bicycling": 20, "transit": 12})

    ergaenze_anfahrt_modus_je_etappe(client, depot_koordinaten=(0.0, 0.0), tagesrouten=[route], modi=["bicycling", "transit"])

    assert route.besuche[0].anfahrt_modus == "transit"
    assert route.besuche[1].anfahrt_modus == "transit"


def test_ergaenze_anfahrt_modus_je_etappe_faellt_auf_erstes_modus_zurueck_ohne_gueltige_route():
    poi = _poi("museum")
    route = Tagesroute(besuche=[Besuch(poi=poi, ankunft=10, wartezeit=0, abfahrt=70)])
    client = _FakeAnfahrtszeitenClient({})  # liefert -1 für jeden angefragten Modus

    ergaenze_anfahrt_modus_je_etappe(client, depot_koordinaten=(0.0, 0.0), tagesrouten=[route], modi=["bicycling", "transit"])

    assert route.besuche[0].anfahrt_modus == "bicycling"  # erstes genanntes Verkehrsmittel als Fallback


def test_max_pois_pro_tag_fuer_flexibilitaet_je_stufe():
    # Skala 1-3 (verkleinert im Zuge des Kosten-Vorfalls, siehe aufbereitung.py-Kommentar), vom LLM
    # aus dem Gesprächsverlauf gesetzt (siehe schema.py `flexibilitaet_stufe`, ENTSCHEIDUNGSLOG.md).
    # Anders als die frühere 1-5-Skala hat JETZT auch Stufe 1 einen festen Deckel.
    assert max_pois_pro_tag_fuer_flexibilitaet(1) == 3  # ganz durchgeplant
    assert max_pois_pro_tag_fuer_flexibilitaet(2) == 2
    assert max_pois_pro_tag_fuer_flexibilitaet(3) == 1  # extrem flexibel


def test_max_pois_pro_tag_fuer_flexibilitaet_ohne_signal_none():
    assert max_pois_pro_tag_fuer_flexibilitaet(None) is None


def test_pause_parameter_fuer_flexibilitaet_je_stufe():
    # Ab Stufe 2 zusätzlich eine Pufferpause (Rückfrage-Ergebnis: nicht nur weniger Stopps, sondern
    # echter Freiraum zwischendrin, z.B. für spontanen Kaffee) – Stufe 1 ("ganz durchgeplant")
    # bewusst ohne Puffer.
    assert pause_parameter_fuer_flexibilitaet(1) == (None, None)
    assert pause_parameter_fuer_flexibilitaet(2) == (150, 20)
    assert pause_parameter_fuer_flexibilitaet(3) == (90, 30)
    assert pause_parameter_fuer_flexibilitaet(None) == (None, None)


def test_erstelle_toptw_instanz_setzt_max_pois_pro_tag_und_puffer_aus_flexibilitaetsstufe():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage", flexibilitaet_stufe=3)
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.max_pois_pro_tag == 1
    assert instanz.pause_intervall_minuten == 90
    assert instanz.pause_dauer_minuten == 30


def test_erstelle_toptw_instanz_ohne_flexibilitaetsstufe_keine_tagesobergrenze():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.max_pois_pro_tag is None
    assert instanz.pause_intervall_minuten is None


def test_erstelle_toptw_instanz_anzahl_tage_override_ersetzt_geschaetzte_dauer():
    # Siehe pipeline.py `_trenne_tour_beispiele_ab`: ein für geführte Touren reservierter Tag muss
    # NICHT von Optimierung 1 mitgeplant werden – ohne Override würde die Instanz weiterhin die
    # volle geschätzte Reisedauer (3) annehmen.
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
        anzahl_tage_override=2,
    )
    assert instanz.anzahl_tage == 2


def test_erstelle_toptw_instanz_ohne_override_nutzt_geschaetzte_dauer():
    anfrage = ReiseAnfrage(reisezeitraum_rohtext="3 Tage")
    instanz = erstelle_toptw_instanz(
        anfrage, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.anzahl_tage == 3


def test_erstelle_toptw_instanz_barrierefreiheit_und_flexibilitaet_kombiniert_nimmt_kuerzeres_intervall():
    # Beide Mechanismen können gleichzeitig zutreffen (siehe aufbereitung.py `erstelle_toptw_
    # instanz`) – das KÜRZERE Intervall gewinnt, eine nötige Barrierefreiheits-Pause (120 Min.) darf
    # durch eine niedrige Flexibilitätsstufe nie "wegoptimiert" werden.
    anfrage_stufe_1 = ReiseAnfrage(
        reisezeitraum_rohtext="3 Tage", altersgerechte_beduerfnisse="Rollstuhl",
        mobilitaetseinschraenkung_stufe="mittel", flexibilitaet_stufe=1,
    )
    instanz = erstelle_toptw_instanz(
        anfrage_stufe_1, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz.pause_intervall_minuten == 120  # Barrierefreiheits-Wert bleibt bestehen

    anfrage_stufe_3 = ReiseAnfrage(
        reisezeitraum_rohtext="3 Tage", altersgerechte_beduerfnisse="Rollstuhl",
        mobilitaetseinschraenkung_stufe="mittel", flexibilitaet_stufe=3,
    )
    instanz_flexibel = erstelle_toptw_instanz(
        anfrage_stufe_3, pois=[], standard_tagesbudget_minuten=480, depot_koordinaten=(0.0, 0.0),
    )
    assert instanz_flexibel.pause_intervall_minuten == 90  # Flexibilitäts-Wert ist kürzer, gewinnt
    assert instanz_flexibel.pause_dauer_minuten == 30

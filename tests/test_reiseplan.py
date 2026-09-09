"""Tests für die Reiseplan-Ausgabe (src/ausgabe/reiseplan.py)."""
import csv
import re

from src.api.typen import POI, ReiseAlternative, Teilstrecke
from src.ausgabe.reiseplan import Reiseplan, als_html, als_kartendaten, als_text, routen_link, speichere_poi_uebersicht
from src.optimierung.toptw import Besuch, Tagesroute
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative

_BAHN = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    co2_kg=9.5, score=0.1,
)
_LANGE_ANREISE = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=1119, kosten_euro=200, distanz_km=3000),
    co2_kg=21.3, score=0.5,
)
_POI = POI(id=1, name="Kletterroute XY", kategorie="klettern", x=0.0, y=0.0, score=3.0, required_time=180, opening=0, closing=600)


def _basis_plan(**zusatz) -> Reiseplan:
    parameter = {"hinreise": _BAHN, "tagesrouten": [], "rueckreise": _BAHN}
    parameter.update(zusatz)
    return Reiseplan(**parameter)


def test_als_text_ohne_kandidaten_und_hinweis_zeigt_nichts_zusaetzliches():
    text = als_text(_basis_plan())
    assert "Weitere gefundene Unterkunfts-Empfehlungen" not in text
    assert "Sicherheit" not in text


def test_als_text_zeigt_unterkunft_mit_link():
    text = als_text(_basis_plan(unterkunft_name="Hotel Zentral", unterkunft_place_id="abc123"))
    assert "Unterkunft: Hotel Zentral" in text
    assert "query_place_id=abc123" in text


def test_als_text_zeigt_sicherheitshinweis_nur_wenn_gesetzt():
    text = als_text(_basis_plan(sicherheitshinweis="Sicherheit war Ihnen wichtig – ..."))
    assert "Sicherheit war Ihnen wichtig" in text


def test_als_html_zeigt_unterkunft_und_sicherheitshinweis():
    html_text = als_html(_basis_plan(unterkunft_name="Hotel Zentral", sicherheitshinweis="Bitte Hinweise prüfen"))
    assert "Hotel Zentral" in html_text
    assert "Bitte Hinweise prüfen" in html_text


def test_als_text_zeigt_fahrzeit_von_unterkunft_und_zwischen_pois():
    # Regression (siehe Projektkonversation: "wär's gut, wenn ich in diesen Tagesansichten die
    # Routenlänge zwischen den einzelnen POIs kennen würde") – Fahrzeit steckt bereits exakt in
    # ankunft/abfahrt (siehe toptw.py), keine neue Berechnung nötig, nur die Anzeige.
    zweiter_poi = POI(id=2, name="Trajansmärkte", kategorie="museum", x=0.0, y=0.0, score=2.0,
                       required_time=90, opening=0, closing=600)
    tag1 = Tagesroute(besuche=[
        Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195),
        Besuch(poi=zweiter_poi, ankunft=210, wartezeit=0, abfahrt=300),
    ])
    text = als_text(_basis_plan(tagesrouten=[tag1]))
    assert "→ 15 Min. von Unterkunft" in text
    assert "→ 15 Min. von Kletterroute XY" in text  # 210 (ankunft) - 195 (vorherige abfahrt)


def test_als_html_zeigt_fahrzeit_von_unterkunft_und_zwischen_pois():
    zweiter_poi = POI(id=2, name="Trajansmärkte", kategorie="museum", x=0.0, y=0.0, score=2.0,
                       required_time=90, opening=0, closing=600)
    tag1 = Tagesroute(besuche=[
        Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195),
        Besuch(poi=zweiter_poi, ankunft=210, wartezeit=0, abfahrt=300),
    ])
    html_text = als_html(_basis_plan(tagesrouten=[tag1]))
    assert "→ 15 min von Unterkunft" in html_text
    assert "→ 15 min von Kletterroute XY" in html_text


def test_als_text_tag1_nennt_ankunft_und_check_in():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    plan = _basis_plan(hinreise=_LANGE_ANREISE, tagesrouten=[tag1])
    text = als_text(plan)
    assert "Tag 1 (Ankunft)" in text
    assert "Ankunft mit Bahn nach 18h 39min – danach Check-in in der Unterkunft." in text
    assert "Ab Ankunft:" in text
    assert "nach 15min: Kletterroute XY (bis 3h 15min, Score 3.0)" in text
    # keine erfundene Uhrzeit wie "09:15" im Text (kein echtes Abfahrtsdatum vorhanden, Grundprinzip 1) –
    # Zeiten bleiben relativ ("nach Xmin"/"XhYmin"), kein HH:MM-Muster.
    assert not re.search(r"\b\d{1,2}:\d{2}\b", text)


def test_als_text_ohne_tagesstart_minuten_bleibt_relativ_auch_ab_tag2():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tag2 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=30, wartezeit=0, abfahrt=210)])
    text = als_text(_basis_plan(tagesrouten=[tag1, tag2]))
    assert not re.search(r"\b\d{1,2}:\d{2}\b", text)


def test_als_text_mit_tagesstart_minuten_zeigt_echte_uhrzeit_ab_tag2_nicht_tag1():
    # Regression (siehe Projektkonversation: "es stehen gar keine Uhrzeiten dran") – NUR ab Tag 2
    # echte Uhrzeiten, Tag 1 bleibt relativ (keine reale Ankunftsuhrzeit der Hinreise bekannt).
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tag2 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=30, wartezeit=0, abfahrt=210)])
    text = als_text(_basis_plan(tagesrouten=[tag1, tag2], tagesstart_minuten=9 * 60))

    zeilen = text.splitlines()
    tag1_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 1"))
    tag2_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 2"))
    assert not any(re.search(r"\b\d{1,2}:\d{2}\b", z) for z in zeilen[tag1_index:tag2_index])
    assert any("09:30" in z for z in zeilen[tag2_index:])  # 09:00 + 30 Min.
    assert any("12:30" in z for z in zeilen[tag2_index:])  # 09:00 + 210 Min.


def test_als_text_uhrzeit_hinweis_nur_wenn_tagesstart_minuten_gesetzt():
    ohne = als_text(_basis_plan())
    assert "basieren auf Ihrer angegebenen Tagesstart" not in ohne
    mit = als_text(_basis_plan(tagesstart_minuten=9 * 60))
    assert "basieren auf Ihrer angegebenen Tagesstart" in mit
    assert "09:00" in mit


def test_als_html_mit_tagesstart_minuten_zeigt_echte_uhrzeit_ab_tag2():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tag2 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=30, wartezeit=0, abfahrt=210)])
    html_text = als_html(_basis_plan(tagesrouten=[tag1, tag2], tagesstart_minuten=9 * 60))
    assert "09:30" in html_text
    assert "12:30" in html_text


def test_als_text_zwischentag_hat_rueckweg_hinweis_letzter_tag_nicht():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tag2 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=10, wartezeit=0, abfahrt=190)])
    text = als_text(_basis_plan(tagesrouten=[tag1, tag2]))
    zeilen = text.splitlines()
    tag1_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 1"))
    tag2_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 2"))
    assert any("Rückweg zur Unterkunft" in z for z in zeilen[tag1_index:tag2_index])
    assert not any("Rückweg zur Unterkunft" in z for z in zeilen[tag2_index:])


def test_als_text_leerer_tag_zeigt_kein_programm():
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[])]))
    assert "(kein Programm eingeplant)" in text
    assert "Ab Ankunft:" not in text


def test_als_html_tag1_nennt_ankunft_und_check_in():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    html_text = als_html(_basis_plan(hinreise=_LANGE_ANREISE, tagesrouten=[tag1]))
    assert "Tag 1 (Ankunft)" in html_text
    assert "Check-in in der Unterkunft" in html_text
    assert "Ab Ankunft" in html_text


def test_als_text_zeigt_einleitung_grobe_struktur_statt_fertiger_plan():
    # Regression (siehe Projektkonversation): "ich möchte nicht, dass am Ende eine vollkommen fertig
    # geplante Reise entsteht ... eine grobe Struktur liefern und er trifft dann Entscheidungen".
    text = als_text(_basis_plan())
    assert "grobe Struktur" in text
    assert "kein fertig gebuchter Plan" in text


def test_als_text_tagesueberschrift_ist_als_vorschlag_gekennzeichnet():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    text = als_text(_basis_plan(tagesrouten=[tag1]))
    assert "unser Vorschlag" in text


def test_als_text_ohne_weitere_empfehlungen_zeigt_nichts_zusaetzliches():
    text = als_text(_basis_plan())
    assert "Weitere Empfehlungen in der Nähe" not in text


def test_als_text_zeigt_weitere_aktivitaeten_empfehlungen_mit_link():
    # POIs, die Optimierung 1 NICHT in die Tagesroute übernommen hat (Zeitfenster/Budget), werden
    # nicht verworfen, sondern als frei kombinierbare Empfehlung gezeigt (siehe Projektkonversation).
    weitere = [POI(id=2, name="Trajansmärkte", kategorie="museum", x=0.0, y=0.0, score=2.0,
                    required_time=90, opening=0, closing=600, place_id="poi-2")]
    text = als_text(_basis_plan(weitere_aktivitaeten_empfehlungen=weitere))
    assert "Weitere Empfehlungen in der Nähe" in text
    assert "Trajansmärkte" in text
    assert "query_place_id=poi-2" in text


def test_als_text_zeigt_einschraenkungshinweise():
    text = als_text(_basis_plan(einschraenkungshinweise=["Hinweis: 'Fischerhütte' ist laut Namen ..."]))
    assert "Hinweis: 'Fischerhütte'" in text


def test_als_text_ohne_leihwunsch_zeigt_nichts_zum_verleih():
    text = als_text(_basis_plan())
    assert "geliehenen" not in text
    assert "Verleih" not in text


def test_als_text_zeigt_gefundenen_verleih_mit_link():
    poi = POI(id=13, name="Autoverleih City", kategorie="car_rental", x=0.0, y=0.0, score=1.0,
              required_time=15, opening=0, closing=600, place_id="mock-poi-13")
    text = als_text(_basis_plan(lokales_leihfahrzeug_gewuenscht="Auto", lokaler_verleih_poi=poi))
    assert "Auto" in text
    assert "Autoverleih City" in text
    assert "query_place_id=mock-poi-13" in text


def test_als_text_leihwunsch_ohne_treffer_zeigt_ehrliche_fehlanzeige():
    # Regression: KEIN erfundener Verleih, wenn nichts gefunden wurde (Grundprinzip 1).
    text = als_text(_basis_plan(lokales_leihfahrzeug_gewuenscht="Fahrrad", lokaler_verleih_poi=None))
    assert "Fahrrad" in text
    assert "konnten wir aber keinen Verleih finden" in text


def test_als_html_zeigt_weitere_empfehlungen_und_einschraenkungshinweise():
    weitere = [POI(id=2, name="Trajansmärkte", kategorie="museum", x=0.0, y=0.0, score=2.0,
                    required_time=90, opening=0, closing=600, place_id="poi-2")]
    html_text = als_html(_basis_plan(
        weitere_aktivitaeten_empfehlungen=weitere, einschraenkungshinweise=["Hinweis: Konflikt gefunden"],
    ))
    assert "Weitere Empfehlungen in der Nähe" in html_text
    assert "Trajansmärkte" in html_text
    assert "Hinweis: Konflikt gefunden" in html_text


def test_als_text_leerer_tag_zeigt_beispiele_aus_weiteren_empfehlungen():
    # "dann soll das nicht einfach nur leer stehen, sondern einfach zwei, drei Beispiele" (Nutzer-
    # wunsch zu geführten Touren, generisch für JEDEN nicht eingeplanten Kandidaten umgesetzt).
    tour = POI(id=2, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=2.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], weitere_aktivitaeten_empfehlungen=[tour]))
    assert "(kein Programm eingeplant)" not in text
    assert "mögliche Beispiele für diesen Tag" in text
    assert "Stadtführung Altstadt" in text


def test_als_text_leerer_tag_beispiel_verschwindet_aus_weiteren_empfehlungen():
    # Kein Duplikat: ein POI, der schon als Tages-Beispiel gezeigt wird, taucht nicht zusätzlich
    # noch einmal in der allgemeinen "Weitere Empfehlungen"-Liste auf.
    tour = POI(id=2, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=2.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], weitere_aktivitaeten_empfehlungen=[tour]))
    assert text.count("Stadtführung Altstadt") == 1


def test_als_html_leerer_tag_zeigt_beispiele_statt_kein_programm():
    tour = POI(id=2, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=2.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    html_text = als_html(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], weitere_aktivitaeten_empfehlungen=[tour]))
    assert "(kein Programm eingeplant)" not in html_text
    assert "Stadtführung Altstadt" in html_text


def test_als_text_zeigt_beispielrestaurants_je_tag():
    # "einfach Beispielrestaurants in der Nähe von der Unterkunft" – Restaurants laufen NICHT durch
    # Optimierung 1 (siehe pipeline.py), werden aber trotzdem angezeigt, auch an einem Tag MIT
    # normalem Programm.
    restaurant = POI(id=3, name="Trattoria da Nino", kategorie="restaurant", x=0.0, y=0.0, score=1.0,
                      required_time=60, opening=0, closing=600, place_id="poi-restaurant")
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    text = als_text(_basis_plan(tagesrouten=[tag1], beispielrestaurants=[restaurant]))
    assert "Beispielrestaurants in der Nähe der Unterkunft" in text
    assert "Trattoria da Nino" in text


def test_als_text_ohne_beispielrestaurants_zeigt_nichts_zusaetzliches():
    text = als_text(_basis_plan())
    assert "Beispielrestaurants" not in text


def test_als_html_zeigt_beispielrestaurants_je_tag():
    restaurant = POI(id=3, name="Trattoria da Nino", kategorie="restaurant", x=0.0, y=0.0, score=1.0,
                      required_time=60, opening=0, closing=600, place_id="poi-restaurant")
    html_text = als_html(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], beispielrestaurants=[restaurant]))
    assert "Beispielrestaurants in der Nähe der Unterkunft" in html_text
    assert "Trattoria da Nino" in html_text


def test_als_text_letzter_tag_mit_tour_beispielen_zeigt_touren_statt_kein_programm():
    # Reservierter Tag für geführte Touren (siehe pipeline.py `_trenne_tour_beispiele_ab`) – KEIN
    # optimiertes Programm, aber auch NICHT "kein Programm eingeplant", sondern die echten Touren.
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tour = POI(id=5, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=1.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    text = als_text(_basis_plan(tagesrouten=[tag1, Tagesroute(besuche=[])], tour_tag_beispiele=[tour]))
    assert "(kein Programm eingeplant)" not in text
    assert "geführte Tour" in text
    assert "Stadtführung Altstadt" in text


def test_als_text_tour_tag_beispiele_nicht_doppelt_in_weiteren_empfehlungen():
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tour = POI(id=5, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=1.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    weiteres = POI(id=6, name="Anderer Fund", kategorie="museum", x=0.0, y=0.0, score=1.0,
                   required_time=60, opening=0, closing=600, place_id="poi-anderer")
    text = als_text(_basis_plan(
        tagesrouten=[tag1, Tagesroute(besuche=[])], tour_tag_beispiele=[tour],
        weitere_aktivitaeten_empfehlungen=[weiteres],
    ))
    assert text.count("Stadtführung Altstadt") == 1
    assert "Anderer Fund" in text  # der reservierte Tag verbraucht NICHT den generischen Vorrat


def test_als_html_letzter_tag_mit_tour_beispielen_zeigt_touren():
    tour = POI(id=5, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=1.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    html_text = als_html(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], tour_tag_beispiele=[tour]))
    assert "(kein Programm eingeplant)" not in html_text
    assert "Stadtführung Altstadt" in html_text


def test_als_text_letzter_tag_mit_lernaktivitaet_zeigt_kurs_statt_kein_programm():
    # Genau wie geführte Touren behandelt (Rückfrage-Ergebnis): "das möchte ich auf jeden Fall
    # lernen" darf nie vom Optimierungsalgorithmus aussortiert werden können.
    kochkurs = POI(id=7, name="Kochkurs Wiener Küche", kategorie="point_of_interest", x=0.0, y=0.0,
                    score=1.0, required_time=180, opening=0, closing=600, place_id="poi-kochkurs")
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[])], lernaktivitaet_tag_beispiele=[kochkurs]))
    assert "(kein Programm eingeplant)" not in text
    assert "Lernaktivität" in text
    assert "Kochkurs Wiener Küche" in text


def test_als_text_tour_und_lernaktivitaet_bekommen_getrennte_tage():
    # Beide Sonderkategorien gleichzeitig gefunden -> ZWEI getrennte reservierte Tage (Rückfrage-
    # Ergebnis), nicht ein gemeinsamer.
    tag1 = Tagesroute(besuche=[Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)])
    tour = POI(id=5, name="Stadtführung Altstadt", kategorie="travel_agency", x=0.0, y=0.0, score=1.0,
               required_time=120, opening=0, closing=600, place_id="poi-tour")
    kochkurs = POI(id=7, name="Kochkurs Wiener Küche", kategorie="point_of_interest", x=0.0, y=0.0,
                    score=1.0, required_time=180, opening=0, closing=600, place_id="poi-kochkurs")
    text = als_text(_basis_plan(
        tagesrouten=[tag1, Tagesroute(besuche=[]), Tagesroute(besuche=[])],
        tour_tag_beispiele=[tour], lernaktivitaet_tag_beispiele=[kochkurs],
    ))
    zeilen = text.splitlines()
    tag2_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 2"))
    tag3_index = next(i for i, z in enumerate(zeilen) if z.startswith("Tag 3"))
    tag2_block = "\n".join(zeilen[tag2_index:tag3_index])
    tag3_block = "\n".join(zeilen[tag3_index:])
    assert "Stadtführung Altstadt" in tag2_block and "Kochkurs Wiener Küche" not in tag2_block
    assert "Kochkurs Wiener Küche" in tag3_block and "Stadtführung Altstadt" not in tag3_block


def test_als_text_zeigt_umstiege_und_wartezeit_statt_nur_gesamtdauer():
    # Regression (siehe Projektkonversation: "nicht nur sagen mit Bahn brauchst du eine Stunde,
    # sondern 30 min dahin, dann umsteigen mit 5 min Wartezeit, dann 25 min Fahrzeit").
    bahn_mit_umstieg = BewerteteAlternative(
        alternative=ReiseAlternative(
            verkehrsmittel="Bahn", dauer_minuten=60, kosten_euro=40, distanz_km=100,
            teilstrecken=[
                Teilstrecke(modus="TRANSIT", linie="ICE 123", von="Berlin Hbf", nach="Fulda", dauer_minuten=30),
                Teilstrecke(modus="TRANSIT", linie="RE 456", von="Fulda", nach="München Hbf", dauer_minuten=25, wartezeit_minuten=5),
            ],
        ),
        co2_kg=9.5, score=0.1,
    )
    text = als_text(_basis_plan(hinreise=bahn_mit_umstieg))

    assert "ICE 123: Berlin Hbf → Fulda (30 min)" in text
    assert "Umstieg in Fulda (5 min Wartezeit)" in text
    assert "RE 456: Fulda → München Hbf (25 min)" in text


def test_als_text_ohne_teilstrecken_zeigt_nur_gesamtdauer():
    text = als_text(_basis_plan())  # _BAHN hat keine teilstrecken (Default leer)
    assert "Umstieg" not in text


def test_als_html_zeigt_umstiege_und_wartezeit():
    bahn_mit_umstieg = BewerteteAlternative(
        alternative=ReiseAlternative(
            verkehrsmittel="Bahn", dauer_minuten=60, kosten_euro=40, distanz_km=100,
            teilstrecken=[
                Teilstrecke(modus="TRANSIT", linie="ICE 123", von="Berlin Hbf", nach="Fulda", dauer_minuten=30),
                Teilstrecke(modus="TRANSIT", linie="RE 456", von="Fulda", nach="München Hbf", dauer_minuten=25, wartezeit_minuten=5),
            ],
        ),
        co2_kg=9.5, score=0.1,
    )
    html_text = als_html(_basis_plan(hinreise=bahn_mit_umstieg))

    assert "ICE 123: Berlin Hbf → Fulda (30 min)" in html_text
    assert "Umstieg in Fulda (5 min Wartezeit)" in html_text


def test_speichere_poi_uebersicht_listet_eingeplante_und_nicht_eingeplante_pois(tmp_path):
    # Regression (siehe Projektkonversation: "ich brauch ein Dokument, wo mir alle POIs
    # aufgezeigt werden, sodass ich sagen kann, dass dieser Optimierungsalgorithmus funktioniert").
    eingeplant = POI(id=1, name="Kletterroute XY", kategorie="klettern", x=0.0, y=0.0, score=3.0,
                      required_time=180, opening=0, closing=600, place_id="poi-1")
    nicht_eingeplant = POI(id=2, name="Trajansmärkte", kategorie="museum", x=0.0, y=0.0, score=2.0,
                            required_time=90, opening=0, closing=600)
    tag1 = Tagesroute(besuche=[Besuch(poi=eingeplant, ankunft=15, wartezeit=0, abfahrt=195)])
    plan = _basis_plan(tagesrouten=[tag1], weitere_aktivitaeten_empfehlungen=[nicht_eingeplant])

    pfad = tmp_path / "pois.csv"
    speichere_poi_uebersicht(plan, pfad)

    with pfad.open(encoding="utf-8-sig", newline="") as datei:
        zeilen = list(csv.DictReader(datei, delimiter=";"))

    assert len(zeilen) == 2
    eingeplante_zeile = next(z for z in zeilen if z["name"] == "Kletterroute XY")
    assert eingeplante_zeile["status"] == "eingeplant"
    assert eingeplante_zeile["tag"] == "1"
    assert eingeplante_zeile["score"] == "3.00"
    assert eingeplante_zeile["ankunft"] == "15"

    nicht_eingeplante_zeile = next(z for z in zeilen if z["name"] == "Trajansmärkte")
    assert nicht_eingeplante_zeile["status"] == "nicht eingeplant (Kandidat)"
    assert nicht_eingeplante_zeile["tag"] == "-"
    assert nicht_eingeplante_zeile["ankunft"] == "-"


def test_routen_link_baut_directions_url_mit_koordinaten():
    link = routen_link((48.1, 11.5), (48.2, 11.6), "bicycling")
    assert link == "https://www.google.com/maps/dir/?api=1&origin=48.1%2C11.5&destination=48.2%2C11.6&travelmode=bicycling"


def test_routen_link_akzeptiert_ortsnamen_statt_koordinaten():
    link = routen_link("Hildesheim", "Hannover", "transit")
    assert link == "https://www.google.com/maps/dir/?api=1&origin=Hildesheim&destination=Hannover&travelmode=transit"


def test_routen_link_ohne_travelmode_laesst_parameter_weg():
    link = routen_link("Hildesheim", "Hannover", None)
    assert "travelmode" not in link


def test_routen_link_ohne_ursprung_oder_ziel_ist_none():
    assert routen_link(None, "Hannover", "driving") is None
    assert routen_link("Hildesheim", None, "driving") is None


def test_als_text_zeigt_etappen_routen_link():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="bicycling")
    text = als_text(_basis_plan(
        tagesrouten=[Tagesroute(besuche=[besuch])], unterkunft_koordinaten=(48.0, 11.0),
    ))
    assert "maps/dir/?api=1&origin=48.0%2C11.0&destination=0.0%2C0.0&travelmode=bicycling" in text


def test_als_text_ohne_unterkunft_koordinaten_zeigt_keinen_etappen_link():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="bicycling")
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[besuch])]))
    assert "maps/dir" not in text


def test_als_text_zeigt_hin_und_rueckreise_routen_link():
    text = als_text(_basis_plan(wohnort="Hildesheim", zielort="Hannover"))
    assert "maps/dir/?api=1&origin=Hildesheim&destination=Hannover&travelmode=transit" in text
    assert "maps/dir/?api=1&origin=Hannover&destination=Hildesheim&travelmode=transit" in text


def test_als_text_bevorzugt_praezise_unterkunft_fuer_hinreise_und_rueckreise_link():
    # Regression (Nutzerfeedback: der Link zur groben Zielstadt allein war "nur halbwegs gut") –
    # sobald eine Unterkunft bestätigt ist, zeigt der Link auf deren GENAUE Koordinaten statt nur
    # auf die Stadt, damit die tatsächlich gebuchte Route in Google Maps sichtbar wird.
    text = als_text(_basis_plan(wohnort="Hildesheim", zielort="Hannover", unterkunft_koordinaten=(52.37, 9.72)))
    assert "maps/dir/?api=1&origin=Hildesheim&destination=52.37%2C9.72&travelmode=transit" in text
    assert "maps/dir/?api=1&origin=52.37%2C9.72&destination=Hildesheim&travelmode=transit" in text
    assert "destination=Hannover" not in text
    assert "origin=Hannover" not in text


def test_als_text_ohne_wohnort_oder_zielort_zeigt_keinen_hinreise_link():
    text = als_text(_basis_plan())
    assert "maps/dir" not in text


def test_als_html_zeigt_etappen_und_hinreise_routen_link():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="walking")
    html_text = als_html(_basis_plan(
        tagesrouten=[Tagesroute(besuche=[besuch])], unterkunft_koordinaten=(48.0, 11.0),
        wohnort="Hildesheim", zielort="Hannover",
    ))
    assert "Route in Google Maps ansehen" in html_text
    # Hinreise-Link zeigt auf die GENAUE Unterkunft (Koordinaten), nicht mehr nur den groben
    # Zielort-Namen, siehe test_als_text_bevorzugt_praezise_unterkunft_fuer_hinreise_link.
    assert "maps/dir/?api=1&amp;origin=Hildesheim&amp;destination=48.0%2C11.0&amp;travelmode=transit" in html_text


def test_als_kartendaten_zeigt_routen_link_je_besuch():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="driving")
    daten = als_kartendaten(_basis_plan(
        tagesrouten=[Tagesroute(besuche=[besuch])], unterkunft_koordinaten=(48.0, 11.0),
    ), lambda _pid: None)
    link = daten["tage"][0]["besuche"][0]["routen_link"]
    assert "travelmode=driving" in link


def test_als_text_zeigt_verkehrsmittel_je_etappe():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="bicycling")
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[besuch])]))
    assert "→ 15 Min. (mit dem Fahrrad) von Unterkunft" in text


def test_als_text_ohne_anfahrt_modus_zeigt_keine_klammer():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)  # anfahrt_modus bleibt None
    text = als_text(_basis_plan(tagesrouten=[Tagesroute(besuche=[besuch])]))
    assert "→ 15 Min. von Unterkunft" in text
    assert "(" not in text.split("→ 15 Min.")[1].split("von Unterkunft")[0]


def test_als_html_zeigt_verkehrsmittel_je_etappe():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="transit")
    html_text = als_html(_basis_plan(tagesrouten=[Tagesroute(besuche=[besuch])]))
    assert "mit öffentlichen Verkehrsmitteln" in html_text


def test_als_kartendaten_zeigt_verkehrsmittel_je_besuch():
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195, anfahrt_modus="driving")
    daten = als_kartendaten(_basis_plan(tagesrouten=[Tagesroute(besuche=[besuch])]), lambda _pid: None)
    assert daten["tage"][0]["besuche"][0]["verkehrsmittel"] == "mit dem Auto"


def test_als_text_ohne_kostenschaetzung_zeigt_nichts():
    text = als_text(_basis_plan())
    assert "Geschätzte Gesamtkosten" not in text


def test_als_text_zeigt_kostenschaetzung_im_rahmen_des_budgets():
    text = als_text(_basis_plan(geschaetzte_kosten_euro=500.0, budget_gesamt=800.0))
    assert "ca. 500 €" in text
    assert "im Rahmen Ihres angegebenen Budgets von 800 €" in text
    assert "300 € Puffer" in text


def test_als_text_zeigt_kostenschaetzung_ueber_dem_budget():
    text = als_text(_basis_plan(geschaetzte_kosten_euro=900.0, budget_gesamt=800.0))
    assert "übersteigt Ihr angegebenes Budget von 800 €" in text
    assert "100 €" in text


def test_als_text_ohne_budget_zeigt_nur_die_schaetzung():
    text = als_text(_basis_plan(geschaetzte_kosten_euro=500.0))
    assert "ca. 500 €" in text
    assert "Budget" not in text


def test_als_text_kennzeichnet_unvollstaendige_kostenschaetzung():
    text = als_text(_basis_plan(geschaetzte_kosten_euro=500.0, kosten_unvollstaendig=True))
    assert "unvollständig" in text


def test_als_html_zeigt_kostenschaetzung():
    html_text = als_html(_basis_plan(geschaetzte_kosten_euro=500.0, budget_gesamt=800.0))
    assert "ca. 500 €" in html_text
    assert "im Rahmen Ihres angegebenen Budgets" in html_text


def test_als_kartendaten_baut_unterkunft_und_tageskarten_mit_foto_url():
    poi_mit_foto = POI(id=1, name="Kletterroute XY", kategorie="klettern", x=0.0, y=0.0, score=3.0,
                        required_time=180, opening=0, closing=600, place_id="poi-1")
    tag1 = Tagesroute(besuche=[Besuch(poi=poi_mit_foto, ankunft=15, wartezeit=0, abfahrt=195)])
    plan = _basis_plan(tagesrouten=[tag1], unterkunft_name="Hotel Zentral", unterkunft_place_id="hotel-1")

    daten = als_kartendaten(plan, lambda place_id: f"/fotos/{place_id}.jpg" if place_id else None)

    assert daten["unterkunft"]["name"] == "Hotel Zentral"
    assert daten["unterkunft"]["foto_url"] == "/fotos/hotel-1.jpg"
    assert len(daten["tage"]) == 1
    assert daten["tage"][0]["tag"] == 1
    assert daten["tage"][0]["ankunftstag"] is True
    besuch_karte = daten["tage"][0]["besuche"][0]
    assert besuch_karte["name"] == "Kletterroute XY"
    assert besuch_karte["kategorie"] == "klettern"
    assert besuch_karte["foto_url"] == "/fotos/poi-1.jpg"
    assert "query_place_id=poi-1" in besuch_karte["maps_link"]


def test_als_kartendaten_ohne_unterkunft_liefert_none():
    daten = als_kartendaten(_basis_plan(), lambda _place_id: None)
    assert daten["unterkunft"] is None
    assert daten["tage"] == []


def test_als_kartendaten_ohne_foto_liefert_keine_foto_url():
    daten = als_kartendaten(_basis_plan(unterkunft_name="Hotel Zentral"), lambda _place_id: None)
    assert daten["unterkunft"]["foto_url"] is None


def test_als_kartendaten_zeigt_hinreise_und_rueckreise_getrennt():
    # Regression (Live-Vorfall, Nutzerfeedback): die Rückreise war früher literal dieselbe
    # `BewerteteAlternative` wie die Hinreise (siehe pipeline.py-Fix) – hier wird geprüft, dass die
    # Web-Kartendaten beide unabhängig voneinander abbilden, statt eine Seite zu duplizieren.
    rueck = BewerteteAlternative(
        alternative=ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=280, kosten_euro=90, distanz_km=500),
        co2_kg=20.0, score=0.4,
    )
    daten = als_kartendaten(_basis_plan(hinreise=_BAHN, rueckreise=rueck), lambda _pid: None)
    assert daten["hinreise"]["name"] == "Hinreise: Bahn"
    assert daten["rueckreise"]["name"] == "Rückreise: Auto"


def test_als_kartendaten_zeigt_vorschlaege_an_leerem_tag():
    empfehlung = POI(id=9, name="Aussichtspunkt Nord", kategorie="natur", x=0.0, y=0.0, score=1.0,
                      required_time=60, opening=0, closing=600)
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[])], weitere_aktivitaeten_empfehlungen=[empfehlung],
    )
    daten = als_kartendaten(plan, lambda _pid: None)
    vorschlaege = daten["tage"][0]["vorschlaege"]
    assert daten["tage"][0]["besuche"] == []
    assert vorschlaege[0]["name"] == "Aussichtspunkt Nord"
    assert vorschlaege[0]["label"] == "Vorschlag (nicht eingeplant)"


def test_als_kartendaten_zeigt_markt_und_restaurant_vorschlaege_am_vollen_mittleren_tag():
    markt_poi = POI(id=10, name="Wochenmarkt Zentral", kategorie="markt", x=0.0, y=0.0, score=1.0,
                     required_time=30, opening=0, closing=600, besuchsklasse="kaffee")
    restaurant_poi = POI(id=11, name="Kneipe Ecke", kategorie="bar", x=0.0, y=0.0, score=1.0,
                          required_time=60, opening=0, closing=600, besuchsklasse="bar")
    besuch = Besuch(poi=_POI, ankunft=15, wartezeit=0, abfahrt=195)
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[]), Tagesroute(besuche=[besuch]), Tagesroute(besuche=[])],
        markt_beispiele=[markt_poi], beispielrestaurants=[restaurant_poi],
    )
    daten = als_kartendaten(plan, lambda _pid: None)
    tag2_vorschlaege = {v["name"]: v["label"] for v in daten["tage"][1]["vorschlaege"]}
    assert tag2_vorschlaege["Wochenmarkt Zentral"] == "Vorschlag: mittags Markt/Café"
    assert tag2_vorschlaege["Kneipe Ecke"] == "Vorschlag: abends essen gehen"
    # Anreise- und Abreisetag bekommen KEINEN Markt-Vorschlag (siehe _markt_beispiele_fuer_tag).
    assert "Wochenmarkt Zentral" not in {v["name"] for v in daten["tage"][0]["vorschlaege"]}
    assert "Wochenmarkt Zentral" not in {v["name"] for v in daten["tage"][2]["vorschlaege"]}


def test_als_kartendaten_zeigt_sondertag_beispiele_als_vorschlag():
    tour_poi = POI(id=12, name="Stadtführung Altstadt", kategorie="tour", x=0.0, y=0.0, score=1.0,
                    required_time=120, opening=0, closing=600, nutzerinteresse="Tour")
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[]), Tagesroute(besuche=[])],
        tour_tag_beispiele=[tour_poi], tour_tage_anzahl=1,
    )
    daten = als_kartendaten(plan, lambda _pid: None)
    sondertag = daten["tage"][1]
    assert sondertag["besuche"] == []
    assert sondertag["vorschlaege"][0]["name"] == "Stadtführung Altstadt"
    assert "geführte Tour" in sondertag["vorschlaege"][0]["label"]


def test_als_kartendaten_zeigt_keine_restaurant_vorschlaege_am_sondertag():
    # Regression (Nutzerfeedback nach Live-Test): an einem reservierten Tour-Tag sollen KEINE
    # Beispielrestaurants/Markt-Vorschläge auftauchen ("da ist nur Tour").
    tour_poi = POI(id=13, name="Bootstour Hafen", kategorie="tour", x=0.0, y=0.0, score=1.0,
                   required_time=120, opening=0, closing=600, nutzerinteresse="Tour")
    restaurant_poi = POI(id=14, name="Restaurant Ecke", kategorie="restaurant", x=0.0, y=0.0, score=1.0,
                          required_time=60, opening=0, closing=600, besuchsklasse="mahlzeit")
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[]), Tagesroute(besuche=[])],
        tour_tag_beispiele=[tour_poi], tour_tage_anzahl=1, beispielrestaurants=[restaurant_poi],
    )
    daten = als_kartendaten(plan, lambda _pid: None)
    namen = {v["name"] for v in daten["tage"][1]["vorschlaege"]}
    assert namen == {"Bootstour Hafen"}


def test_als_text_reserviert_mehrere_tour_tage_bei_explizitem_wunsch():
    tour_poi = POI(id=15, name="Wanderung Bergtour", kategorie="tour", x=0.0, y=0.0, score=1.0,
                    required_time=180, opening=0, closing=600, nutzerinteresse="Tour")
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[]) for _ in range(3)],
        tour_tag_beispiele=[tour_poi], tour_tage_anzahl=2,
    )
    text = als_text(plan)
    tag2 = text.split("Tag 2")[1].split("Tag 3")[0]
    tag3 = text.split("Tag 3")[1]
    assert "Für diesen Tag empfehlen wir eine geführte Tour" in tag2
    assert "Für diesen Tag empfehlen wir eine geführte Tour" in tag3


def test_als_text_zeigt_keine_beispielrestaurants_an_reserviertem_tour_tag():
    tour_poi = POI(id=16, name="Altstadtführung", kategorie="tour", x=0.0, y=0.0, score=1.0,
                    required_time=120, opening=0, closing=600, nutzerinteresse="Tour")
    restaurant_poi = POI(id=17, name="Trattoria Ecke", kategorie="restaurant", x=0.0, y=0.0, score=1.0,
                          required_time=60, opening=0, closing=600, besuchsklasse="mahlzeit")
    plan = _basis_plan(
        tagesrouten=[Tagesroute(besuche=[])],
        tour_tag_beispiele=[tour_poi], tour_tage_anzahl=1, beispielrestaurants=[restaurant_poi],
    )
    text = als_text(plan)
    assert "Altstadtführung" in text
    assert "Trattoria Ecke" not in text
    assert "Beispielrestaurants" not in text


def test_speichere_poi_uebersicht_ohne_kandidaten_schreibt_nur_kopfzeile(tmp_path):
    pfad = tmp_path / "pois.csv"
    speichere_poi_uebersicht(_basis_plan(), pfad)
    with pfad.open(encoding="utf-8-sig", newline="") as datei:
        zeilen = list(csv.reader(datei, delimiter=";"))
    assert len(zeilen) == 1  # nur die Kopfzeile
    assert zeilen[0][0] == "tag"

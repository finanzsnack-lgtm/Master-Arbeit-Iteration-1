"""Tests für Optimierung 1 (Greedy-Konstruktion + ILS)."""
from src.api.typen import POI
from src.optimierung.toptw import TOPTWInstanz, iterated_local_search, plane_gesamte_reise, simuliere_route


def _beispiel_pois() -> list[POI]:
    return [
        POI(id=1, name="Museum", kategorie="kultur", x=0.01, y=0.0, score=5,
            required_time=60, opening=0, closing=600),
        POI(id=2, name="Park", kategorie="natur", x=0.02, y=0.0, score=3,
            required_time=30, opening=0, closing=600),
        POI(id=3, name="Restaurant", kategorie="kulinarik", x=0.0, y=0.01, score=4,
            required_time=45, opening=300, closing=600),
    ]


def test_ils_ergebnis_ist_eine_gueltige_route():
    instanz = TOPTWInstanz(pois=_beispiel_pois(), tagesbudget_minuten=120, anzahl_tage=1)
    route = iterated_local_search(instanz, instanz.pois, max_ohne_verbesserung=10, zufalls_seed=1)
    reihenfolge = [besuch.poi for besuch in route.besuche]
    # Re-Simulation muss dasselbe Ergebnis wie die interne Berechnung liefern
    # (Zeitfenster & Tagesbudget werden nicht verletzt).
    assert simuliere_route(instanz, reihenfolge) is not None


def test_ils_liefert_score_groesser_gleich_null():
    instanz = TOPTWInstanz(pois=_beispiel_pois(), tagesbudget_minuten=500, anzahl_tage=1)
    route = iterated_local_search(instanz, instanz.pois, max_ohne_verbesserung=20, zufalls_seed=42)
    assert route.score >= 0


def test_zeitfenster_wird_nicht_verletzt():
    # Der POI liegt so weit vom Depot entfernt, dass allein die Anreise das
    # enge Zeitfenster (closing=5 Minuten) sprengt.
    pois = [POI(id=1, name="Weit weg", kategorie="test", x=0.5, y=0.5, score=10,
                required_time=10, opening=0, closing=5)]
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=1000, anzahl_tage=1)
    assert simuliere_route(instanz, pois) is None


def test_tagesbudget_wird_nicht_verletzt():
    pois = [POI(id=1, name="Weit weg", kategorie="test", x=0.5, y=0.5, score=10,
                required_time=10, opening=0, closing=10000)]
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=5, anzahl_tage=1)
    assert simuliere_route(instanz, pois) is None


def test_geschwindigkeit_kmh_beeinflusst_reisezeit():
    # Schnelleres Fortbewegungsmittel (siehe Projektkonversation: F14-Radius/Tempo) -> kürzere Reisezeit
    # zwischen denselben zwei Punkten.
    a = POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=0, opening=0, closing=600)
    b = POI(id=2, name="B", kategorie="test", x=0.1, y=0.0, score=1, required_time=0, opening=0, closing=600)
    zu_fuss = TOPTWInstanz(pois=[a, b], tagesbudget_minuten=600, anzahl_tage=1, geschwindigkeit_kmh=4.5)
    mit_auto = TOPTWInstanz(pois=[a, b], tagesbudget_minuten=600, anzahl_tage=1, geschwindigkeit_kmh=40.0)
    assert mit_auto.reisezeit_minuten(a, b) < zu_fuss.reisezeit_minuten(a, b)


def test_max_aktivitaetszeit_minuten_wird_nicht_verletzt():
    # Regression (siehe Projektkonversation: "da wurden zehn Stunden Aktivitäten geplant, das macht
    # ja keiner") – reine Besuchszeit (ohne Fahrzeit) darf `max_aktivitaetszeit_minuten` nicht
    # überschreiten, selbst wenn im Gesamtbudget (inkl. Fahrzeit) noch Platz wäre.
    pois = [
        POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=200, opening=0, closing=600),
        POI(id=2, name="B", kategorie="test", x=0.001, y=0.0, score=1, required_time=200, opening=0, closing=600),
    ]
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=600, anzahl_tage=1, max_aktivitaetszeit_minuten=360)
    # Beide POIs zusammen (400 Min. Besuchszeit) verletzen die 360-Minuten-Aktivitätszeit-Grenze.
    assert simuliere_route(instanz, pois) is None
    # Ein einzelner POI (200 Min.) verletzt sie nicht.
    assert simuliere_route(instanz, [pois[0]]) is not None


def test_max_aktivitaetszeit_minuten_default_schraenkt_bestehende_aufrufer_nicht_ein():
    # Default ist bewusst sehr groß (siehe TOPTWInstanz-Doku), damit Aufrufer ohne explizite Angabe
    # (z.B. ältere Tests) unverändert funktionieren.
    pois = _beispiel_pois()
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=600, anzahl_tage=1)
    assert simuliere_route(instanz, pois) is not None


def test_plane_gesamte_reise_ohne_tagesbudget_je_tag_nutzt_instanz_budget():
    pois = _beispiel_pois()
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=500, anzahl_tage=2)
    tagesrouten = plane_gesamte_reise(instanz, max_ohne_verbesserung=10)
    assert len(tagesrouten) == 2


def test_simuliere_route_lehnt_zwei_mahlzeiten_zu_dicht_hintereinander_ab():
    # Regression (siehe Projektkonversation: "ich möchte nicht um 13:13 essen und um 14:07 schon
    # wieder in einem Restaurant sitzen") – zwei "mahlzeit"-Besuche brauchen den Standard-
    # Mindestabstand von 4h (siehe toptw.py `_STANDARD_MINDESTABSTAND_MINUTEN`).
    restaurant_a = POI(id=1, name="Restaurant A", kategorie="restaurant", x=0.0, y=0.0, score=1,
                        required_time=60, opening=0, closing=600, besuchsklasse="mahlzeit")
    restaurant_b = POI(id=2, name="Restaurant B", kategorie="restaurant", x=0.001, y=0.0, score=1,
                        required_time=60, opening=0, closing=600, besuchsklasse="mahlzeit")
    instanz = TOPTWInstanz(pois=[restaurant_a, restaurant_b], tagesbudget_minuten=600, anzahl_tage=1)
    # restaurant_b läge (Fahrzeit + required_time von A eingerechnet) deutlich unter 4h nach A.
    assert simuliere_route(instanz, [restaurant_a, restaurant_b]) is None


def test_simuliere_route_erlaubt_mahlzeiten_mit_ausreichend_abstand():
    restaurant_a = POI(id=1, name="Restaurant A", kategorie="restaurant", x=0.0, y=0.0, score=1,
                        required_time=60, opening=0, closing=1000, besuchsklasse="mahlzeit")
    restaurant_b = POI(id=2, name="Restaurant B", kategorie="restaurant", x=0.001, y=0.0, score=1,
                        required_time=60, opening=4 * 60 + 61, closing=1000, besuchsklasse="mahlzeit")
    instanz = TOPTWInstanz(pois=[restaurant_a, restaurant_b], tagesbudget_minuten=1000, anzahl_tage=1)
    # restaurant_b öffnet erst deutlich mehr als 4h nach dem Ende von restaurant_a -> zulässig.
    assert simuliere_route(instanz, [restaurant_a, restaurant_b]) is not None


def test_simuliere_route_erlaubt_kaffee_direkt_nach_dem_restaurant():
    # Explizit gewünschte Ausnahme (siehe Projektkonversation: "ein Kaffee darf natürlich auch nach
    # dem Restaurant kommen, 30 Minuten später reicht") – KEIN Mindestabstand zwischen
    # "mahlzeit" und "kaffee".
    restaurant = POI(id=1, name="Restaurant", kategorie="restaurant", x=0.0, y=0.0, score=1,
                      required_time=60, opening=0, closing=600, besuchsklasse="mahlzeit")
    cafe = POI(id=2, name="Café", kategorie="cafe", x=0.001, y=0.0, score=1,
               required_time=30, opening=0, closing=600, besuchsklasse="kaffee")
    instanz = TOPTWInstanz(pois=[restaurant, cafe], tagesbudget_minuten=600, anzahl_tage=1)
    assert simuliere_route(instanz, [restaurant, cafe]) is not None


def test_simuliere_route_lehnt_kaffee_und_bar_zu_dicht_hintereinander_ab():
    cafe = POI(id=1, name="Café", kategorie="cafe", x=0.0, y=0.0, score=1,
               required_time=30, opening=0, closing=600, besuchsklasse="kaffee")
    bar = POI(id=2, name="Bar", kategorie="bar", x=0.001, y=0.0, score=1,
              required_time=60, opening=0, closing=600, besuchsklasse="bar")
    instanz = TOPTWInstanz(pois=[cafe, bar], tagesbudget_minuten=600, anzahl_tage=1)
    assert simuliere_route(instanz, [cafe, bar]) is None


def test_simuliere_route_ohne_besuchsklasse_bleibt_unbeschraenkt():
    # POIs ohne Besuchsklasse (Standardfall, z.B. Museum/Park) sind von KEINEM Mindestabstand
    # betroffen – Regressionsschutz, dass bestehende Aufrufer/Tests unverändert funktionieren.
    pois = _beispiel_pois()
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=600, anzahl_tage=1)
    assert simuliere_route(instanz, pois) is not None


def test_reisezeit_minuten_bevorzugt_echte_matrix_vor_luftlinie():
    # Regression (siehe Projektkonversation: "die Zeiten sind falsch") – mit einer echten,
    # vorab abgerufenen Reisezeit (siehe aufbereitung.py `hole_reisezeitmatrix`) wird NICHT mehr
    # die Luftlinien-Schätzung verwendet.
    a = POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=0, opening=0, closing=600)
    b = POI(id=2, name="B", kategorie="test", x=0.001, y=0.0, score=1, required_time=0, opening=0, closing=600)
    instanz = TOPTWInstanz(
        pois=[a, b], tagesbudget_minuten=600, anzahl_tage=1,
        reisezeiten_minuten={(1, 2): 42},
    )
    assert instanz.reisezeit_minuten(a, b) == 42


def test_reisezeit_minuten_faellt_bei_fehlendem_matrix_eintrag_auf_luftlinie_zurueck():
    # Fehlt EIN Paar in der Matrix (z.B. Google fand keine Route), bricht nichts ab – nur dieses
    # Paar nutzt die Luftlinien-Schätzung.
    a = POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=0, opening=0, closing=600)
    b = POI(id=2, name="B", kategorie="test", x=0.1, y=0.0, score=1, required_time=0, opening=0, closing=600)
    instanz = TOPTWInstanz(pois=[a, b], tagesbudget_minuten=600, anzahl_tage=1, reisezeiten_minuten={})
    assert instanz.reisezeit_minuten(a, b) > 0  # Luftlinien-Fallback, kein Absturz/0


def test_simuliere_route_fuegt_pause_nach_intervall_ein():
    # Regression (siehe Projektkonversation: "Pausen eingeplant werden" bei eingeschränkter
    # Gehfähigkeit) – nach `pause_intervall_minuten` kumulierter Zeit wird vor dem nächsten Besuch
    # zusätzlich `pause_dauer_minuten` gewartet.
    a = POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=120, opening=0, closing=1000)
    b = POI(id=2, name="B", kategorie="test", x=0.001, y=0.0, score=1, required_time=30, opening=0, closing=1000)
    instanz = TOPTWInstanz(
        pois=[a, b], tagesbudget_minuten=1000, anzahl_tage=1,
        pause_intervall_minuten=120, pause_dauer_minuten=20,
    )
    route = simuliere_route(instanz, [a, b])
    # a required_time=120 -> kumulierte Zeit beim Erreichen von b bereits >= 120 -> Pause vor b.
    assert route.besuche[1].wartezeit >= 20


def test_simuliere_route_ohne_pause_intervall_bleibt_unveraendert():
    a = POI(id=1, name="A", kategorie="test", x=0.0, y=0.0, score=1, required_time=100, opening=0, closing=1000)
    b = POI(id=2, name="B", kategorie="test", x=0.001, y=0.0, score=1, required_time=30, opening=0, closing=1000)
    instanz = TOPTWInstanz(pois=[a, b], tagesbudget_minuten=1000, anzahl_tage=1)  # pause_intervall_minuten=None (Default)
    route = simuliere_route(instanz, [a, b])
    assert route.besuche[1].wartezeit == 0


def test_simuliere_route_haelt_max_pois_pro_tag_ein():
    # Regression (siehe Projektkonversation: "wenn er sagt, er möchte flexibler sein, dann setzt
    # man nur ein gewisses Fenster an POIs in einen Tag" – F05 Flexibilitätspräferenz). Drei kurze,
    # zeitlich problemlos passende POIs, aber Obergrenze 2 pro Tag.
    pois = [
        POI(id=i, name=f"POI {i}", kategorie="test", x=0.001 * i, y=0.0, score=1,
            required_time=10, opening=0, closing=1000)
        for i in range(1, 4)
    ]
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=1000, anzahl_tage=1, max_pois_pro_tag=2)
    assert simuliere_route(instanz, pois) is None  # 3 POIs > Obergrenze 2 -> ungültig
    assert simuliere_route(instanz, pois[:2]) is not None  # 2 POIs <= Obergrenze -> gültig


def test_simuliere_route_ohne_max_pois_pro_tag_unbeschraenkt():
    pois = [
        POI(id=i, name=f"POI {i}", kategorie="test", x=0.001 * i, y=0.0, score=1,
            required_time=10, opening=0, closing=1000)
        for i in range(1, 4)
    ]
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=1000, anzahl_tage=1)  # max_pois_pro_tag=None (Default)
    route = simuliere_route(instanz, pois)
    assert route is not None
    assert len(route.besuche) == 3


def test_plane_gesamte_reise_mit_verkuerztem_tag1_budget_plant_dort_weniger_ein():
    # Simuliert eine sehr lange Hinreise (siehe pipeline.py): Tag 1 bleibt praktisch ohne Budget,
    # Tag 2 hat das volle Budget und kann trotzdem etwas einplanen.
    pois = _beispiel_pois()
    instanz = TOPTWInstanz(pois=pois, tagesbudget_minuten=500, anzahl_tage=2)

    tagesrouten = plane_gesamte_reise(instanz, max_ohne_verbesserung=10, tagesbudget_je_tag=[0, 500])

    assert tagesrouten[0].besuche == []  # kein Budget übrig -> nichts eingeplant
    assert len(tagesrouten[1].besuche) > 0  # volles Budget -> POIs werden eingeplant

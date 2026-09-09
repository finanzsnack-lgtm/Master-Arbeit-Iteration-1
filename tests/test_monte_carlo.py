"""Tests für den Monte-Carlo-Härtetest (An-/Abreise-Umstiege, siehe monte_carlo.py)."""
from src.api.typen import Teilstrecke
from src.optimierung.monte_carlo import haertetest_teilstrecken


def test_haertetest_liefert_quote_zwischen_0_und_1():
    teilstrecken = [
        Teilstrecke(modus="TRANSIT", linie="RE 1", von="A", nach="B", dauer_minuten=30, wartezeit_minuten=None),
        Teilstrecke(modus="TRANSIT", linie="RE 2", von="B", nach="C", dauer_minuten=30, wartezeit_minuten=10),
    ]
    ergebnis = haertetest_teilstrecken(teilstrecken, anzahl_laeufe=100, zufalls_seed=1)
    assert 0.0 <= ergebnis.quote_ohne_verletzung <= 1.0
    assert ergebnis.laeufe == 100


def test_grosszuegiger_umstiegspuffer_ist_robust():
    teilstrecken = [
        Teilstrecke(modus="TRANSIT", linie="RE 1", von="A", nach="B", dauer_minuten=30, wartezeit_minuten=None),
        Teilstrecke(modus="TRANSIT", linie="RE 2", von="B", nach="C", dauer_minuten=30, wartezeit_minuten=60),
    ]
    ergebnis = haertetest_teilstrecken(teilstrecken, anzahl_laeufe=200, unsicherheitsfaktor=0.1, zufalls_seed=1)
    assert ergebnis.ist_robust


def test_umstiegspuffer_null_erkennt_verpassten_anschluss():
    # Kein Puffer beim Umstieg -> jede noch so kleine positive Störung der ersten Teilstrecke
    # verpasst den Anschluss. Beweist (analog zur früheren POI-Variante), dass der Mechanismus
    # Verletzungen tatsächlich erkennt statt immer "robust" zu melden.
    teilstrecken = [
        Teilstrecke(modus="TRANSIT", linie="RE 1", von="A", nach="B", dauer_minuten=30, wartezeit_minuten=None),
        Teilstrecke(modus="TRANSIT", linie="RE 2", von="B", nach="C", dauer_minuten=30, wartezeit_minuten=0),
    ]
    ergebnis = haertetest_teilstrecken(teilstrecken, anzahl_laeufe=2000, zufalls_seed=1)
    assert ergebnis.verletzungen > 0
    assert not ergebnis.ist_robust


def test_teilstrecke_ohne_wartezeit_ist_kein_pruefpunkt():
    # Eine TRANSIT-Teilstrecke OHNE wartezeit_minuten (z.B. die erste, ohne vorherigen Anschluss)
    # wird selbst nicht als Umstieg geprüft – nur ihre Störung fließt in die nächste Prüfung ein.
    teilstrecken = [
        Teilstrecke(modus="TRANSIT", linie="RE 1", von="A", nach="B", dauer_minuten=30, wartezeit_minuten=None),
    ]
    ergebnis = haertetest_teilstrecken(teilstrecken, anzahl_laeufe=200, zufalls_seed=1)
    assert ergebnis.verletzungen == 0
    assert ergebnis.ist_robust


def test_leere_teilstreckenliste_ist_robust():
    ergebnis = haertetest_teilstrecken([], anzahl_laeufe=50, zufalls_seed=1)
    assert ergebnis.verletzungen == 0
    assert ergebnis.ist_robust

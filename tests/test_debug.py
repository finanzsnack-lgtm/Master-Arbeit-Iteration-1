"""Tests für die Planungs-Debug-Ausgabe (src/ausgabe/debug.py), siehe pruefe_planung.py."""
from src.api.typen import POI, Teilstrecke
from src.ausgabe.debug import PlanungsDebugSammlung, schreibe_debug_datei
from src.optimierung.monte_carlo import RobustheitsErgebnis
from src.optimierung.toptw import Besuch, Tagesroute, TOPTWInstanz


def _poi(name: str, preisniveau: int | None = None, nutzerinteresse: str | None = None) -> POI:
    return POI(id=1, name=name, kategorie="museum", x=0.0, y=0.0, score=3.0, required_time=60,
               opening=0, closing=600, preisniveau=preisniveau, nutzerinteresse=nutzerinteresse)


def test_schreibe_debug_datei_zeigt_alle_fuenf_abschnitte(tmp_path):
    sammlung = PlanungsDebugSammlung(
        rohe_pois=[_poi("Museum A", nutzerinteresse="Kultur"), _poi("Museum B")],
        pois_nach_harten_einschraenkungen=[_poi("Museum A", nutzerinteresse="Kultur")],
        ausgewaehlte_pois=[_poi("Museum A", nutzerinteresse="Kultur")],
        toptw_instanz=TOPTWInstanz(pois=[], tagesbudget_minuten=480, anzahl_tage=1),
        tagesrouten=[Tagesroute(besuche=[Besuch(poi=_poi("Museum A"), ankunft=10, wartezeit=0, abfahrt=70, anfahrt_modus="walking")])],
        hinreise_teilstrecken=[
            Teilstrecke(modus="TRANSIT", linie="RE 1", von="Heimatort", nach="Zielort",
                        dauer_minuten=90, wartezeit_minuten=10),
        ],
        hinreise_robustheit=RobustheitsErgebnis(laeufe=1000, verletzungen=50, quote_ohne_verletzung=0.95, schwelle=0.95),
    )
    pfad = tmp_path / "debug.txt"

    schreibe_debug_datei(sammlung, pfad)
    text = pfad.read_text(encoding="utf-8")

    assert "1. Roh-Treffer" in text
    assert "Museum A" in text and "Museum B" in text
    assert "2. Nach harten Einschränkungen" in text
    assert "3. AN OPTIMIERUNG 1 WEITERGEGEBEN" in text
    assert "4. ERGEBNIS OPTIMIERUNG 1" in text
    assert "Anfahrt: walking" in text
    assert "5. MONTE-CARLO-HÄRTETEST" in text
    assert "Heimatort -> Zielort" in text
    assert "1000 Läufe, 50 mit verpasstem Anschluss" in text
    assert "95.0%" in text
    assert "robust" in text


def test_schreibe_debug_datei_ohne_haertetest_zeigt_ehrliche_fehlanzeige(tmp_path):
    sammlung = PlanungsDebugSammlung()  # komplett leer, z.B. wenn nichts gefunden wurde
    pfad = tmp_path / "debug.txt"

    schreibe_debug_datei(sammlung, pfad)
    text = pfad.read_text(encoding="utf-8")

    assert "(keine)" in text
    assert "(keine Tagesrouten)" in text
    assert "(kein Härtetest gelaufen)" in text


def test_schreibe_debug_datei_zeigt_preisniveau_wenn_vorhanden(tmp_path):
    sammlung = PlanungsDebugSammlung(rohe_pois=[_poi("Museum A", preisniveau=2)])
    pfad = tmp_path / "debug.txt"

    schreibe_debug_datei(sammlung, pfad)
    text = pfad.read_text(encoding="utf-8")

    assert "Preisniveau 2/4" in text

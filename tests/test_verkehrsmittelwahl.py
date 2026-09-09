"""Tests für Optimierung 2 (gewichtete Verkehrsmittelwahl) und den Nachhaltigkeits-Nudge."""
from src.api.typen import ReiseAlternative
from src.optimierung.verkehrsmittelwahl import bewerte_alternativen, nachhaltigkeits_nudge


def test_bahn_wird_bei_gleicher_zeit_und_kosten_wegen_co2_bevorzugt():
    alternativen = [
        ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
        ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    ]
    bewertete = bewerte_alternativen(alternativen)
    assert bewertete[0].alternative.verkehrsmittel == "Bahn"


def test_nudge_wird_erzeugt_wenn_bahn_langsamer_aber_sauberer_ist():
    alternativen = [
        ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=240, kosten_euro=60, distanz_km=500),
        ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    ]
    bewertete = bewerte_alternativen(alternativen)
    nudge = nachhaltigkeits_nudge(bewertete)
    assert nudge is not None
    assert "Bahn" in nudge


def test_kein_nudge_wenn_bahn_bereits_die_beste_option_ist():
    alternativen = [
        ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=200, kosten_euro=50, distanz_km=500),
        ReiseAlternative(verkehrsmittel="Auto", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    ]
    bewertete = bewerte_alternativen(alternativen)
    assert nachhaltigkeits_nudge(bewertete) is None

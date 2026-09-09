"""Tests für die harte Einschränkungs-Prüfung (src/datenaufbereitung/vertraeglichkeit.py)."""
from src.api.typen import POI, Unterkunft
from src.datenaufbereitung.vertraeglichkeit import (
    filtere_pois_hart,
    filtere_unterkuenfte_barrierefrei,
    pruefe_barrierefreiheit_des_plans,
)
from src.fragekatalog.schema import ReiseAnfrage


class _FakeClient:
    """Simuliert `MapsClient.ist_barrierefrei` über eine feste place_id -> Status-Zuordnung."""

    def __init__(self, status_je_place_id: dict[str, bool | None]):
        self._status_je_place_id = status_je_place_id

    def ist_barrierefrei(self, place_id):
        return self._status_je_place_id.get(place_id)


def _poi(id_, name, kategorie="restaurant", place_id=None):
    return POI(id=id_, name=name, kategorie=kategorie, x=0.0, y=0.0, score=1.0,
               required_time=60, opening=0, closing=600, place_id=place_id)


def test_filtere_pois_hart_ohne_einschraenkungen_laesst_alles_durch():
    anfrage = ReiseAnfrage()
    pois = [_poi(1, "Fischers Fritz"), _poi(2, "Trattoria Roma")]
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, _FakeClient({}))
    assert ergebnis == pois
    assert hinweise == []


def test_filtere_pois_hart_entfernt_fischrestaurant_bei_fischallergie_wenn_alternative_da():
    # Regression (siehe Projektkonversation): "wenn ich Fischallergie angebe, soll kein
    # Fischrestaurant vorgeschlagen werden".
    anfrage = ReiseAnfrage(ernaehrung_einschraenkungen=["Fischallergie"])
    pois = [_poi(1, "Fischers Fritz"), _poi(2, "Trattoria Roma")]
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, _FakeClient({}))
    assert [p.name for p in ergebnis] == ["Trattoria Roma"]
    assert hinweise == []


def test_filtere_pois_hart_behaelt_einzigen_treffer_aber_mit_hinweis():
    anfrage = ReiseAnfrage(ernaehrung_einschraenkungen=["Fischallergie"])
    pois = [_poi(1, "Fischers Fritz")]
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, _FakeClient({}))
    assert [p.name for p in ergebnis] == ["Fischers Fritz"]
    assert len(hinweise) == 1
    assert "Fischers Fritz" in hinweise[0]


def test_filtere_pois_hart_behaelt_einzigen_treffer_trotz_anderer_kategorien_daneben():
    # Ein Museum daneben ist KEINE Alternative zum Fisch-Restaurant (andere Kategorie) – der
    # einzige Restaurant-Treffer bleibt erhalten, aber mit Hinweis (kein Verschweigen des Konflikts).
    anfrage = ReiseAnfrage(ernaehrung_einschraenkungen=["Fischallergie"])
    pois = [_poi(1, "Fischers Fritz", kategorie="restaurant"), _poi(2, "Naturkundemuseum", kategorie="museum")]
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, _FakeClient({}))
    assert {p.name for p in ergebnis} == {"Fischers Fritz", "Naturkundemuseum"}
    assert len(hinweise) == 1
    assert "Fischers Fritz" in hinweise[0]


def test_filtere_pois_hart_barrierefreiheit_entfernt_nicht_zugaengliche_pois():
    anfrage = ReiseAnfrage(altersgerechte_beduerfnisse="Ich bin auf Krücken angewiesen", mobilitaetseinschraenkung_stufe="mittel")
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a"), _poi(2, "Museum B", kategorie="museum", place_id="b")]
    client = _FakeClient({"a": False, "b": True})
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client)
    assert [p.name for p in ergebnis] == ["Museum B"]
    assert hinweise == []


def test_filtere_pois_hart_barrierefreiheit_ohne_bedarf_wird_nicht_geprueft():
    anfrage = ReiseAnfrage()
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a")]
    client = _FakeClient({"a": False})
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client)
    assert ergebnis == pois  # kein Bedarf genannt -> keine Prüfung/Filterung
    assert hinweise == []


def test_filtere_pois_hart_barrierefreiheit_stufe_leicht_wird_nicht_geprueft():
    # "leicht" (z.B. altersbedingt langsameres Tempo) schließt KEINEN Ort aus – nur Tempo-/Pausen-/
    # Nähe-Anpassungen an anderer Stelle (siehe schema.py `mobilitaetseinschraenkung_stufe`).
    anfrage = ReiseAnfrage(altersgerechte_beduerfnisse="etwas langsameres Tempo", mobilitaetseinschraenkung_stufe="leicht")
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a")]
    client = _FakeClient({"a": False})
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client)
    assert ergebnis == pois
    assert hinweise == []


def test_filtere_pois_hart_barrierefreiheit_stufe_mittel_unbekannter_status_wird_nicht_ausgefiltert():
    anfrage = ReiseAnfrage(altersgerechte_beduerfnisse="Krücken", mobilitaetseinschraenkung_stufe="mittel")
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a")]
    client = _FakeClient({})  # Places hat dazu keine Angabe -> None
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client)
    assert ergebnis == pois
    assert hinweise == []


def test_filtere_pois_hart_barrierefreiheit_stufe_stark_unbekannter_status_wird_ausgefiltert():
    # "stark" (z.B. Rollstuhl): anders als "mittel" zählt ein UNBEKANNTER Status ebenfalls als
    # Ausschlussgrund (siehe schema.py) – hier bleibt Museum B übrig, weil dessen Status eindeutig
    # bestätigt ist, Museum A (unbekannter Status) fliegt raus.
    anfrage = ReiseAnfrage(altersgerechte_beduerfnisse="Rollstuhl", mobilitaetseinschraenkung_stufe="stark")
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a"), _poi(2, "Museum B", kategorie="museum", place_id="b")]
    client = _FakeClient({"b": True})  # "a" bleibt unbekannt (None)
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client)
    assert [p.name for p in ergebnis] == ["Museum B"]
    assert hinweise == []


def test_filtere_unterkuenfte_barrierefrei_entfernt_nicht_zugaengliche_wenn_alternative_da():
    anfrage = ReiseAnfrage(unterkunft_anforderungen="am liebsten barrierefrei", mobilitaetseinschraenkung_stufe="mittel")
    unterkuenfte = [
        Unterkunft(id=1, name="Hotel A", x=0.0, y=0.0, preisniveau=2, zertifiziert_nachhaltig=False, place_id="a"),
        Unterkunft(id=2, name="Hotel B", x=0.0, y=0.0, preisniveau=2, zertifiziert_nachhaltig=False, place_id="b"),
    ]
    client = _FakeClient({"a": False, "b": True})
    ergebnis, hinweise = filtere_unterkuenfte_barrierefrei(unterkuenfte, anfrage, client)
    assert [u.name for u in ergebnis] == ["Hotel B"]
    assert hinweise == []


def test_filtere_unterkuenfte_barrierefrei_behaelt_einzige_option_mit_hinweis():
    anfrage = ReiseAnfrage(unterkunft_anforderungen="am liebsten barrierefrei", mobilitaetseinschraenkung_stufe="mittel")
    unterkuenfte = [Unterkunft(id=1, name="Hotel A", x=0.0, y=0.0, preisniveau=2, zertifiziert_nachhaltig=False, place_id="a")]
    client = _FakeClient({"a": False})
    ergebnis, hinweise = filtere_unterkuenfte_barrierefrei(unterkuenfte, anfrage, client)
    assert [u.name for u in ergebnis] == ["Hotel A"]
    assert len(hinweise) == 1


def test_filtere_unterkuenfte_barrierefrei_stufe_leicht_wird_nicht_geprueft():
    anfrage = ReiseAnfrage(unterkunft_anforderungen="am liebsten barrierefrei", mobilitaetseinschraenkung_stufe="leicht")
    unterkuenfte = [Unterkunft(id=1, name="Hotel A", x=0.0, y=0.0, preisniveau=2, zertifiziert_nachhaltig=False, place_id="a")]
    client = _FakeClient({"a": False})
    ergebnis, hinweise = filtere_unterkuenfte_barrierefrei(unterkuenfte, anfrage, client)
    assert [u.name for u in ergebnis] == ["Hotel A"]
    assert hinweise == []


def test_filtere_pois_hart_strikt_entfernt_auch_ohne_alternative():
    # Zweiter Planungsversuch nach fehlgeschlagener Nachplanungs-Prüfung (siehe
    # agent_tools.py::plane_reise_und_abschliessen): anders als der normale Modus wird der
    # einzige Treffer HIER konsequent entfernt statt mit Warnhinweis behalten.
    anfrage = ReiseAnfrage(altersgerechte_beduerfnisse="Ich bin auf einen Rollstuhl angewiesen", mobilitaetseinschraenkung_stufe="stark")
    pois = [_poi(1, "Museum A", kategorie="museum", place_id="a")]
    client = _FakeClient({"a": False})
    ergebnis, hinweise = filtere_pois_hart(pois, anfrage, client, barrierefreiheit_strikt=True)
    assert ergebnis == []
    assert hinweise == []


def test_pruefe_barrierefreiheit_des_plans_findet_konflikt():
    client = _FakeClient({"a": False, "b": True})
    verletzungen = pruefe_barrierefreiheit_des_plans(["a", "b"], "b", client, mobilitaetseinschraenkung_stufe="mittel")
    assert verletzungen == ["a"]


def test_pruefe_barrierefreiheit_des_plans_ohne_konflikt_ist_leer():
    client = _FakeClient({"a": True, "b": True})
    verletzungen = pruefe_barrierefreiheit_des_plans(["a", "b"], "b", client, mobilitaetseinschraenkung_stufe="mittel")
    assert verletzungen == []


def test_pruefe_barrierefreiheit_des_plans_prueft_auch_unterkunft():
    client = _FakeClient({"unterkunft": False})
    verletzungen = pruefe_barrierefreiheit_des_plans([], "unterkunft", client, mobilitaetseinschraenkung_stufe="mittel")
    assert verletzungen == ["unterkunft"]


def test_pruefe_barrierefreiheit_des_plans_ohne_stufe_prueft_nicht():
    client = _FakeClient({"a": False})
    verletzungen = pruefe_barrierefreiheit_des_plans(["a"], None, client)
    assert verletzungen == []


def test_pruefe_barrierefreiheit_des_plans_stufe_stark_unbekannt_ist_verletzung():
    client = _FakeClient({})  # "a" bleibt unbekannt (None)
    verletzungen = pruefe_barrierefreiheit_des_plans(["a"], None, client, mobilitaetseinschraenkung_stufe="stark")
    assert verletzungen == ["a"]

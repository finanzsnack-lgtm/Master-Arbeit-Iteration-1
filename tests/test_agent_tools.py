"""
Tests für die LLM-Werkzeuge der agentischen Dialogsteuerung (src/fragekatalog/agent_tools.py) –
deterministisch, OHNE echten LLM-Aufruf. Ruft die rohen `handler`-Coroutinen der `SdkMcpTool`-
Objekte direkt auf (kein SDK-Server/keine echte Session nötig).
"""
import asyncio
from unittest.mock import patch

import pytest

from src.api.typen import POI, ReiseAlternative, Unterkunft
from src.ausgabe.debug import PlanungsDebugSammlung
from src.ausgabe.reiseplan import Reiseplan
from src.fragekatalog.agent_tools import AgentSessionState, ERLAUBTE_TOOLS, erstelle_tools, fehlende_pflichtfelder
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.toptw import Besuch, Tagesroute
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative
from src.protokoll import Protokollierer


def _rufe(tools, name, **args):
    tool = next(t for t in tools if t.name == name)
    return asyncio.run(tool.handler(args))


def _basis_state(**zusatz) -> AgentSessionState:
    parameter = {"anfrage": ReiseAnfrage(), "maps_client": _FakeClient()}
    parameter.update(zusatz)
    return AgentSessionState(**parameter)


class _FakeClient:
    def __init__(self, unterkuenfte=None, barrierefrei_je_place_id=None):
        self.letzte_kategorien: list[str] | None = None
        self._unterkuenfte = unterkuenfte or []
        self._barrierefrei_je_place_id = barrierefrei_je_place_id or {}

    def geocode(self, ort):
        return (48.0, 11.0)

    def suche_pois(self, ort, kategorien, radius_meter=3000, ernaehrung_einschraenkungen=None):
        self.letzte_kategorien = list(kategorien)
        return []

    def suche_unterkuenfte(self, ort, praeferenz_text=None):
        return list(self._unterkuenfte)

    def reisealternativen(self, von, nach):
        return [ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500)]

    def anfahrtszeiten_minuten(self, ursprung, ziele, modus="walking"):
        return [-1 for _ in ziele]

    def ist_barrierefrei(self, place_id):
        return self._barrierefrei_je_place_id.get(place_id)


def test_erlaubte_tools_stimmt_mit_erstellten_tools_ueberein():
    state = _basis_state()
    tools = erstelle_tools(state)
    erzeugte_namen = {f"mcp__reisebot__{t.name}" for t in tools}
    assert erzeugte_namen == set(ERLAUBTE_TOOLS)


def test_fehlende_pflichtfelder_ohne_angaben_listet_alle_pflichtfelder():
    anfrage = ReiseAnfrage()
    fehlend = fehlende_pflichtfelder(anfrage)
    assert "budget_gesamt" in fehlend
    assert "wohnort" in fehlend
    assert "name" in fehlend


def test_fehlende_pflichtfelder_ignoriert_optionale_felder():
    anfrage = ReiseAnfrage()
    fehlend = fehlende_pflichtfelder(anfrage)
    # F09/F10/F11/F14/F17 sind pflichtfeld=False (siehe katalog.py) -> dürfen NIE auftauchen
    assert "gesundheitliche_einschraenkungen" not in fehlend
    assert "lokaler_transport_praeferenz" not in fehlend
    assert "sicherheitsbeduerfnis" not in fehlend


def test_speichere_feld_speichert_gueltigen_string():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "speichere_feld", feld="wohnort", wert="Hannover")
    assert state.anfrage.wohnort == "Hannover"
    assert not ergebnis.get("is_error")


def test_speichere_feld_speichert_gueltiges_array():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="zielregionen", wert=["Italien", "Frankreich"])
    assert state.anfrage.zielregionen == ["Italien", "Frankreich"]


def test_speichere_feld_lehnt_falschen_typ_ab():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "speichere_feld", feld="budget_gesamt", wert="viel Geld")
    assert ergebnis.get("is_error") is True
    assert state.anfrage.budget_gesamt is None  # nicht gespeichert


def test_speichere_feld_lehnt_unbekanntes_feld_ab():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "speichere_feld", feld="lieblingsfarbe", wert="blau")
    assert ergebnis.get("is_error") is True


def test_speichere_feld_meldet_verbleibende_pflichtfelder():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "speichere_feld", feld="wohnort", wert="Hannover")
    text = ergebnis["content"][0]["text"]
    assert "Noch fehlende Pflichtfelder" in text
    assert "budget_gesamt" in text


def test_speichere_feld_uebernimmt_zuvor_gefundene_unterkunft():
    # Simuliert den echten Ablauf: hole_api_daten (siehe eigener Test unten) füllt
    # state.zuletzt_gefundene_unterkunft, speichere_feld übernimmt sie erst bei Bestätigung.
    state = _basis_state()
    state.zuletzt_gefundene_unterkunft = Unterkunft(
        id=1, name="Hotel Zentral", x=48.13, y=11.57, preisniveau=2, zertifiziert_nachhaltig=True, place_id="hz1",
    )
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="unterkunft_anforderungen", wert="zentral gelegen")
    assert state.anfrage.unterkunft_name == "Hotel Zentral"
    assert state.anfrage.unterkunft_koordinaten == (48.13, 11.57)
    assert state.anfrage.unterkunft_place_id == "hz1"
    assert state.anfrage.unterkunft_preisniveau == 2


def test_speichere_feld_ohne_zuvor_gefundene_unterkunft_laesst_felder_leer():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="unterkunft_anforderungen", wert="zentral gelegen")
    assert state.anfrage.unterkunft_name is None


def test_speichere_feld_aktivitaeten_persistiert_spezialrecherche_und_gewichtung():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="aktivitaeten_interessen", wert=["Klettern", "Shopping"],
        aktivitaeten_mit_spezialrecherche=["Klettern"], aktivitaeten_gewichtung={"Klettern": 2.0},
    )
    assert state.anfrage.aktivitaeten_mit_spezialrecherche == ["Klettern"]
    assert state.anfrage.aktivitaeten_gewichtung == {"Klettern": 2.0}


def test_speichere_feld_tagesstart_persistiert_ki_interpretierte_minuten():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="tagesstart_praeferenz", wert="ab neun bis abends um neun",
        tagesstart_minuten=540, tagesende_minuten=1260,
    )
    assert state.anfrage.tagesstart_minuten == 540
    assert state.anfrage.tagesende_minuten == 1260


def test_speichere_feld_tagesstart_ohne_interpretierbare_uhrzeit_bleibt_leer():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="tagesstart_praeferenz", wert="mal schauen")
    assert state.anfrage.tagesstart_minuten is None
    assert state.anfrage.tagesende_minuten is None


def test_speichere_feld_sicherheitsbeduerfnis_setzt_bedenklich_flag():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="sicherheitsbeduerfnis", wert="sehr wichtig", sicherheit_bedenklich=True)
    assert state.anfrage.sicherheit_bedenklich is True


def test_speichere_feld_mobilitaetseinschraenkung_stufe_wirkt_bei_beliebigem_feld():
    # NICHT auf ein Feld beschränkt (anders als sicherheit_bedenklich, siehe agent_tools.py
    # Tool-Beschreibung) – kann z.B. bei F10 (altersgerechte_beduerfnisse) genauso gesetzt werden
    # wie bei F09/F15.
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="altersgerechte_beduerfnisse",
        wert="wegen der Kinder lieber gemütlich, nicht hetzen", mobilitaetseinschraenkung_stufe="leicht",
    )
    assert state.anfrage.mobilitaetseinschraenkung_stufe == "leicht"


def test_speichere_feld_mobilitaetseinschraenkung_stufe_kann_verfeinert_werden():
    # Anders als das frühere, einmal gesetzte Bool: die Stufe kann im Gesprächsverlauf korrigiert
    # werden (z.B. "leicht" -> "stark", wenn sich ein Rollstuhlbedarf erst später herausstellt).
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="altersgerechte_beduerfnisse", wert="etwas langsam", mobilitaetseinschraenkung_stufe="leicht")
    _rufe(tools, "speichere_feld", feld="gesundheitliche_einschraenkungen", wert="Rollstuhl", mobilitaetseinschraenkung_stufe="stark")
    assert state.anfrage.mobilitaetseinschraenkung_stufe == "stark"


def test_speichere_feld_ohne_mobilitaetseinschraenkung_stufe_bleibt_none():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="altersgerechte_beduerfnisse", wert="keine besonderen Bedürfnisse")
    assert state.anfrage.mobilitaetseinschraenkung_stufe is None


def test_speichere_feld_ungueltige_mobilitaetseinschraenkung_stufe_wird_ignoriert():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="altersgerechte_beduerfnisse", wert="x",
        mobilitaetseinschraenkung_stufe="mittelschwer",  # kein gültiger Wert
    )
    assert state.anfrage.mobilitaetseinschraenkung_stufe is None


def test_speichere_feld_persistiert_ki_interpretierte_reisedaten():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="reisezeitraum_rohtext", wert="15.09. - 18.09.2026",
        reise_start_datum="2026-09-15", reise_end_datum="2026-09-18",
    )
    assert state.anfrage.reise_start_datum == "2026-09-15"
    assert state.anfrage.reise_end_datum == "2026-09-18"


def test_speichere_feld_ungueltiges_iso_datum_wird_ignoriert():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(
        tools, "speichere_feld", feld="reisezeitraum_rohtext", wert="im Sommer",
        reise_start_datum="15.09.2026", reise_end_datum="2026-09-18",  # erstes Datum nicht ISO
    )
    assert state.anfrage.reise_start_datum is None
    assert state.anfrage.reise_end_datum == "2026-09-18"


def test_speichere_feld_ohne_reisedaten_bleibt_none():
    state = _basis_state()
    tools = erstelle_tools(state)
    _rufe(tools, "speichere_feld", feld="reisezeitraum_rohtext", wert="im Sommer, unklar wie lange")
    assert state.anfrage.reise_start_datum is None
    assert state.anfrage.reise_end_datum is None


def test_hole_api_daten_liefert_text_fuer_typ_c_feld():
    state = _basis_state()
    state.anfrage.zielregionen = ["Italien"]
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="verkehrsmittel_praeferenz")
    text = ergebnis["content"][0]["text"]
    assert "Bahn" in text


def test_hole_api_daten_gibt_aktivitaeten_aktuell_an_die_suche_weiter():
    # Regression: ohne dieses Argument fiel die Suche auf das beim ersten Durchlauf noch leere
    # anfrage.aktivitaeten_interessen zurück und suchte de facto nach GAR NICHTS.
    state = _basis_state()
    state.anfrage.zielregionen = ["Italien"]
    tools = erstelle_tools(state)

    _rufe(tools, "hole_api_daten", feld="aktivitaeten_interessen", aktivitaeten_aktuell=["Restaurants", "Kultur"])

    assert state.maps_client.letzte_kategorien == ["Restaurants", "Kultur"]


def test_hole_api_daten_unterkunft_ohne_treffer_meldet_ehrlich_und_cached_nichts():
    state = _basis_state()
    state.anfrage.zielregionen = ["Italien"]
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="unterkunft_anforderungen", aktueller_wert="ruhige Lage")
    assert not ergebnis.get("is_error")
    assert state.zuletzt_gefundene_unterkunft is None


def test_hole_api_daten_unterkunft_cached_gefundene_unterkunft():
    hotel = Unterkunft(id=1, name="Hotel Zentral", x=48.13, y=11.57, preisniveau=2, zertifiziert_nachhaltig=True, place_id="hz1")
    state = _basis_state(maps_client=_FakeClient(unterkuenfte=[hotel]))
    state.anfrage.zielregionen = ["Italien"]
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="unterkunft_anforderungen", aktueller_wert="zentral")
    text = ergebnis["content"][0]["text"]
    assert "Hotel Zentral" in text
    assert state.zuletzt_gefundene_unterkunft is hotel


def test_hole_api_daten_lokaler_transport_ohne_bestaetigte_unterkunft_wartet():
    state = _basis_state()
    state.anfrage.lokaler_transport_praeferenz = "ich möchte vor Ort ein Fahrrad ausleihen"
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="lokaler_transport_praeferenz")
    text = ergebnis["content"][0]["text"]
    assert "noch nicht bestätigt" in text
    assert state.anfrage.lokaler_verleih_gewaehlt is None


def test_hole_api_daten_lehnt_nicht_typ_c_feld_ab():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="wohnort")
    assert ergebnis.get("is_error") is True


def test_hole_api_daten_lehnt_unbekanntes_feld_ab():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "hole_api_daten", feld="lieblingsfarbe")
    assert ergebnis.get("is_error") is True


def _vollstaendige_anfrage(**zusatz) -> ReiseAnfrage:
    parameter = dict(
        name="Max", email="max@example.com", reisebegleitung=["allein"], reiseleitung_gewuenscht=False,
        reisezeitraum_rohtext="3 Tage", zielregionen=["Italien"],
        wohnort="Hannover", budget_gesamt=1000.0, verkehrsmittel_praeferenz=["Bahn"],
        unterkunft_anforderungen="zentral", aktivitaeten_interessen=["Kultur"],
    )
    parameter.update(zusatz)
    anfrage = ReiseAnfrage(**parameter)
    for frage_feld in fehlende_pflichtfelder(anfrage):
        pytest.fail(f"Testvorbereitung unvollständig, Feld fehlt noch: {frage_feld}")
    return anfrage


def _leerer_plan(**zusatz) -> Reiseplan:
    bahn = BewerteteAlternative(
        alternative=ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500), co2_kg=9.5, score=0.1,
    )
    parameter = {"hinreise": bahn, "tagesrouten": [], "rueckreise": bahn}
    parameter.update(zusatz)
    return Reiseplan(**parameter)


def test_plane_reise_und_abschliessen_blockiert_bei_fehlenden_pflichtfeldern():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "plane_reise_und_abschliessen")
    assert ergebnis.get("is_error") is True
    assert state.abgeschlossen is False


def test_plane_reise_und_abschliessen_erfolgreich_bei_vollstaendigen_pflichtfeldern(tmp_path):
    anfrage = _vollstaendige_anfrage()
    plan = _leerer_plan()
    state = _basis_state(anfrage=anfrage, ausgabe_basisname=str(tmp_path / "reiseplan_test"))
    tools = erstelle_tools(state)

    with patch("src.fragekatalog.agent_tools.plane_reise", return_value=(plan, None, PlanungsDebugSammlung())), \
         patch("src.fragekatalog.agent_tools.speichere_datei") as m_datei, \
         patch("src.fragekatalog.agent_tools.speichere_json") as m_json, \
         patch("src.fragekatalog.agent_tools.speichere_poi_uebersicht") as m_poi_uebersicht, \
         patch("src.fragekatalog.agent_tools.sende_mail") as m_mail:
        ergebnis = _rufe(tools, "plane_reise_und_abschliessen")

    assert not ergebnis.get("is_error")
    assert state.abgeschlossen is True
    assert state.reiseplan is plan
    m_datei.assert_called_once()
    m_json.assert_called_once()
    m_mail.assert_called_once()
    m_poi_uebersicht.assert_called_once()
    poi_uebersicht_pfad = m_poi_uebersicht.call_args.args[1]
    assert poi_uebersicht_pfad.name == "reiseplan_test_pois.csv"


def test_plane_reise_und_abschliessen_schreibt_debug_datei_neben_dem_protokoll(tmp_path):
    # Nutzerwunsch: die Debug-Ausgabe (rohe/gefilterte/weitergegebene POIs, Optimierung-1-/
    # Härtetest-Eingabe/-Ergebnis) soll bei JEDEM echten Test entstehen (chat.py/webapp.py), nicht
    # nur über pruefe_planung.py – landet neben dem Sitzungsprotokoll (Protokollierer.pfad).
    anfrage = _vollstaendige_anfrage()
    plan = _leerer_plan()
    protokollierer = Protokollierer(pfad=tmp_path / "chat_2026-01-01_120000.jsonl")
    state = _basis_state(
        anfrage=anfrage, ausgabe_basisname=str(tmp_path / "reiseplan_test"), protokollierer=protokollierer,
    )
    tools = erstelle_tools(state)
    debug_sammlung = PlanungsDebugSammlung(rohe_pois=[
        POI(id=1, name="Museum A", kategorie="museum", x=0, y=0, score=3.0, required_time=60, opening=0, closing=600),
    ])

    with patch("src.fragekatalog.agent_tools.plane_reise", return_value=(plan, None, debug_sammlung)), \
         patch("src.fragekatalog.agent_tools.speichere_datei"), \
         patch("src.fragekatalog.agent_tools.speichere_json"), \
         patch("src.fragekatalog.agent_tools.speichere_poi_uebersicht"), \
         patch("src.fragekatalog.agent_tools.sende_mail"):
        _rufe(tools, "plane_reise_und_abschliessen")

    debug_pfad = tmp_path / "chat_2026-01-01_120000_debug.txt"
    assert debug_pfad.exists()
    inhalt = debug_pfad.read_text(encoding="utf-8")
    assert "PLANUNGS-DEBUG" in inhalt
    assert "Museum A" in inhalt


def test_plane_reise_und_abschliessen_ohne_protokollierer_schreibt_keine_debug_datei(tmp_path):
    anfrage = _vollstaendige_anfrage()
    plan = _leerer_plan()
    state = _basis_state(anfrage=anfrage, ausgabe_basisname=str(tmp_path / "reiseplan_test"))  # kein protokollierer
    tools = erstelle_tools(state)

    with patch("src.fragekatalog.agent_tools.plane_reise", return_value=(plan, None, PlanungsDebugSammlung())), \
         patch("src.fragekatalog.agent_tools.speichere_datei"), \
         patch("src.fragekatalog.agent_tools.speichere_json"), \
         patch("src.fragekatalog.agent_tools.speichere_poi_uebersicht"), \
         patch("src.fragekatalog.agent_tools.sende_mail"):
        ergebnis = _rufe(tools, "plane_reise_und_abschliessen")

    assert not ergebnis.get("is_error")  # kein Absturz ohne Protokollierer
    assert list(tmp_path.glob("*_debug.txt")) == []


def test_plane_reise_und_abschliessen_blockiert_bei_barrierefreiheits_konflikt_und_erlaubt_retry(tmp_path):
    anfrage = _vollstaendige_anfrage(altersgerechte_beduerfnisse="bitte barrierefrei", mobilitaetseinschraenkung_stufe="mittel")
    besuch_ohne_zugang = Besuch(poi=POI(
        id=1, name="Konfliktort", kategorie="museum", x=0, y=0, score=1.0, required_time=60,
        opening=0, closing=600, place_id="schlecht",
    ))
    plan_mit_konflikt = _leerer_plan(tagesrouten=[Tagesroute(besuche=[besuch_ohne_zugang])])
    plan_nach_neuplanung = _leerer_plan()

    client = _FakeClient(barrierefrei_je_place_id={"schlecht": False})
    state = _basis_state(anfrage=anfrage, maps_client=client, ausgabe_basisname=str(tmp_path / "reiseplan_test"))
    tools = erstelle_tools(state)

    with patch("src.fragekatalog.agent_tools.plane_reise", return_value=(plan_mit_konflikt, None, PlanungsDebugSammlung())):
        erster_versuch = _rufe(tools, "plane_reise_und_abschliessen")
    assert erster_versuch.get("is_error") is True
    assert state.abgeschlossen is False

    with patch("src.fragekatalog.agent_tools.plane_reise", return_value=(plan_nach_neuplanung, None, PlanungsDebugSammlung())) as m_plane_reise, \
         patch("src.fragekatalog.agent_tools.speichere_datei"), \
         patch("src.fragekatalog.agent_tools.speichere_json"), \
         patch("src.fragekatalog.agent_tools.speichere_poi_uebersicht"), \
         patch("src.fragekatalog.agent_tools.sende_mail"):
        zweiter_versuch = _rufe(tools, "plane_reise_und_abschliessen", barrierefreiheit_bereits_gepruft=True)

    assert not zweiter_versuch.get("is_error")
    assert state.abgeschlossen is True
    assert m_plane_reise.call_args.kwargs.get("barrierefreiheit_strikt") is True


def test_breche_planung_ab_setzt_flag():
    state = _basis_state()
    tools = erstelle_tools(state)
    ergebnis = _rufe(tools, "breche_planung_ab", grund="keine Lust mehr")
    assert state.abgebrochen is True
    assert not ergebnis.get("is_error")

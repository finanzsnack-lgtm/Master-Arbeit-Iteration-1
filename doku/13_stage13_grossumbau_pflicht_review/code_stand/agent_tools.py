"""
Werkzeuge (In-Process SDK-MCP-Tools) für die LLM-autonome Dialogsteuerung
(siehe Projektkonversation: "ich gebe meinem Chatbot all die Fragen, den
Regelkatalog und lasse mit diesen Informationen dann den User einfach nur mit
dem Chatbot kommunizieren, ohne irgendeine Zwischeninstanz über meinen Code").

Ersetzt die bisherige Python-Zustandsmaschine (zustandsmaschine.py::
Dialogschleife) als Ablaufsteuerung: statt dass Python Frage für Frage
vorgibt, bekommt das LLM den GESAMTEN Fragekatalog + diese fünf Werkzeuge in
den System-Prompt (siehe regelwerk.py) und entscheidet selbst, was als
Nächstes zu tun ist (fragen / Daten abrufen / Wert speichern / abschließen /
abbrechen).

WICHTIG (CLAUDE.md, Grundprinzip 1/3 – angepasste Fassung, siehe
ENTSCHEIDUNGSLOG.md): das LLM steuert jetzt den GESPRÄCHSABLAUF selbst
(welche Frage wann, welche übersprungen wird), erfindet aber weiterhin NIE
Fakten (siehe `hole_api_daten`, reine Weiterleitung an
vorschlaege.py::hole_echte_daten_fuer_vorschlag) und baut NIE selbst die
Route/Optimierung (siehe `plane_reise_und_abschliessen`, reine Weiterleitung
an pipeline.py::plane_reise, HART gesperrt, bis alle Pflichtfelder gesetzt
sind).

Jedes Tool ist bewusst dünn: die eigentliche Fachlogik (API-Aufrufe,
Optimierung, All-Inclusive-/Aktivitäten-Sonderfälle) bleibt vollständig in
den bestehenden, unveränderten Modulen (vorschlaege.py, pipeline.py,
reiseplan.py) – hier wird nur der Zugriff für das LLM freigeschaltet und
validiert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool

from src.api.flightapi import FlugClient
from src.api.google_maps import MapsClient
from src.api.hotelbeds import HotelClient
from src.ausgabe.reiseplan import Reiseplan, als_text, sende_mail, speichere_datei, speichere_json, speichere_poi_uebersicht
from src.fragekatalog.katalog import FRAGEKATALOG
from src.fragekatalog.schema import ReiseAnfrage, Rueckgabetyp
from src.fragekatalog.vorschlaege import (
    hole_echte_daten_fuer_vorschlag,
    ist_all_inclusive_wunsch,
    trenne_bereits_im_paket_enthalten,
)
from src.pipeline import plane_reise
from src.protokoll import Protokollierer

# Sammelt alle generierten Reiseplan-Ausgaben (Text/JSON/POI-CSV) an einer Stelle statt einzeln im
# Projekt-Wurzelverzeichnis (siehe Projektkonversation: "wozu ist das alles, das sieht nicht nötig
# aus"). Wird bei Bedarf angelegt (siehe `plane_reise_und_abschliessen`), nicht schon beim Import.
_ERGEBNISSE_VERZEICHNIS = Path(__file__).resolve().parent.parent.parent / "ergebnisse"

_FELD_JE_NAME = {frage.feld: frage for frage in FRAGEKATALOG}

_PYTHON_TYP_JE_RUECKGABETYP: dict[Rueckgabetyp, type | tuple[type, ...]] = {
    Rueckgabetyp.STRING: str,
    Rueckgabetyp.ARRAY: list,
    Rueckgabetyp.ZAHL: (int, float),
    Rueckgabetyp.BOOL: bool,
}


@dataclass
class AgentSessionState:
    """
    Ersetzt `FrageZustand`/`Dialogschleife`-Bilanzierung: EIN gemeinsamer,
    veränderlicher Zustand für die Dauer einer Sitzung, über den die Tools
    per Closure (siehe `erstelle_tools`) auf dieselbe `ReiseAnfrage` und
    dieselben API-Clients zugreifen wie chat.py.
    """

    anfrage: ReiseAnfrage
    maps_client: MapsClient
    flug_client: FlugClient | None = None
    hotel_client: HotelClient | None = None
    protokollierer: Protokollierer | None = None
    ausgabe_basisname: str = "reiseplan_chat"
    abgebrochen: bool = False
    abgeschlossen: bool = False
    reiseplan: Reiseplan | None = None
    nachhaltigkeits_nudge: str | None = None
    abschluss_meldungen: list[str] = field(default_factory=list)


def fehlende_pflichtfelder(anfrage: ReiseAnfrage) -> list[str]:
    """
    Rein deterministische Vollständigkeitsprüfung (siehe CLAUDE.md, Grundprinzip 3 – bleibt der
    Teil, den der regelbasierte Layer weiterhin GARANTIERT, unabhängig davon, ob/wie oft das LLM
    danach fragt): alle `pflichtfeld=True`-Felder aus FRAGEKATALOG, deren Wert auf `anfrage` noch
    leer ist ("leer" = None, "" oder []).
    """
    fehlend = []
    for frage in FRAGEKATALOG:
        if not frage.pflichtfeld:
            continue
        wert = getattr(anfrage, frage.feld, None)
        if wert is None or wert == "" or wert == []:
            fehlend.append(frage.feld)
    return fehlend


def _protokolliere(state: AgentSessionState, tool_name: str, argumente: dict, ergebnis: str) -> None:
    if state.protokollierer is not None:
        state.protokollierer.eintrag("tool_aufruf", tool=tool_name, argumente=argumente, ergebnis=ergebnis)


def _text_ergebnis(text: str, is_error: bool = False) -> dict[str, Any]:
    ergebnis: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        ergebnis["is_error"] = True
    return ergebnis


def _validiere_und_caste(feld: str, wert: Any) -> tuple[Any, str | None]:
    """
    Prüft `wert` gegen den in FRAGEKATALOG hinterlegten `Rueckgabetyp` (siehe schema.py). Claude
    liefert Tool-Argumente bereits typisiert (kein Text-Parsing mehr nötig, anders als früher bei
    `RegelbasierterInterpreter._parse`, der rohen Nutzertext interpretieren musste) – hier wird nur
    noch gegen die erwartete Form gegengeprüft. Gibt (gecasteter_wert, fehlermeldung|None) zurück.
    """
    frage = _FELD_JE_NAME.get(feld)
    if frage is None:
        bekannte_felder = ", ".join(sorted(_FELD_JE_NAME))
        return None, f"Unbekanntes Feld '{feld}'. Bekannte Felder: {bekannte_felder}."

    erwarteter_typ = _PYTHON_TYP_JE_RUECKGABETYP[frage.rueckgabetyp]
    if frage.rueckgabetyp is Rueckgabetyp.ARRAY:
        if not isinstance(wert, list) or not all(isinstance(eintrag, str) for eintrag in wert):
            return None, f"Feld '{feld}' erwartet eine Liste von Strings, bekommen: {wert!r}."
        return wert, None
    if frage.rueckgabetyp is Rueckgabetyp.ZAHL:
        if isinstance(wert, bool) or not isinstance(wert, erwarteter_typ):
            return None, f"Feld '{feld}' erwartet eine Zahl, bekommen: {wert!r}."
        return float(wert), None
    if not isinstance(wert, erwarteter_typ):
        return None, f"Feld '{feld}' erwartet {frage.rueckgabetyp.value}, bekommen: {wert!r}."
    return wert, None


def erstelle_tools(state: AgentSessionState) -> list[SdkMcpTool[Any]]:
    """Baut die fünf Werkzeuge, geschlossen über `state` (siehe AgentSessionState)."""

    @tool(
        "speichere_feld",
        "Speichert einen bestätigten Wert für EIN Feld aus dem Fragekatalog (siehe Systemprompt: "
        "vollständiger Katalog mit Feldnamen, Typ und Pflichtstatus). Ändert auch bereits gesetzte "
        "Felder, falls der Nutzer eine frühere Angabe revidiert. Gibt den aktuellen Vollständigkeits-"
        "status zurück (welche Pflichtfelder noch fehlen).",
        {
            "type": "object",
            "properties": {
                "feld": {"type": "string", "description": "Exakter Feldname aus dem Fragekatalog, z.B. 'budget_gesamt'."},
                "wert": {
                    "anyOf": [
                        {"type": "string"}, {"type": "number"}, {"type": "boolean"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "Der zu speichernde Wert, Typ passend zum erwarteten Rückgabetyp des Feldes.",
                },
                "aktivitaeten_mit_spezialrecherche": {
                    "type": "array", "items": {"type": "string"},
                    "description": (
                        "NUR bei feld=aktivitaeten_interessen: welche der gespeicherten Aktivitäten über "
                        "OpenStreetMap/Overpass recherchiert werden sollen (dieselbe Liste, die du zuvor an "
                        "hole_api_daten übergeben hast) – wird für die SPÄTERE, finale Planung gebraucht, nicht "
                        "nur für die Chat-Vorschau. Ohne dieses Argument wird bei der finalen Planung KEINE "
                        "Overpass-Recherche mehr durchgeführt, selbst wenn die Vorschau sie genutzt hat."
                    ),
                },
                "aktivitaeten_gewichtung": {
                    "type": "object", "additionalProperties": {"type": "number"},
                    "description": (
                        "NUR bei feld=aktivitaeten_interessen: relative Gewichtung einzelner genannter "
                        "Interessen (Schlüssel = exakter Text aus 'wert', z.B. {'Klettern': 2.0, "
                        "'Shopping': 0.5}) – beeinflusst, welche der Treffer bevorzugt eingeplant werden. "
                        "Setze das NICHT nur, wenn es wegen zu vieler Treffer eine explizite vergleichende "
                        "Rückfrage gab (das bleibt ein gültiger Auslöser, aber nicht der einzige), sondern "
                        "immer wenn der GESAMTE bisherige Gesprächskontext eine unterschiedliche Priorität "
                        "erkennen lässt (Betonung, Wiederholung, ein genannter Grund, eine erkennbare "
                        "Rangfolge – nicht nur das wörtliche Wort 'wichtig'). Bei erkennbar gleichrangig/"
                        "neutral genannten Interessen weglassen (Standard bleibt 1.0) – keine Präferenz "
                        "erfinden, die der Nutzer nicht tatsächlich ausgedrückt hat."
                    ),
                },
            },
            "required": ["feld", "wert"],
        },
    )
    async def speichere_feld(args: dict[str, Any]) -> dict[str, Any]:
        feld = args["feld"]
        gecasteter_wert, fehler = _validiere_und_caste(feld, args.get("wert"))
        if fehler:
            _protokolliere(state, "speichere_feld", args, fehler)
            return _text_ergebnis(fehler, is_error=True)

        setattr(state.anfrage, feld, gecasteter_wert)

        # Sonderfälle (siehe Moduldoku): bleiben bewusst feldspezifisch fest verdrahtet, wie vorher
        # in chat.py::b2_bis_b6_frage_typ_c, nur hierher verschoben.
        if feld == "unterkunft_anforderungen" and ist_all_inclusive_wunsch(gecasteter_wert) and state.hotel_client is not None:
            ziel = state.anfrage.primaeres_reiseziel()
            if ziel:  # ohne bereits bekanntes Ziel kann nicht geokodiert werden -> Sonderfall einfach übersprungen
                hotels = state.hotel_client.suche_all_inclusive_hotels(state.maps_client.geocode(ziel))
                if hotels:
                    gewaehlt = hotels[0]
                    state.anfrage.all_inclusive_gewuenscht = True
                    state.anfrage.all_inclusive_hotel_id = gewaehlt.externe_hotel_id
                    state.anfrage.all_inclusive_hotel_name = gewaehlt.name
                    state.anfrage.all_inclusive_hotel_koordinaten = (gewaehlt.x, gewaehlt.y)
        elif feld == "aktivitaeten_interessen":
            # BEHOBENER BUG (siehe Projektkonversation, Code-Review nach dem Architekturwechsel):
            # `aktivitaeten_mit_spezialrecherche` wurde bisher NIRGENDS persistiert – Overpass lief
            # zwar korrekt in der Chat-Vorschau (hole_api_daten bekommt das Argument direkt), aber
            # pipeline.py::plane_reise liest beim finalen Planen `anfrage.aktivitaeten_mit_
            # spezialrecherche`, das ohne diese Zeile für immer leer geblieben wäre.
            state.anfrage.aktivitaeten_mit_spezialrecherche = list(args.get("aktivitaeten_mit_spezialrecherche") or [])
            state.anfrage.aktivitaeten_gewichtung = dict(args.get("aktivitaeten_gewichtung") or {})
            _, noch_zu_planen = trenne_bereits_im_paket_enthalten(gecasteter_wert, state.anfrage, state.hotel_client)
            state.anfrage.aktivitaeten_noch_per_poi_zu_planen = noch_zu_planen

        fehlend = fehlende_pflichtfelder(state.anfrage)
        ergebnis_text = (
            f"Gespeichert: {feld} = {gecasteter_wert!r}. "
            + (f"Noch fehlende Pflichtfelder: {', '.join(fehlend)}." if fehlend else "Alle Pflichtfelder sind gesetzt.")
        )
        _protokolliere(state, "speichere_feld", args, ergebnis_text)
        return _text_ergebnis(ergebnis_text)

    @tool(
        "hole_api_daten",
        "Ruft ECHTE Daten (Unterkünfte, Aktivitäten/POIs, Verkehrsmittel-Alternativen) für ein "
        "Typ-C-Feld ab. Erfinde NIE selbst Orte/Preise/Zeiten. Bei aktivitaeten_interessen/"
        "verkehrsmittel_praeferenz formulierst du DANACH einen Vorschlag ausschließlich auf Basis "
        "des Ergebnisses. Bei unterkunft_anforderungen (siehe Systemprompt) rufst du es GENAUSO "
        "auf (echte Daten prüfen bleibt Pflicht), nennst dem Nutzer aber KEINE der zurückgegebenen "
        "Hotelnamen/Kandidaten und holst dazu KEINE Zustimmung ein – das Ergebnis dient nur der "
        "internen Prüfung, dass echte Unterkünfte existieren.",
        {
            "type": "object",
            "properties": {
                "feld": {
                    "type": "string",
                    "description": "Eines von: unterkunft_anforderungen, aktivitaeten_interessen, verkehrsmittel_praeferenz.",
                },
                "aktueller_wert": {
                    "type": "string",
                    "description": "NUR bei feld=unterkunft_anforderungen: die aktuelle (ggf. noch unbestätigte) Nutzerantwort als Text.",
                },
                "aktivitaeten_aktuell": {
                    "type": "array", "items": {"type": "string"},
                    "description": (
                        "NUR bei feld=aktivitaeten_interessen: die VOLLSTÄNDIGE Liste ALLER bisher im Gespräch "
                        "genannten Aktivitäten-Interessen (z.B. ['Klettern', 'Wandern', 'Restaurants', 'Cafés']), "
                        "nicht nur die zuletzt genannten oder die mit Vertiefungsbedarf – wird 1:1 als "
                        "Suchkategorien verwendet. Fehlt dieses Argument oder lässt es ein genanntes Interesse "
                        "aus, wird NICHT danach gesucht (kein Fallback aufs Erraten)."
                    ),
                },
                "spezialrecherche_aktivitaeten": {
                    "type": "array", "items": {"type": "string"},
                    "description": (
                        "NUR bei feld=aktivitaeten_interessen: welche der in `aktivitaeten_aktuell` genannten "
                        "Aktivitäten zusätzlich über OpenStreetMap/Overpass recherchiert werden sollen (siehe "
                        "Systemprompt: Klettern, Wandern mit Schwierigkeitsgrad, Ski, Tauchen, Mountainbike u.ä.)."
                    ),
                },
                "flug_erwuenscht": {
                    "type": "boolean",
                    "description": (
                        "NUR bei feld=verkehrsmittel_praeferenz: true, wenn der Nutzer nach einem "
                        "Alternativziel-Vorschlag ausdrücklich auf dem ursprünglichen, mit Bahn/Auto nicht "
                        "mehr sinnvoll erreichbaren Ziel besteht (siehe CLAUDE.md, Grundprinzip 5)."
                    ),
                },
            },
            "required": ["feld"],
        },
    )
    async def hole_api_daten(args: dict[str, Any]) -> dict[str, Any]:
        feld = args["feld"]
        frage = _FELD_JE_NAME.get(feld)
        if frage is None or not frage.api_abruf_noetig:
            fehler = f"Für Feld '{feld}' ist kein Datenabruf vorgesehen."
            _protokolliere(state, "hole_api_daten", args, fehler)
            return _text_ergebnis(fehler, is_error=True)

        text = hole_echte_daten_fuer_vorschlag(
            frage, state.anfrage, state.maps_client,
            spezialrecherche_aktivitaeten=args.get("spezialrecherche_aktivitaeten") or [],
            flug_client=state.flug_client,
            flug_erwuenscht=bool(args.get("flug_erwuenscht", False)),
            hotel_client=state.hotel_client,
            unterkunft_antwort_text=args.get("aktueller_wert") if feld == "unterkunft_anforderungen" else None,
            aktivitaeten_aktuell=args.get("aktivitaeten_aktuell") if feld == "aktivitaeten_interessen" else None,
        )
        _protokolliere(state, "hole_api_daten", args, text)
        return _text_ergebnis(text)

    @tool(
        "fehlende_pflichtfelder",
        "Gibt die Namen aller Pflichtfelder zurück, die noch keinen Wert haben. Vor einem Versuch, "
        "die Planung abzuschließen, IMMER vorher prüfen.",
        {},
    )
    async def fehlende_pflichtfelder_tool(_args: dict[str, Any]) -> dict[str, Any]:
        fehlend = fehlende_pflichtfelder(state.anfrage)
        text = f"Fehlende Pflichtfelder: {', '.join(fehlend)}." if fehlend else "Keine Pflichtfelder fehlen mehr."
        _protokolliere(state, "fehlende_pflichtfelder", {}, text)
        return _text_ergebnis(text)

    @tool(
        "plane_reise_und_abschliessen",
        "Schließt den Dialog ab: plant die Reise (Optimierung 1+2, Monte-Carlo-Härtetest) aus den "
        "gespeicherten Feldern und verschickt/speichert den Reiseplan. Schlägt fehl, solange "
        "Pflichtfelder fehlen – dann zurück in den Dialog und die fehlenden Felder klären.",
        {},
    )
    async def plane_reise_und_abschliessen(_args: dict[str, Any]) -> dict[str, Any]:
        fehlend = fehlende_pflichtfelder(state.anfrage)
        if fehlend:
            fehler = f"Kann noch nicht abschließen, es fehlen: {', '.join(fehlend)}."
            _protokolliere(state, "plane_reise_und_abschliessen", {}, fehler)
            return _text_ergebnis(fehler, is_error=True)

        plan, nudge = plane_reise(state.anfrage, state.maps_client, state.flug_client, state.hotel_client)
        state.reiseplan = plan
        state.nachhaltigkeits_nudge = nudge

        # Generierte Ausgaben landen gesammelt in ergebnisse/ statt einzeln im Projekt-Wurzelverzeichnis
        # (siehe Projektkonversation: "wozu ist das alles, das steht nicht nötig aus" – chat.py
        # geben nur einen BASISNAMEN vor, z.B. "reiseplan_chat", nicht den Zielordner). Ist
        # `ausgabe_basisname` bereits ein absoluter Pfad (siehe Tests, tmp_path), gewinnt er unverändert –
        # pathlib verwirft bei `A / B` den linken Teil, wenn B absolut ist.
        _ERGEBNISSE_VERZEICHNIS.mkdir(exist_ok=True)
        ausgabe_pfad = _ERGEBNISSE_VERZEICHNIS / f"{state.ausgabe_basisname}.txt"
        speichere_datei(plan, ausgabe_pfad)
        speichere_json(plan, ausgabe_pfad.with_suffix(".json"))
        # POI-Übersicht (siehe reiseplan.py `speichere_poi_uebersicht`, Projektkonversation: "ich
        # brauch ein Dokument, wo mir alle POIs aufgezeigt werden, sodass ich sagen kann, dass
        # dieser Optimierungsalgorithmus funktioniert") – ALLE Kandidaten mit Score/Zeitfenster/
        # gewählt-Status, als CSV für Excel/Auswertung, nicht nur die fertige Textzusammenfassung.
        poi_uebersicht_pfad = ausgabe_pfad.with_name(f"{ausgabe_pfad.stem}_pois.csv")
        speichere_poi_uebersicht(plan, poi_uebersicht_pfad)
        meldungen = [
            f"Reiseplan gespeichert unter: {ausgabe_pfad}",
            f"POI-Übersicht (alle Kandidaten mit Score/Zeitfenster) gespeichert unter: {poi_uebersicht_pfad}",
        ]

        if state.anfrage.email:
            try:
                sende_mail(plan, state.anfrage.email)
                meldungen.append(f"Reiseplan per Mail an {state.anfrage.email} verschickt.")
            except RuntimeError as fehler:
                meldungen.append(f"Mail-Versand fehlgeschlagen ({fehler}). Reiseplan liegt weiterhin als Datei vor.")
        else:
            meldungen.append("Keine E-Mail-Adresse hinterlegt, Reiseplan wird nicht per Mail verschickt.")

        state.abschluss_meldungen = meldungen
        state.abgeschlossen = True

        text = (nudge + "\n\n" if nudge else "") + als_text(plan) + "\n\n" + "\n".join(meldungen)
        _protokolliere(state, "plane_reise_und_abschliessen", {}, "Reise erfolgreich geplant und abgeschlossen.")
        return _text_ergebnis(text)

    @tool(
        "breche_planung_ab",
        "Beendet die Planung sofort, wenn der Nutzer erkennbar den gesamten Prozess abbrechen möchte.",
        {"grund": str},
    )
    async def breche_planung_ab(args: dict[str, Any]) -> dict[str, Any]:
        state.abgebrochen = True
        _protokolliere(state, "breche_planung_ab", args, "Planung abgebrochen.")
        return _text_ergebnis("Alles klar, die Planung wird abgebrochen.")

    return [speichere_feld, hole_api_daten, fehlende_pflichtfelder_tool, plane_reise_und_abschliessen, breche_planung_ab]


def erstelle_mcp_server(state: AgentSessionState) -> McpSdkServerConfig:
    """`ClaudeAgentOptions.mcp_servers={"reisebot": erstelle_mcp_server(state)}` (siehe chat.py)."""
    return create_sdk_mcp_server(name="reisebot", tools=erstelle_tools(state))


ERLAUBTE_TOOLS = [
    "mcp__reisebot__speichere_feld",
    "mcp__reisebot__hole_api_daten",
    "mcp__reisebot__fehlende_pflichtfelder",
    "mcp__reisebot__plane_reise_und_abschliessen",
    "mcp__reisebot__breche_planung_ab",
]

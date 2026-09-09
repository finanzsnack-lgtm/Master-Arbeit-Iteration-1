"""
Werkzeuge (In-Process SDK-MCP-Tools) für die LLM-autonome Dialogsteuerung: das LLM bekommt den
GESAMTEN Fragekatalog + diese fünf Werkzeuge in den System-Prompt (siehe regelwerk.py) und
entscheidet selbst, was als Nächstes zu tun ist (fragen / Daten abrufen / Wert speichern /
abschließen / abbrechen).

CLAUDE.md, Grundprinzip 1/3: das LLM steuert den GESPRÄCHSABLAUF selbst (welche Frage wann, welche
übersprungen wird), erfindet aber NIE Fakten (siehe `hole_api_daten`, reine Weiterleitung an
vorschlaege.py) und baut NIE selbst die Route/Optimierung (siehe `plane_reise_und_abschliessen`,
reine Weiterleitung an pipeline.py::plane_reise, HART gesperrt, bis alle Pflichtfelder gesetzt
sind).

Jedes Tool ist bewusst dünn: die eigentliche Fachlogik (API-Aufrufe, Optimierung) bleibt
vollständig in den bestehenden Modulen (vorschlaege.py, pipeline.py, reiseplan.py) – hier wird nur
der Zugriff für das LLM freigeschaltet und validiert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool

from src.api.google_maps import MapsClient
from src.api.typen import Unterkunft
from src.ausgabe.debug import schreibe_debug_datei
from src.ausgabe.reiseplan import Reiseplan, als_text, sende_mail, speichere_datei, speichere_json, speichere_poi_uebersicht
from src.datenaufbereitung.vertraeglichkeit import pruefe_barrierefreiheit_des_plans
from src.fragekatalog.katalog import FRAGEKATALOG
from src.fragekatalog.schema import ReiseAnfrage, Rueckgabetyp
from src.fragekatalog.vorschlaege import hole_echte_daten_fuer_vorschlag, suche_unterkunft, suche_verleih_nahe_unterkunft
from src.pipeline import plane_reise
from src.protokoll import Protokollierer

# Sammelt alle generierten Reiseplan-Ausgaben (Text/JSON/POI-CSV) an einer Stelle statt einzeln im
# Projekt-Wurzelverzeichnis. Wird bei Bedarf angelegt (siehe `plane_reise_und_abschliessen`), nicht
# schon beim Import.
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
    """EIN gemeinsamer, veränderlicher Zustand für die Dauer einer Sitzung, über den die Tools
    per Closure (siehe `erstelle_tools`) auf dieselbe `ReiseAnfrage` und denselben API-Client
    zugreifen wie chat.py."""

    anfrage: ReiseAnfrage
    maps_client: MapsClient
    protokollierer: Protokollierer | None = None
    ausgabe_basisname: str = "reiseplan_chat"
    abgebrochen: bool = False
    abgeschlossen: bool = False
    reiseplan: Reiseplan | None = None
    nachhaltigkeits_nudge: str | None = None
    abschluss_meldungen: list[str] = field(default_factory=list)
    # Zwischenspeicher für die zuletzt bei hole_api_daten(feld=unterkunft_anforderungen) gefundene
    # Unterkunft (siehe suche_unterkunft) – wird bei Bestätigung durch speichere_feld auf
    # `anfrage.unterkunft_*` übernommen, damit die im Chat vorgeschlagene Unterkunft auch
    # tatsächlich die geplante ist, ohne ein zweites Mal zu suchen.
    zuletzt_gefundene_unterkunft: Unterkunft | None = None
    # Merkt sich, für welches Unterkunft-Objekt bereits eine Vorschau-Karte (Foto/Preis, siehe
    # IOKanal.zeige_karte/chat.py::hauptablauf) an den Nutzer geschickt wurde – verhindert, dass
    # dieselbe Karte bei jedem weiteren Chat-Turn erneut verschickt wird, solange sich
    # `zuletzt_gefundene_unterkunft` nicht ändert (z.B. neue Suche nach Ablehnung).
    unterkunft_karte_zuletzt_gezeigt: Unterkunft | None = None


def fehlende_pflichtfelder(anfrage: ReiseAnfrage) -> list[str]:
    """
    Rein deterministische Vollständigkeitsprüfung (CLAUDE.md, Grundprinzip 3): alle
    `pflichtfeld=True`-Felder aus FRAGEKATALOG, deren Wert auf `anfrage` noch leer ist
    ("leer" = None, "" oder []).
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
    liefert Tool-Argumente bereits typisiert – hier wird nur noch gegen die erwartete Form
    gegengeprüft. Gibt (gecasteter_wert, fehlermeldung|None) zurück.
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
                        "Setze das, wenn der GESAMTE bisherige Gesprächskontext eine unterschiedliche Priorität "
                        "erkennen lässt (Betonung, Wiederholung, ein genannter Grund, eine erkennbare "
                        "Rangfolge – nicht nur das wörtliche Wort 'wichtig'). Bei erkennbar gleichrangig/"
                        "neutral genannten Interessen weglassen (Standard bleibt 1.0) – keine Präferenz "
                        "erfinden, die der Nutzer nicht tatsächlich ausgedrückt hat."
                    ),
                },
                "sicherheit_bedenklich": {
                    "type": "boolean",
                    "description": (
                        "NUR bei feld=sicherheitsbeduerfnis: true, wenn du aus dem GESAMTEN bisherigen "
                        "Gesprächskontext eine echte Sicherheitssorge erkennst (nicht nur bei wörtlicher "
                        "Nennung des Wortes 'Sicherheit') – steuert, ob dem Nutzer im fertigen Reiseplan ein "
                        "Verweis auf die offiziellen Reise- und Sicherheitshinweise des Auswärtigen Amts "
                        "beigelegt wird. Erkennst du dabei ein Ziel, dessen Sicherheitslage erkennbar "
                        "problematisch ist, schlage VOR dem Speichern proaktiv eine sicherere Alternativregion "
                        "vor (allgemeines Reisewissen ist hier ausnahmsweise zulässig, siehe Systemprompt)."
                    ),
                },
                "tagesstart_minuten": {
                    "type": "integer",
                    "description": (
                        "NUR bei feld=tagesstart_praeferenz: von dir interpretierte Startuhrzeit für einen "
                        "normalen Reisetag, als Minuten seit Mitternacht (9 Uhr = 540). Leite sie aus der "
                        "Antwort ab, auch bei vagen Formulierungen wie 'eher früh' – nur bei GAR KEINEM "
                        "zeitlichen Anhaltspunkt weglassen, statt eine Uhrzeit zu erfinden."
                    ),
                },
                "tagesende_minuten": {
                    "type": "integer",
                    "description": "NUR bei feld=tagesstart_praeferenz: wie `tagesstart_minuten`, aber die späteste Enduhrzeit.",
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

        # Sonderfälle (siehe Moduldoku): bleiben bewusst feldspezifisch fest verdrahtet.
        if feld == "unterkunft_anforderungen":
            gefunden = state.zuletzt_gefundene_unterkunft
            if gefunden is not None:
                state.anfrage.unterkunft_name = gefunden.name
                state.anfrage.unterkunft_koordinaten = (gefunden.x, gefunden.y)
                state.anfrage.unterkunft_place_id = gefunden.place_id
                state.anfrage.unterkunft_foto_referenz = gefunden.foto_referenz
                state.anfrage.unterkunft_preisniveau = gefunden.preisniveau
        elif feld == "aktivitaeten_interessen":
            state.anfrage.aktivitaeten_mit_spezialrecherche = list(args.get("aktivitaeten_mit_spezialrecherche") or [])
            state.anfrage.aktivitaeten_gewichtung = dict(args.get("aktivitaeten_gewichtung") or {})
        elif feld == "sicherheitsbeduerfnis":
            state.anfrage.sicherheit_bedenklich = bool(args.get("sicherheit_bedenklich", False))
        elif feld == "tagesstart_praeferenz":
            if args.get("tagesstart_minuten") is not None:
                state.anfrage.tagesstart_minuten = int(args["tagesstart_minuten"])
            if args.get("tagesende_minuten") is not None:
                state.anfrage.tagesende_minuten = int(args["tagesende_minuten"])

        fehlend = fehlende_pflichtfelder(state.anfrage)
        ergebnis_text = (
            f"Gespeichert: {feld} = {gecasteter_wert!r}. "
            + (f"Noch fehlende Pflichtfelder: {', '.join(fehlend)}." if fehlend else "Alle Pflichtfelder sind gesetzt.")
        )
        _protokolliere(state, "speichere_feld", args, ergebnis_text)
        return _text_ergebnis(ergebnis_text)

    @tool(
        "hole_api_daten",
        "Ruft ECHTE Daten (Unterkünfte, Fahrzeug-Verleih, Aktivitäten/POIs, Verkehrsmittel-"
        "Alternativen) für ein Typ-C-Feld ab. Erfinde NIE selbst Orte/Preise/Zeiten – nenne dem "
        "Nutzer bei aktivitaeten_interessen/verkehrsmittel_praeferenz ausschließlich, was dieses "
        "Werkzeug zurückgibt, und hole dazu Zustimmung ein, bevor du speichere_feld aufrufst. Bei "
        "unterkunft_anforderungen schlägt es GENAU EINE gefundene Unterkunft vor, die du dem "
        "Nutzer kurz nennst und bestätigen lässt ('passt das für dich?') – KEINE Liste mehrerer "
        "Kandidaten. Bei lokaler_transport_praeferenz braucht es eine bereits bestätigte "
        "Unterkunft (F15) – rufe es dafür ERST NACH F15 auf.",
        {
            "type": "object",
            "properties": {
                "feld": {
                    "type": "string",
                    "description": (
                        "Eines von: unterkunft_anforderungen, lokaler_transport_praeferenz, "
                        "aktivitaeten_interessen, verkehrsmittel_praeferenz."
                    ),
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
                "ziel_trotzdem_gewuenscht": {
                    "type": "boolean",
                    "description": (
                        "NUR bei feld=verkehrsmittel_praeferenz: true, wenn der Nutzer nach einem "
                        "Alternativziel-Vorschlag ausdrücklich auf dem ursprünglichen, mit Bahn/Auto nicht "
                        "mehr sinnvoll erreichbaren Ziel besteht (CLAUDE.md, Grundprinzip 5: Flüge sind "
                        "ausgeschlossen, es gibt also keine Alternative außer der langen Fahrt)."
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

        if feld == "unterkunft_anforderungen":
            text, gefunden = suche_unterkunft(state.anfrage, state.maps_client, args.get("aktueller_wert"))
            state.zuletzt_gefundene_unterkunft = gefunden
        elif feld == "lokaler_transport_praeferenz":
            text, verleih = suche_verleih_nahe_unterkunft(state.anfrage, state.maps_client)
            if verleih is not None:
                state.anfrage.lokaler_verleih_gewaehlt = verleih
        else:
            text = hole_echte_daten_fuer_vorschlag(
                frage, state.anfrage, state.maps_client,
                spezialrecherche_aktivitaeten=args.get("spezialrecherche_aktivitaeten") or [],
                aktivitaeten_aktuell=args.get("aktivitaeten_aktuell") if feld == "aktivitaeten_interessen" else None,
                ziel_trotzdem_gewuenscht=bool(args.get("ziel_trotzdem_gewuenscht", False)),
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
        "Pflichtfelder fehlen – dann zurück in den Dialog und die fehlenden Felder klären. Schlägt "
        "auch fehl, wenn bei genannter Barrierefreiheits-/Mobilitätsanforderung der geplante Plan "
        "sie nicht erfüllt – dann frag den Nutzer kurz, ob eine strengere Neuplanung (ggf. weniger "
        "Programm) in Ordnung ist, und rufe danach mit barrierefreiheit_bereits_gepruft=true erneut auf.",
        {
            "type": "object",
            "properties": {
                "barrierefreiheit_bereits_gepruft": {
                    "type": "boolean",
                    "description": (
                        "true beim ZWEITEN Aufruf, nachdem der Nutzer einer strengeren Neuplanung nach "
                        "einer fehlgeschlagenen Barrierefreiheits-Prüfung zugestimmt hat."
                    ),
                },
            },
        },
    )
    async def plane_reise_und_abschliessen(args: dict[str, Any]) -> dict[str, Any]:
        fehlend = fehlende_pflichtfelder(state.anfrage)
        if fehlend:
            fehler = f"Kann noch nicht abschließen, es fehlen: {', '.join(fehlend)}."
            _protokolliere(state, "plane_reise_und_abschliessen", args, fehler)
            return _text_ergebnis(fehler, is_error=True)

        barrierefreiheit_strikt = bool(args.get("barrierefreiheit_bereits_gepruft", False))
        plan, nudge, debug_sammlung = plane_reise(
            state.anfrage, state.maps_client, barrierefreiheit_strikt=barrierefreiheit_strikt
        )

        # Debug-Ausgabe (siehe src/ausgabe/debug.py: rohe/gefilterte/an Optimierung 1 weitergegebene
        # POIs, Optimierung-1- und Härtetest-Eingabe/-Ergebnis) landet NEBEN dem Sitzungsprotokoll in
        # protokolle/ – bewusst dort statt in ergebnisse/ (das ist der eigentliche Nutzer-Reiseplan),
        # da beides zur Nachvollziehbarkeit DIESER Sitzung gehört. Entsteht bei JEDEM echten Aufruf
        # (chat.py/webapp.py), nicht nur über pruefe_planung.py – auch bei einem wegen
        # Barrierefreiheit abgelehnten ersten Versuch, um die Ablehnung nachvollziehen zu können.
        if state.protokollierer is not None:
            debug_pfad = state.protokollierer.pfad.with_name(f"{state.protokollierer.pfad.stem}_debug.txt")
            schreibe_debug_datei(debug_sammlung, debug_pfad)

        # Nachplanungs-Prüfung (siehe vertraeglichkeit.py `pruefe_barrierefreiheit_des_plans`): der
        # ERSTE Planungsversuch behält einen Konflikt notfalls mit Warnhinweis, statt eine leere
        # Auswahl zu riskieren – hier wird der TATSÄCHLICH fertige Plan noch einmal gegen echte
        # Daten geprüft. Nur beim ersten Versuch (noch nicht strikt), sonst würde ein potenziell
        # verbleibender Konflikt bei der Unterkunft selbst (die im Dialog schon fest bestätigt
        # wurde) endlos denselben Fehler zurückgeben.
        if state.anfrage.barrierefreiheit_oder_eingeschraenkt() and not barrierefreiheit_strikt:
            besuchte_place_ids = [
                besuch.poi.place_id for route in plan.tagesrouten for besuch in route.besuche if besuch.poi.place_id
            ]
            verletzungen = pruefe_barrierefreiheit_des_plans(besuchte_place_ids, plan.unterkunft_place_id, state.maps_client)
            if verletzungen:
                fehler = (
                    "Der geplante Reiseplan erfüllt die genannte Barrierefreiheits-/Mobilitätsanforderung "
                    f"NICHT vollständig ({len(verletzungen)} betroffene Orte). Frag den Nutzer kurz, ob eine "
                    "strengere Neuplanung in Ordnung ist (schließt diese Orte konsequent aus, auch wenn dadurch "
                    "weniger Programm übrig bleibt), und rufe danach dieses Werkzeug erneut mit "
                    "barrierefreiheit_bereits_gepruft=true auf."
                )
                _protokolliere(state, "plane_reise_und_abschliessen", args, fehler)
                return _text_ergebnis(fehler, is_error=True)

        state.reiseplan = plan
        state.nachhaltigkeits_nudge = nudge

        # Generierte Ausgaben landen gesammelt in ergebnisse/ statt einzeln im Projekt-Wurzelverzeichnis.
        # `ausgabe_basisname` gibt nur einen Basisnamen vor, keinen Zielordner. Ist er bereits ein
        # absoluter Pfad (siehe Tests, tmp_path), gewinnt er unverändert – pathlib verwirft bei
        # `A / B` den linken Teil, wenn B absolut ist.
        _ERGEBNISSE_VERZEICHNIS.mkdir(exist_ok=True)
        ausgabe_pfad = _ERGEBNISSE_VERZEICHNIS / f"{state.ausgabe_basisname}.txt"
        speichere_datei(plan, ausgabe_pfad)
        speichere_json(plan, ausgabe_pfad.with_suffix(".json"))
        # POI-Übersicht (siehe reiseplan.py `speichere_poi_uebersicht`) – ALLE Kandidaten mit
        # Score/Zeitfenster/gewählt-Status, als CSV für Excel/Auswertung.
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
        _protokolliere(state, "plane_reise_und_abschliessen", args, "Reise erfolgreich geplant und abgeschlossen.")
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

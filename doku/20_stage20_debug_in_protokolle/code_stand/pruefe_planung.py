"""
Direkter Test der deterministischen Planung (POI-Suche, Optimierung 1+2, Monte-Carlo-Härtetest)
OHNE Dialog/LLM: eine `ReiseAnfrage` wird direkt aus einer `planungs_testfaelle/*.json`-Datei
(Feldname -> Wert, siehe ReiseAnfrage in src/fragekatalog/schema.py) gebaut. Testet NUR die
deterministische Planungskette (Grundprinzip 3), ganz ohne LLM/Dialog.

Nutzt bei vorhandenem `GOOGLE_MAPS_API_KEY` (siehe .env) echte APIs, sonst Mock-Daten (MOCK_MODE,
wie überall im Projekt) – KEINE erfundenen Daten.

Aufruf:
  python pruefe_planung.py                    # nutzt planungs_testfaelle/klettern_essen.json
  python pruefe_planung.py <name>              # nutzt planungs_testfaelle/<name>.json
  python pruefe_planung.py --liste             # zeigt alle verfügbaren Testfälle
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

from src.api.google_maps import erzeuge_client
from src.ausgabe.debug import PlanungsDebugSammlung, schreibe_debug_datei
from src.ausgabe.reiseplan import als_text, speichere_datei, speichere_json, speichere_poi_uebersicht
from src.fragekatalog.agent_tools import _ERGEBNISSE_VERZEICHNIS
from src.fragekatalog.schema import ReiseAnfrage
from src.fragekatalog.vorschlaege import suche_unterkunft, suche_verleih_nahe_unterkunft
from src.pipeline import plane_reise

TESTFAELLE_VERZEICHNIS = Path(__file__).parent / "planungs_testfaelle"
STANDARD_TESTFALL = "klettern_essen"


def verfuegbare_testfaelle() -> list[str]:
    return sorted(pfad.stem for pfad in TESTFAELLE_VERZEICHNIS.glob("*.json"))


def lade_anfrage(name: str) -> ReiseAnfrage:
    """
    Lädt `planungs_testfaelle/{name}.json` (Feldname -> Wert, exakt die
    Feldnamen aus `ReiseAnfrage`) und baut daraus direkt eine `ReiseAnfrage`.
    Ein Tippfehler im Feldnamen fällt sofort als TypeError auf (Python
    verweigert unbekannte Konstruktor-Argumente), statt still ignoriert zu
    werden.
    """
    pfad = TESTFAELLE_VERZEICHNIS / f"{name}.json"
    if not pfad.exists():
        vorhandene = ", ".join(verfuegbare_testfaelle()) or "(keine gefunden)"
        raise SystemExit(f"Testfall '{name}' nicht gefunden ({pfad}). Verfügbar: {vorhandene}")
    werte = json.loads(pfad.read_text(encoding="utf-8"))
    bekannte_felder = {f.name for f in fields(ReiseAnfrage)}
    unbekannt = set(werte) - bekannte_felder
    if unbekannt:
        raise SystemExit(f"Unbekannte Felder in '{pfad.name}' (Tippfehler?): {sorted(unbekannt)}")
    return ReiseAnfrage(**werte)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    argumente = sys.argv[1:]
    if argumente and argumente[0] in ("--liste", "-l"):
        print("Verfügbare Planungs-Testfälle (planungs_testfaelle/*.json):")
        for name in verfuegbare_testfaelle():
            print(f"  - {name}")
        return

    testfall_name = argumente[0] if argumente else STANDARD_TESTFALL
    anfrage = lade_anfrage(testfall_name)

    print(f"=== Planungs-Testfall: {testfall_name} (Ziel: {anfrage.primaeres_reiseziel()}) ===\n")

    client = erzeuge_client()

    # Simuliert, was im echten Dialog bei F15/F14 passiert: Unterkunft suchen+bestätigen (siehe
    # agent_tools.py::speichere_feld), danach ggf. Verleih nahe dieser Unterkunft suchen – ohne
    # diese Schritte würde plane_reise() auf den groben Zielort-Mittelpunkt zurückfallen.
    _, unterkunft = suche_unterkunft(anfrage, client, anfrage.unterkunft_anforderungen)
    if unterkunft is not None:
        anfrage.unterkunft_name = unterkunft.name
        anfrage.unterkunft_koordinaten = (unterkunft.x, unterkunft.y)
        anfrage.unterkunft_place_id = unterkunft.place_id
        _, verleih = suche_verleih_nahe_unterkunft(anfrage, client)
        if verleih is not None:
            anfrage.lokaler_verleih_gewaehlt = verleih

    # Sammelt Zwischenergebnisse (rohe POI-Treffer, gefilterte/ausgewählte Kandidaten, Optimierung-1-
    # Eingabe/-Ergebnis, Härtetest-Eingabe/-Ergebnis) für die Debug-Datei unten – siehe src/ausgabe/
    # debug.py. Nur hier gesetzt (chat.py/webapp.py übergeben nichts, kein Mehraufwand dort).
    debug_sammlung = PlanungsDebugSammlung()
    plan, nudge = plane_reise(anfrage, client, debug_sammlung=debug_sammlung)

    print(als_text(plan))
    if nudge:
        print(f"\n[Nachhaltigkeits-Hinweis] {nudge}")

    _ERGEBNISSE_VERZEICHNIS.mkdir(exist_ok=True)
    basisname = f"planung_{testfall_name}"
    speichere_datei(plan, _ERGEBNISSE_VERZEICHNIS / f"{basisname}.txt")
    speichere_json(plan, _ERGEBNISSE_VERZEICHNIS / f"{basisname}.json")
    poi_pfad = _ERGEBNISSE_VERZEICHNIS / f"{basisname}_pois.csv"
    speichere_poi_uebersicht(plan, poi_pfad)
    debug_pfad = _ERGEBNISSE_VERZEICHNIS / f"{basisname}_debug.txt"
    schreibe_debug_datei(debug_sammlung, debug_pfad)
    print(
        f"\nGespeichert unter: {_ERGEBNISSE_VERZEICHNIS}/{basisname}.{{txt,json}}, "
        f"{poi_pfad.name}, {debug_pfad.name}"
    )


if __name__ == "__main__":
    main()

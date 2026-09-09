"""
Direkter Test der deterministischen Planung (POI-Suche, Optimierung 1+2,
Monte-Carlo-Härtetest) OHNE Dialog/LLM – im Unterschied zu main.py wird hier
KEINE Chat-Session gestartet, sondern eine `ReiseAnfrage` direkt aus einer
`planungs_testfaelle/*.json`-Datei (Feldname -> Wert, siehe ReiseAnfrage in
src/fragekatalog/schema.py) gebaut und direkt an `pipeline.py::plane_reise()`
übergeben.

WARUM (siehe Projektkonversation): main.py/testfaelle/*.json steuern die
ECHTE, LLM-geführte Dialogschleife mit vorbereiteten Antworten – das Modell
entscheidet selbst über Rückfragen/Zustimmungsrunden, ein Testfall-Skript
kann daher vorzeitig enden (`SkriptEndeFehler`), wenn es eine gestellte Frage
nicht abdeckt. Für die Frage "sind POIs/Tagesplan/API-Routen sinnvoll?" ist
der Dialog selbst irrelevant – dieses Skript testet NUR die deterministische
Planungskette (Grundprinzip 3), ganz ohne die Möglichkeit einer Rückfrage,
weil hier schlicht niemand fragt.

Nutzt bei vorhandenem `GOOGLE_MAPS_API_KEY` (siehe .env) echte APIs, sonst
Mock-Daten (MOCK_MODE, wie überall im Projekt) – KEINE erfundenen Daten.

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

from src.api.flightapi import erzeuge_flug_client
from src.api.google_maps import erzeuge_client
from src.api.hotelbeds import erzeuge_hotel_client
from src.ausgabe.reiseplan import als_text, speichere_datei, speichere_json, speichere_poi_uebersicht
from src.fragekatalog.agent_tools import _ERGEBNISSE_VERZEICHNIS
from src.fragekatalog.schema import ReiseAnfrage
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
    plan, nudge = plane_reise(anfrage, client, erzeuge_flug_client(), erzeuge_hotel_client())

    print(als_text(plan))
    if nudge:
        print(f"\n[Nachhaltigkeits-Hinweis] {nudge}")

    _ERGEBNISSE_VERZEICHNIS.mkdir(exist_ok=True)
    basisname = f"planung_{testfall_name}"
    speichere_datei(plan, _ERGEBNISSE_VERZEICHNIS / f"{basisname}.txt")
    speichere_json(plan, _ERGEBNISSE_VERZEICHNIS / f"{basisname}.json")
    poi_pfad = _ERGEBNISSE_VERZEICHNIS / f"{basisname}_pois.csv"
    speichere_poi_uebersicht(plan, poi_pfad)
    print(f"\nGespeichert unter: {_ERGEBNISSE_VERZEICHNIS}/{basisname}.{{txt,json}}, {poi_pfad.name}")


if __name__ == "__main__":
    main()

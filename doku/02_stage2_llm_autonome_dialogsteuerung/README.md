# Station 2 — Architekturwechsel: LLM-autonome Dialogsteuerung

**Zeitraum:** 11.08.2026 (ENTSCHEIDUNGSLOG.md Phase 10)
**Status:** aktuelle Basis-Architektur, seither nur noch erweitert (siehe Stationen 3–5), nicht
grundlegend verändert.
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `agent_tools.py`, `chat.py`,
`regelwerk.py` zum Zeitpunkt dieser Doku (12.08.2026); seither ggf. leicht durch die Folgestationen
ergänzt, siehe dortige Original-Dateien im Quellcode für den exakt aktuellen Stand.

## Was geändert wurde

Die feste Python-Zustandsmaschine aus [Station 1](../01_stage1_regelbasierte_dialogsteuerung/README.md)
wurde vollständig entfernt und durch eine einzige, durchgehende Agenten-Session ersetzt:

- Das LLM bekommt jetzt den **kompletten** Fragekatalog samt Kontexthinweisen und **fünf
  Werkzeuge** in einer Session (Claude Agent SDK, In-Process-MCP-Tools über `claude_agent_sdk.
  tool`/`create_sdk_mcp_server`, neues Modul `code_stand/agent_tools.py`):
  1. `speichere_feld(feld, wert)` — validiert gegen den erwarteten Rückgabetyp, speichert.
  2. `hole_api_daten(feld, ...)` — holt echte Daten für Unterkunft/Aktivitäten/Verkehrsmittel.
  3. `fehlende_pflichtfelder()` — deterministische Vollständigkeitsprüfung.
  4. `plane_reise_und_abschliessen()` — plant/verschickt die Reise; HART gesperrt, solange
     Pflichtfelder fehlen.
  5. `breche_planung_ab(grund)` — bei erkennbarem Abbruchwunsch.
- Das LLM entscheidet **selbst**, welche Frage als Nächstes drankommt, übersprungen oder erneut
  gestellt wird — keine feste Reihenfolge mehr von außen. Die Regel dafür steht im System-Prompt
  (`code_stand/regelwerk.py`): grundsätzlich jede Frage stellen, nur überspringen, wenn aus dem
  bisherigen Gespräch/einer Planungsentscheidung SICHER klar ist, dass sie
  beantwortet/gegenstandslos ist; im Zweifel immer fragen.
- `chat.py` wurde komplett neu geschrieben: eine einzelne Query-Response-Schleife
  (`ClaudeSDKClient`) statt der alten b2..b6-Funktionen (siehe `code_stand/chat.py`).
- Der Korrektur-Sondermechanismus aus Station 1 (`_ABHAENGIGE_FELDER` usw.) wurde **ersatzlos
  überflüssig**: das Modell ändert eine frühere Angabe jetzt einfach durch einen erneuten
  `speichere_feld`-Aufruf.

## Was unverändert blieb

Die komplette deterministische Trip-Building-/Optimierungs-Kette (`src/optimierung/*`,
`src/pipeline.py`, `src/ausgabe/reiseplan.py`, alle `src/api/*`-Clients,
`src/datenaufbereitung/*`) — nur die ORCHESTRIERUNG (wer stellt wann welche Frage) wurde ersetzt,
nicht die Fakten-/Planungslogik selbst. Das ist die zentrale Trennlinie, die auch nach diesem
Umbau bestehen bleiben musste: die KI führt den Dialog, baut aber nie selbst die Route.

## Warum dieser Schritt gemacht wurde

Expliziter Nutzerwunsch (siehe Station 1, "Warum diese Station verlassen wurde"). Der Nutzer wurde
**vor** der Umsetzung ausdrücklich darauf hingewiesen, dass diese Änderung den zu diesem Zeitpunkt
in CLAUDE.md als "nicht verhandelbar" markierten Architektur-Grundprinzipien 1 und 3 sowie der
bisherigen kostenlosen, deterministischen End-zu-Ende-Testbarkeit widerspricht. Als Alternative
wurde angeboten, nur die bestehende Skip-Logik zu generalisieren und den Kontrollfluss weiter
regelbasiert zu lassen — der Nutzer hat sich nach dieser Aufklärung bewusst für den vollständigen
Umbau entschieden.

## Bewusst akzeptierter Kompromiss

Gesprächsverhalten (was das Modell fragt/überspringt) ist seither **nicht mehr per pytest
automatisiert testbar** — nur die reinen Werkzeug-/Validierungsfunktionen bleiben es
(`tests/test_agent_tools.py`). `main.py`-Testfälle laufen seither zwangsläufig gegen die echte,
kostenpflichtige LLM-Session statt kostenlos im Mock-Modus. Diese Konsequenz wurde dem Nutzer vorab
genannt und von ihm bewusst in Kauf genommen.

## Live-Verifikation

Zwei vollständige End-zu-Ende-Gespräche (echtes LLM, echte Google-Maps-API, ~25–30
Gesprächsrunden) plus ein gezielter dritter Testlauf für `plane_reise_und_abschliessen` bestätigten
korrektes Verhalten (echte Tool-Aufrufe, korrekte Ablehnung branchenfremder Treffer, korrektes
Nachhaken, F14-Fahrzeugwechsel-Logik funktionierte durch die neue Architektur hindurch, keine
einzige Typvalidierungsfehler über beide Läufe). Details siehe ENTSCHEIDUNGSLOG.md Phase 10.

Danach aufgetretene Bugs und Nachbesserungen: [Station 3](../03_stage3_nachbesserungen_live_test/README.md).

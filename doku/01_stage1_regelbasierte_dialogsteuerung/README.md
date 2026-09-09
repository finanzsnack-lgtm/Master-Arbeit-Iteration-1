# Station 1 — Regelbasierte Dialogsteuerung (Erstversion)

**Zeitraum:** 03.–10.08.2026 (ENTSCHEIDUNGSLOG.md Phasen 1–9)
**Status:** abgelöst durch [Station 2](../02_stage2_llm_autonome_dialogsteuerung/README.md), Code
seither vollständig gelöscht.

> **Hinweis zur Quellenlage:** Der Code dieser Station (`src/fragekatalog/zustandsmaschine.py`,
> `src/fragekatalog/llm_interpreter.py`, alte `chat.py`-Funktionen) wurde nach erfolgreicher
> Live-Verifikation der Nachfolge-Architektur bewusst gelöscht (siehe Station 2) — zu diesem
> Zeitpunkt existierte noch kein Git in diesem Projekt. Es gibt daher **keinen exakten
> Code-Duplikat** dieser Station, nur diese Beschreibung, rekonstruiert aus
> `ENTSCHEIDUNGSLOG.md` Phasen 1–9 und den zum Zeitpunkt der Löschung noch vorhandenen
> Docstring-Verweisen in benachbarten, weiterhin existierenden Modulen. Bewusste Entscheidung
> (siehe `doku/README.md`), hier nichts als "Original" auszugeben, was tatsächlich Rekonstruktion
> wäre.

## Wie das Programm hier funktionierte

Eine feste, deterministische Python-Zustandsmaschine (`Dialogschleife` in
`zustandsmaschine.py`) steuerte den kompletten Gesprächsablauf von außen:

1. Sie ging den `FRAGEKATALOG` (`katalog.py`, K1–K18 mit bedingten Folgefragen) **strikt der
   Reihe nach** durch — die Fragenfolge war zu diesem Zeitpunkt im Code festgelegt, nicht dem
   Gesprächsverlauf überlassen.
2. Für **jeden einzelnen Schritt** rief sie das LLM über einen `ClaudeAntwortInterpreter`
   (`llm_interpreter.py`) auf — aber jeweils nur für einen eng vorgegebenen Zweck: Frage
   formulieren ODER Antwort analysieren ODER Vorschlag formulieren ODER Zustimmung auswerten,
   nie mehrere Aufgaben gleichzeitig. Diese Aufrufe erzwangen über `ClaudeAgentOptions.
   output_format={"type": "json_schema", ...}` ein festes JSON-Schema pro Zweck.
3. Eine Skip-Logik existierte nur an **einer** Stelle fest einprogrammiert: F11
   (Sicherheitsbedürfnis) war als `ueberspringbar=True` markiert, alles andere wurde immer
   gefragt, unabhängig vom Gesprächskontext.
4. Für automatisierte Tests/`main.py` gab es einen zweiten, parallelen `RegelbasierterInterpreter`
   — ein reiner Komma-Split-Parser ohne LLM-Beteiligung, damit Tests kostenlos und deterministisch
   liefen (siehe Phase 1: "automatisierte Tests dürfen nicht von einem externen LLM-Aufruf
   abhängen").
5. Eine nachträgliche Änderung einer bereits gegebenen Antwort mitten im Dialog brauchte einen
   eigenen Sondermechanismus (`_ABHAENGIGE_FELDER`, `betroffene_korrektur_fragen`,
   `frage_zur_korrektur_zuruecksetzen`, `springe_zu_frage` in `zustandsmaschine.py`,
   `_behandle_aenderungswunsch_falls_vorhanden`/`fuehre_korrekturschleife_aus` in `chat.py`) — die
   feste Ablaufsteuerung konnte Korrekturen nicht organisch behandeln.

## Was in dieser Station bereits gut funktionierte (blieb in Station 2 unverändert)

- Die komplette deterministische Trip-Building-Kette: `src/optimierung/*` (TOPTW/ILS,
  Monte-Carlo-Härtetest), `src/pipeline.py`, `src/ausgabe/reiseplan.py`, alle `src/api/*`-Clients.
- `katalog.py`/`schema.py` als kanonische Quelle für Feldnamen/Typen/Pflichtstatus.
- `vorschlaege.py::hole_echte_daten_fuer_vorschlag` als zentrale Dispatch-Funktion für echte
  Daten.
- Die Audio-Kanal-Abstraktion (`IOKanal`) und die Prompt-Protokollierung (`protokoll.py`).

## Warum diese Station verlassen wurde

Der Nutzer erlebte die feste Fragenreihenfolge als unnötig starr — jede Anfrage musste komplett
durch den Katalog, ohne dass aus dem Gesprächsverlauf bereits Beantwortetes berücksichtigt werden
konnte, außer an der einen fest programmierten Ausnahme (F11). Zusätzlich fiel während eines
Testlaufs auf, dass Aktivitäten (v.a. Restaurant-/Bar-Suche) grundsätzlich schlecht eingeplant
wurden — das war zwar ursächlich ein separater Bug (siehe Station 3), verstärkte aber den Eindruck,
dass die starre Ablaufsteuerung dem eigentlichen Ziel im Weg stand. Der explizite Nutzerwunsch:
"Ich gebe meinem Chatbot all die Tools, all die Fragen, all den Regelkatalog und lasse […] den User
einfach nur mit dem Chatbot kommunizieren, ohne irgendeine Zwischeninstanz über meinen Code."

Details zur eigentlichen Umstellung: [Station 2](../02_stage2_llm_autonome_dialogsteuerung/README.md).

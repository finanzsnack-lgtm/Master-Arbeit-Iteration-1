# Station 4 — Projektstruktur aufgeräumt

**Zeitraum:** 11.08.2026 (ENTSCHEIDUNGSLOG.md Phase 12)
**Auslöser:** "Reiseplan, Allergie, Barrierefreiheit, JSON und Text. [...] Wozu ist das alles? Das
steht für mich nicht nach nötig aus." — lose generierte Ausgabedateien lagen direkt im
Projekt-Wurzelverzeichnis, teils verwaist (z.B. `reiseplan_allergie_barrierefrei.*`, dessen
zugehöriger Testfall längst nicht mehr existierte), und erschwerten die Übersicht über den
eigentlichen Quellcode.

## Was geändert wurde

- Generierte Reiseplan-Ausgaben (Text/JSON/POI-CSV) landen jetzt gesammelt in `ergebnisse/` statt
  einzeln lose im Projekt-Wurzelverzeichnis (`src/fragekatalog/agent_tools.py`,
  `_ERGEBNISSE_VERZEICHNIS`). `main.py`/`chat.py` geben weiterhin nur einen Basisnamen vor (z.B.
  `reiseplan_chat`), der Zielordner ist jetzt zentral an einer Stelle festgelegt.
- Bestehende, teils verwaiste Dateien wurden dorthin verschoben statt gelöscht (keine Daten
  verworfen, nur einsortiert).
- `.gitignore` entsprechend auf einen einzigen `ergebnisse/`-Eintrag vereinfacht (vorher mehrere
  einzelne `reiseplan_*`-Muster).
- Neues `README.md` im Projektordner erklärt kurz, was jedes Top-Level-Verzeichnis/jede Datei ist
  und wie man das Programm startet.

## Was bewusst NICHT geändert wurde

`src/` selbst blieb unverändert — die vier Architektur-Schichten (siehe
[Station 2](../02_stage2_llm_autonome_dialogsteuerung/README.md)) waren durch den Umbau bereits
klar gegliedert. Der eigentliche Störfaktor waren generierte Laufzeit-Ausgaben im selben
Verzeichnis wie der Quellcode, nicht die Code-Struktur selbst.

## Einordnung

Reine Aufräumarbeit ohne Verhaltensänderung des Programms — keine funktionale Nachbesserung wie
[Station 3](../03_stage3_nachbesserungen_live_test/README.md), sondern Vorbereitung dafür, dass
der Quellcode für Dritte (Betreuer, Prüfer) nachvollziehbar bleibt.

Weiter zu: [Station 5](../05_stage5_bahn_teilstrecken/README.md).

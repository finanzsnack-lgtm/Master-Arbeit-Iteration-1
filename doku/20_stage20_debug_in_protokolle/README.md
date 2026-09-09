# Station 20 — Debug-Ausgabe bei jeder echten Planung, Ablage in protokolle/

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 39)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Nutzerfrage: "wo kann ich sehen, welche Ein-/Ausgaben an Optimierung 1/Monte-Carlo gingen?" –
Antwort war bisher "nur über `pruefe_planung.py`" (Station 17). Nutzerwunsch danach: das soll auch
beim Testen über den echten Dialog (Chat/Web) automatisch entstehen, UND in `protokolle/` liegen,
NICHT in `ergebnisse/`/einem reinen Test-Ordner – Begründung: `pruefe_planung.py` selbst gilt als
Test-Werkzeug, das beim finalen Code-Extrakt für die Abgabe eher rausfliegt ("diese ganzen
Testdinger, die nehmen wir am Ende alle raus"), die Debug-Ausgabe UND das Sitzungsprotokoll
(`protokolle/`) sollen dagegen als nachvollziehbarer, bleibender Bestandteil der echten Anwendung
erhalten bleiben.

## Umsetzung

- `pipeline.py::plane_reise` erzeugt jetzt IMMER eine `PlanungsDebugSammlung` (kein optionaler
  Parameter mehr) und gibt sie als DRITTEN Rückgabewert zurück: `plan, nudge, debug_sammlung =
  plane_reise(...)`. Kostet praktisch nichts (nur Referenzen auf ohnehin berechnete Daten).
- `agent_tools.py::plane_reise_und_abschliessen` (der tatsächliche Pfad für chat.py/webapp.py)
  schreibt sie bei JEDEM Planungsversuch (auch einem an der Barrierefreiheit gescheiterten ersten
  Versuch, zur Fehlersuche) als `<protokoll_stem>_debug.txt` NEBEN das Sitzungsprotokoll – NUR wenn
  ein `Protokollierer` gesetzt ist (in Tests ohne Protokollierer: kein Absturz, kein Schreiben).
- `pruefe_planung.py` schreibt seine Debug-Datei jetzt ebenfalls nach
  `protokolle/planung_<testfall>_debug.txt` statt nach `ergebnisse/` – EIN einheitlicher Ort
  unabhängig vom Einstiegspunkt.

## Verifikation

Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) – Debug-
Datei landet jetzt korrekt in `protokolle/`.

## Tests

2 neue Tests in `test_agent_tools.py` (Debug-Datei entsteht neben dem Protokoll, wenn ein
Protokollierer gesetzt ist; kein Absturz/keine Datei ohne Protokollierer), 3 bestehende Mocks auf
das neue 3-Tupel angepasst. Komplette Suite: 252/252 grün.

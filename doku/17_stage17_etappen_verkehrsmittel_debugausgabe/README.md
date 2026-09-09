# Station 17 — Verkehrsmittel je Etappe im Reiseplan, Planungs-Debug-Ausgabe

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 36)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Drei Rückmeldungen nach dem Ausprobieren von Kostenschätzung/Hotel-Karte (Station 16):

1. Wunsch nach Anzeige, wie lange man zwischen den POIs unterwegs ist und mit welchem
   Verkehrsmittel geplant wurde — ausdrücklich NICHT vom Optimierungsalgorithmus selbst berechnet,
   sondern von Google abgerufen. Zwei Umsetzungsvarianten zur Wahl gestellt (vorher alle
   Kandidaten-Paare multimodal abfragen vs. erst optimieren, dann nur die gewählten Etappen erneut
   abfragen) — nach Recherche Variante B empfohlen und vom Nutzer bestätigt.
2. Wunsch nach einer Debug-Ausgabedatei je Testlauf, die zeigt, welche Rohdaten der Conversational
   Agent (bzw. hier: die deterministische Planung) bekommt, welche davon an Optimierung 1
   weitergegeben werden, und was dabei herauskommt.
3. Dieselbe Ausgabe zusätzlich für den Monte-Carlo-Härtetest (Eingabe + Ergebnis), zum Vergleichen.

## Recherche zu Punkt 1

Die reine Fahrzeit zwischen POIs kam bereits VOR dieser Änderung real von Google
(`aufbereitung.py::hole_reisezeitmatrix`, VOR dem Optimierungslauf abgerufen) — der Algorithmus
selbst berechnet nichts. Es fehlte nur: (a) die Anzeige, welches Verkehrsmittel gemeint war, und
(b) die Möglichkeit, dass unterschiedliche Etappen unterschiedliche (vom Nutzer genannte)
Verkehrsmittel nutzen — bisher war die GESAMTE Reise auf EIN global abgeleitetes Verkehrsmittel
festgelegt.

## Umsetzung

- `aufbereitung.py::modi_fuer_lokalen_transport` (ersetzt `modus_fuer_lokalen_transport`) erkennt
  jetzt ALLE in F14 genannten Verkehrsmittel statt nur das erste Treffer im internen Dict, sortiert
  nach der Position des jeweils frühesten Treffers IM TEXT.
- `hole_reisezeitmatrix` fragt bei mehreren genannten Verkehrsmitteln die Distance Matrix je Modus
  ab (weiterhin ein NxN-Aufruf pro Modus) und nimmt je Paar die schnellere Zeit — das bestimmt
  direkt, mit welchem Tempo Optimierung 1 tatsächlich rechnet.
- Neue Funktion `ergaenze_anfahrt_modus_je_etappe` (Variante B): läuft NACH Optimierung 1, NUR für
  die tatsächlich besuchten Etappen. Bei nur einem genannten Verkehrsmittel (Regelfall) ohne
  zusätzlichen API-Aufruf; bei mehreren mit einem gezielten Aufruf je Etappe/Modus. Neues Feld
  `Besuch.anfahrt_modus` (toptw.py) — rein für die Anzeige, verändert `ankunft`/`abfahrt` nicht.
- Anzeige in `reiseplan.py::als_text`/`als_html`/`als_kartendaten` + `static/index.html`.
- Neues Modul `src/ausgabe/debug.py` (`PlanungsDebugSammlung`/`schreibe_debug_datei`) —
  `pipeline.py::plane_reise` bekommt einen optionalen `debug_sammlung`-Parameter, der (nur wenn
  übergeben) an jedem relevanten Schritt befüllt wird: rohe Google/Overpass-Treffer, nach harten
  Einschränkungen, an Optimierung 1 weitergegebene Kandidaten, Optimierung-1-Eingabe/-Ergebnis,
  Härtetest-Eingabe/-Ergebnis. `pruefe_planung.py` schreibt daraus `<name>_debug.txt`.
- **Live-Fund während des Smoke-Tests:** `monte_carlo.py::_instanz_mit_gestoerten_fahrzeiten`
  stürzte mit `math domain error` ab, wenn zwei POIs so nah beieinander liegen, dass Google 0
  Minuten Reisezeit meldet (`math.log(0)`) — unabhängiger, vorbestehender Bug, behoben (mindestens
  1 Minute vor der Logarithmus-Bildung, analog zum bestehenden Luftlinien-Fallback).

## Nutzerentscheidungen aus der Rückfrage

- Variante B (nicht vorab alle Kandidaten-Paare multimodal abfragen).
- Pro Etappe wird NUR EIN Verkehrsmittel genannt (kein Alternativen-Vergleich).
- Debug-Ausgabe NUR aus `pruefe_planung.py`.
- Format: strukturierte, vorsortierte Textdatei statt JSON.

## Entdeckte, noch offene Lücke

`planungs_testfaelle/` existierte beim Smoke-Test nicht mehr (siehe ENTSCHEIDUNGSLOG.md, "Offene
Punkte") — für den Live-Test neu angelegt (`smoketest_etappen.json`), die ursprünglichen Testfälle
wurden NICHT rekonstruiert.

## Tests

13 neue/umbenannte Tests (`test_aufbereitung.py`: 6, `test_reiseplan.py`: 4, `test_debug.py` neu:
3) plus ein echter Live-Lauf gegen die Google API zur Verifikation (`pruefe_planung.py`), da
`plane_reise` selbst keine pytest-Integration hat. Komplette Suite: 239/239 grün.

# Station 16 — Erstes Nutzertest-Feedback: Kostenschätzung, Hotel-Karte, Websuche, Mikrofon

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 35)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Fünf Rückmeldungen nach dem ersten echten Testlauf von `webapp.py` (Station 15). Zwei davon
widersprachen bestehenden, bewusst getroffenen Entscheidungen — deshalb vor der Umsetzung erst per
Rückfrage geklärt statt einfach übernommen:

1. Kosten (Aktivitäten, Hotel, Fahrt) sollen ins Budget mit einfließen, inkl. einer realistischen
   Verpflegungspauschale pro Tag.
2. Hotel-Foto+Preis sollte schon bei der Bestätigungs-Rückfrage im Chat erscheinen — widerspricht
   der Station-15-Entscheidung "Karten nur im fertigen Reiseplan".
3. Mikrofon-Knopf + Vorlesefunktion für den Browser-Chat.
4. Freier Web-Zugriff für den Agenten ("die braucht er doch zum Recherchieren") — widerspricht
   Grundprinzip 1-3 (alle Fakten NUR aus den definierten API-Modulen).
5. Bug-Report: die Vorschau-Suche fand bei mehreren genannten Städten (Magdeburg/Potsdam/Berlin)
   nur Treffer in der ersten — UND der Bot hatte im Chat live behauptet, die finale Planung würde
   später "noch alle drei Städte einzeln durchsuchen".

Vor der Umsetzung wurden die Punkte 1/2/4/5 per Rückfrage geklärt (Punkt 3 unmissverständlich
genug, um direkt umzusetzen, mit Hinweis auf einen fehlenden Firefox-Support).

## Root-Cause zu Punkt 5

`ReiseAnfrage.primaeres_reiseziel()` (schema.py) liefert IMMER nur `zielregionen[0]`. Das nutzen
sowohl die Vorschau (`vorschlaege.py`) ALS AUCH die finale Planung (`pipeline.py::plane_reise`) —
die Behauptung des Bots im Live-Test ("später werden alle drei Städte durchsucht") war schlicht
falsch, eine unbelegte Aussage über die eigene Architektur.

## Umsetzung

- **Kostenschätzung** (Rückfrage-Ergebnis: nur informativ, keine harte Nebenbedingung): neues Modul
  `src/optimierung/kostenschaetzung.py` (Preistabellen `price_level` → grobe Euro-Schätzung +
  Verpflegungspauschale 35 €/Tag), neue Felder `POI.preisniveau`/`ReiseAnfrage.
  unterkunft_preisniveau`/`Reiseplan.geschaetzte_kosten_euro`/`kosten_unvollstaendig`/
  `budget_gesamt`, Anzeige + Budgetvergleich in `reiseplan.py::als_text`/`als_html`.
- **Hotel-Karte live im Chat** (Rückfrage-Ergebnis: nur bei F15, sonst bleibt's bei Station 15):
  neue `IOKanal.zeige_karte(unterkunft)`-Methode (No-Op bei TextKanal/AudioKanal), aufgerufen von
  `chat.py::hauptablauf` nach jedem Turn, sobald ein neuer Unterkunft-Kandidat gefunden wurde.
  `WebIOKanal.zeige_karte` (webapp.py) lädt das Foto sofort herunter und schickt eine eigene
  `hotel_karte`-WebSocket-Nachricht, `static/index.html` rendert sie als Karten-Bubble im
  Chat-Verlauf.
- **Websuche für den Agenten** (Rückfrage-Ergebnis: bewusst zugelassen, informierte Entscheidung
  gegen Grundprinzip 2): `chat.py` erlaubt zusätzlich das eingebaute `WebSearch`-Werkzeug,
  `regelwerk.py` erklärt die Grenze (Recherche/Kontext ja, POI-/Preis-/Reisezeit-Fakten bleiben
  ausschließlich bei den 5 MCP-Tools). CLAUDE.md entsprechend als dokumentierte Ausnahme ergänzt.
- **Zielregionen-Klarstellung** (Rückfrage-Ergebnis: minimal, nur ein Hinweis, keine echte
  Multi-Stadt-Unterstützung): F07-`kontext_hinweis` (katalog.py) + eine Verteidigungslinie
  `_mehrere_zielregionen_hinweis` in `vorschlaege.py` an allen drei Such-Einstiegspunkten, die dem
  LLM bei JEDEM betroffenen Tool-Aufruf erneut verbietet, eine spätere Mehrstädte-Suche zu
  behaupten.
- **Mikrofon + Vorlesefunktion**: rein clientseitig in `static/index.html` (Web Speech API,
  `SpeechRecognition`/`speechSynthesis`) — kein Python-Code betroffen. Nutzt Mikrofon/Lautsprecher
  DES BROWSERS/GERÄTS, nicht die des Servers (anders als `AUDIO_MODUS`/`AudioKanal`, das für einen
  entfernten Web-Client ohnehin nicht funktionieren würde).

## Tests

21 neue Tests (`test_kostenschaetzung.py` neu, `test_kanal.py` neu, `test_webapp.py` neu, plus
Ergänzungen in `test_google_maps.py`/`test_reiseplan.py`/`test_vorschlaege.py`/
`test_agent_tools.py`). Mikrofon/Vorlesen sind reines Browser-JS ohne Python-Gegenstück — manuell
verifiziert wie der Rest der Chat-UI. Komplette Suite: 224/224 grün (203 + 21 neue).

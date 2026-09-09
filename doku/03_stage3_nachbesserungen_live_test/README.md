# Station 3 — Nachbesserungen nach dem ersten Live-Test der neuen Architektur

**Zeitraum:** 11.08.2026 (ENTSCHEIDUNGSLOG.md Phase 11)
**Auslöser:** Ein echter `chat.py`/`main.py`-Testlauf des Nutzers (hypothetische Reise nach
Innsbruck) direkt nach [Station 2](../02_stage2_llm_autonome_dialogsteuerung/README.md) deckte
zwei echte Bugs und einen breiten Verständnis-/Nachvollziehbarkeits-Bedarf auf. Auf ausdrücklichen
Nutzerwunsch ("führe alle Punkte um, priorisiere sie, setze sie alle um") an einem Stück
umgesetzt.

## Bug 1: Restaurants/Cafés wurden nie gefunden

**Symptom:** Obwohl im Dialog explizit "zweimal am Abend essen, mittags Kaffee" genannt wurde,
kamen nur Museen/generische Sehenswürdigkeiten als Vorschlag.

**Ursache:** `vorschlaege.py::hole_echte_daten_fuer_vorschlag`s `aktivitaeten_interessen`-Zweig
las `anfrage.aktivitaeten_interessen` — dieses Feld ist beim **ersten** Durchlauf durch eine
Typ-C-Frage aber noch leer (wird erst NACH Zustimmung über `speichere_feld` gesetzt). Die
POI-Suche lief dadurch faktisch mit einer leeren Kategorienliste und fiel auf den generischen
Fallback `tourist_attraction` zurück.

**Fix:** Neuer Parameter `aktivitaeten_aktuell` sowohl in `hole_echte_daten_fuer_vorschlag` als
auch im Werkzeug `hole_api_daten` — das LLM übergibt jetzt explizit die vollständige, noch
unbestätigte Interessenliste. Der System-Prompt weist das LLM zusätzlich an, dabei wirklich ALLE
genannten Interessen mitzugeben, nicht nur die mit Vertiefungsbedarf.

## Bug 2: Ein bestätigtes Verkehrsmittel wurde von Optimierung 2 überstimmt

**Symptom:** Nutzer bestätigt im Dialog "ich fahre mit dem Auto" — der finale Reiseplan zeigt
trotzdem Bahn für Hin-/Rückreise.

**Ursache:** `pipeline.py::plane_reise` bewertete immer ALLE echten Alternativen (Bahn/Auto/
Fernbus) nach Zeit/Kosten/CO2 und nahm automatisch die objektiv beste — das ignorierte eine
bereits im Dialog getroffene, konkrete Nutzerentscheidung vollständig. Da die CO2-Gewichtung
(Grundprinzip 5: Bahn-Nudging) strukturell die Bahn begünstigt, gewann praktisch immer die Bahn,
unabhängig davon, was der Nutzer wollte.

**Fix:** Neue Funktion `_nur_bestaetigte_verkehrsmittel` — Optimierung 2 bewertet weiterhin
gewichtet, aber nur noch innerhalb der vom Nutzer bestätigten Auswahl (Fallback auf alle
Alternativen nur bei unklarem Freitext, kein Absturz).

## Aufräumen: Reste der alten Architektur (Station 1) entfernt

Auf Nutzerwunsch ("Code reviewed, alles rausgeschmissen, was aus der alten Architektur unnötig
ist") wurden verwaiste Elemente entfernt: `schema.py::FrageZustand` (seit Station 2 verwaist),
`Protokollierer.llm_aufruf` (nirgends mehr aufgerufen), `regelwerk.py::baue_regelwerk_text`s
`tool_modus=False`-Zweig (kompletter alter Gateway-Text, seit Station 2 toter Code). Dabei wurden
**zwei weitere echte Funktionslücken** gefunden (nicht nur Kosmetik): `aktivitaeten_mit_
spezialrecherche` (Overpass-Flag) und `aktivitaeten_gewichtung` (vergleichende Präferenz) wurden
von `speichere_feld` bisher nirgends auf `ReiseAnfrage` persistiert — die Chat-Vorschau nutzte sie
korrekt, aber die spätere finale Planung hätte sie nie gesehen. Beide sind jetzt zusätzliche
optionale Argumente von `speichere_feld`.

## Neue Funktion: F20 — Tagesstart-Präferenz + kategoriebezogene Tageszeitfenster

**Auslöser:** "Ich sollte nicht direkt nach dem Aufstehen in die Bar gehen — das soll dem
Tagesablauf logisch angepasst werden" + "es standen gar keine Uhrzeiten dran".

**Umsetzung:**
1. `aufbereitung.py::wende_tageszeitfenster_an` hebt `POI.opening` je nach Place Type auf eine
   kategoriebezogene Mindest-Tageszeit relativ zum jeweiligen Tagesbeginn an (Bar erst ab 8h in
   den Tag hinein, Nachtclub 9h, Restaurant 3h, ...) — ohne eine absolute Uhrzeit zu erfinden,
   nur relativ zum (ggf. erfragten) Tagesbeginn.
2. `reiseplan.py` zeigt ab Tag 2 echte Uhrzeiten (`tagesstart_minuten + relative Zeit`) statt
   "nach Xmin" — nur wenn der Nutzer F20 tatsächlich beantwortet hat. Tag 1 bleibt immer relativ,
   da die tatsächliche Ankunftsuhrzeit der Hinreise nirgends real feststeht (kein echtes Ticket
   vorhanden).

## Neue Funktion: POI-Übersicht als CSV-Export

**Auslöser:** "Ich brauch ein Dokument, wo mir alle POIs aufgezeigt werden, sodass ich sagen kann,
dass dieser Optimierungsalgorithmus funktioniert" — Bedarf für die Evaluation der Masterarbeit.

**Umsetzung:** `reiseplan.py::speichere_poi_uebersicht` schreibt eine Zeile pro POI-**Kandidat**
(nicht nur die tatsächlich eingeplanten): Score, Zeitfenster, Besuchsdauer, Quelle, ob/wann
eingeplant. Semikolon-getrennt mit UTF-8-BOM (deutsches Excel), automatisch bei jedem
erfolgreichen `plane_reise_und_abschliessen` mitgeschrieben.

## Sonstiges

Ein Architektur-Schema (Diagramm des Anfrage-Flusses durch die vier Schichten) wurde als Artifact
veröffentlicht, siehe README.md des Hauptprojekts.

Weiter zu: [Station 4](../04_stage4_struktur_aufraeumen/README.md).

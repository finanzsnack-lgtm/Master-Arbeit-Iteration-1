# Station 22 — Barrierefreiheit LLM-beurteilt, geführte Touren, Restaurants raus aus Optimierung 1

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 41)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Ein echter Live-Test (Berlin, Familie mit zwei Kindern) zeigte zwei konkrete Probleme: Tag 3 blieb
komplett leer, obwohl eine Reiseleitung/Führung gewünscht war (F04 `reiseleitung_gewuenscht=true`
beantwortet, aber im Code nirgends verwendet); ein gewünschtes Abendessen mit der Familie wurde als
normaler POI behandelt und von Optimierung 1 komplett aussortiert. Zusätzlich fiel beim Nachdenken
über die Reisetempo-Frage (F10) auf: das LLM bekam nie mitgeteilt, welche Wörter die bisherige
Barrierefreiheits-Keyword-Suche überhaupt auslösen – eine sinngemäße, aber nicht wörtliche Antwort
lief unbemerkt ins Leere.

## Umsetzung

**Barrierefreiheit/Reisetempo (F09/F10/F15):** `schema.py::barrierefreiheit_oder_eingeschraenkt()`
durchsuchte bisher drei Freitextfelder nach ~13 festen Wörtern. Analog zu F11 (`sicherheit_
bedenklich`) ersetzt: neues Feld `ReiseAnfrage.barrierefreiheit_bedenklich: bool`, vom LLM per
Tool-Argument bei `speichere_feld` gesetzt, wenn es aus dem GESAMTEN Gesprächskontext eine
Mobilitätseinschränkung erkennt – nicht auf ein Feld beschränkt. Alle downstream Effekte
(Geschwindigkeit/Pausen/Nähe-Gewichtung, harter Ausschluss) bleiben unverändert deterministisch.

**Geführte Touren:** Ein erster Vorschlag (F04 deterministisch verdrahten) wurde vom Nutzer
ausdrücklich abgelehnt – das LLM soll selbst entscheiden, wann eine Tour-Suche nötig ist. Umgesetzt
als reine `kontext_hinweis`-Ergänzung in `katalog.py` (F04 und F16): das LLM nimmt bei erkanntem
Tour-Wunsch selbst einen konkreten Suchbegriff in `aktivitaeten_interessen` auf – dieselbe
bestehende `suche_pois`-Freitextsuche, kein neuer Mechanismus. Zusätzlich, unabhängig von der
Trigger-Frage: ein Tag ohne eingeplantes Programm zeigt jetzt 2–3 gefundene, aber nicht platzierte
Kandidaten statt nur "kein Programm eingeplant" (`reiseplan.py::_verteile_beispiele_auf_leere_tage`).

**Restaurants raus aus Optimierung 1:** Ein ursprünglicher Vorschlag (Restaurant fest ans Tagesende
anhängen) wurde vom Nutzer im selben Gespräch revidiert. Neue Funktion `pipeline.py::_trenne_
beispielrestaurants_ab`: essensbezogene Treffer (`besuchsklasse == "mahlzeit"`) werden VOR
Optimierung 1 aus der Kandidatenliste entfernt, nach Entfernung zur Unterkunft sortiert und als
`Reiseplan.beispielrestaurants` zurückgegeben. Cafés/Bars sind nicht betroffen. Anzeige je Tag
(`reiseplan.py::_restaurants_fuer_tag`, rotierender 3er-Ausschnitt).

## Verifikation

Live gegen die echte Google API smoke-getestet (Testfall mit den Interessen `["Museum",
"Restaurants", "geführte Tour"]`): die Tour-Suche fand reale Anbieter, die sogar direkt in Tag 1
eingeplant wurden; beide Tage zeigten unterschiedliche, echte Beispielrestaurants; kein Restaurant
tauchte in der normalen Tagesroute oder doppelt in "Weitere Empfehlungen" auf.

## Tests

Neue Tests in `test_fragekatalog.py`/`test_agent_tools.py`/`test_pipeline.py`/`test_reiseplan.py`,
bestehende Barrierefreiheit-Tests in `test_aufbereitung.py`/`test_vertraeglichkeit.py`/
`test_vorschlaege.py` auf das neue Flag umgestellt. Komplette Suite: 264/264 grün.

## Offener Punkt (beantwortet, nicht umgesetzt)

Echte Hotelpreise (statt Preisniveau-Schätzung) bräuchten eine gesonderte Hotel-/OTA-Preis-API –
die auf Google Maps sichtbaren Booking/Hostelworld-Preise stammen aus Google Hotel Ads, einem
getrennten Partnerprodukt, nicht über den normalen `GOOGLE_MAPS_API_KEY` erreichbar. Siehe
ENTSCHEIDUNGSLOG.md "Offene Punkte".

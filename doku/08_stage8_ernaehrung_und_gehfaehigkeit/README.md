# Station 8 — Ernährungspräferenz, eingeschränkte Gehfähigkeit + echte Distanzmatrix

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phasen 18–19)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `google_maps.py`,
`poi_sammlung.py`, `aufbereitung.py`, `toptw.py`, `schema.py`, `pipeline.py`, `vorschlaege.py` zum
Zeitpunkt VOR dieser Session (deckt alle drei unten beschriebenen Änderungen ab, die in einem
durchgehenden Arbeitsblock entstanden sind).

## Zwei Themen in einem Rutsch

Der Nutzer brachte in derselben Nachricht zwei Wünsche, die beide über die neue
Freitext-POI-Suche (siehe [Station 6](../06_stage6_freitext_poi_suche/README.md)) bzw. Optimierung
1 laufen:

1. "Auch muss bei den Ernährungspräferenzen drauf geachtet werden, dass wenn eine geäußert wird,
   die ausgewählten Restaurants den Ausprägungen angepasst werden."
2. "Wenn ich angebe, dass ich Schwierigkeiten habe zu gehen, dann müssen die Gehzeiten neu
   berechnet werden, Pausen eingeplant werden, dazu sollten dann POIs die nah am Hotel liegen höher
   gewichtet werden, so dass die Person auch einen schönen Urlaub haben kann."

## Ernährungspräferenz → Restaurant-Suche

Nutzt dieselbe Text-Search-Architektur wie Station 6: eine erkannte Ernährungspräferenz (z. B.
"vegetarisch") wird VOR den Interesse-Text in die Google-Places-Query gesetzt ("vegetarisch
Restaurants in Innsbruck"), aber NUR bei essen-bezogenen Interessen (Schlüsselwort-Erkennung),
nicht bei z. B. "Klettern". Googles eigene Suchrelevanz übernimmt die eigentliche Umsetzung – kein
selbst gepflegtes Zuordnungswissen, was "vegetarisch" bedeutet.

Live-Test (Innsbruck, Interesse "Restaurants", Präferenz "vegetarisch"): "One green table" landet
unter den Top-Treffern.

## Eingeschränkte Gehfähigkeit — drei Anpassungen

Neue, von `barrierefreiheit_wichtig()` unabhängige Erkennung (`ReiseAnfrage.
eingeschraenkte_gehfaehigkeit()`), weil eine ANDERE Konsequenz folgt: nicht Orte ausfiltern,
sondern die Planung selbst anpassen.

1. **Gehzeiten neu berechnen**: Geschwindigkeit sinkt von 4.5 auf 2.0 km/h — nur wenn die Person
   ohnehin zu Fuß unterwegs ist (ein bestätigtes Auto-Tempo wird nicht künstlich verlangsamt).
2. **Pausen einplanen**: neue Nebenbedingung im ILS-Kern (`TOPTWInstanz.pause_intervall_minuten`)
   — nach 120 Minuten kumulierter Fahr-/Aktivitätszeit wird vor dem nächsten Besuch automatisch
   eine 20-Minuten-Pause eingeplant (als zusätzliche Wartezeit, keine eigene Pseudo-Station). Die
   Ausgabe zeigt das jetzt explizit ("davon X Min. Pause/Wartezeit"), damit eine ungewöhnlich lange
   Besuchsdauer nicht wie ein Fehler aussieht.
3. **POIs nah am Hotel höher gewichten**: neue Funktion `gewichte_nach_naehe_zum_depot` – ein
   glatt abfallender Score-Faktor (nicht harter Cutoff), bei 1.5 km Entfernung auf die Hälfte
   gefallen. Die bestehende Präferenz-Gewichtung bleibt dabei relativ erhalten.

Alle drei Werte (2.0 km/h, 120min/20min, 1.5 km) sind dokumentierte, literaturunabhängige
Modellannahmen, keine erfundenen Fakten über eine konkrete Person (Grundprinzip 1) – analog zu den
bereits bestehenden Besuchsdauer-/Tageszeit-Konstanten in `google_maps.py`.

Live-Test (Innsbruck, Museen+Restaurants, "Schwierigkeiten zu gehen" + zu Fuß): Scores nicht mehr
einheitlich 3.0 (2.7/2.3/2.0 sichtbar, Nähe-Gewichtung wirkt), eine 20-Minuten-Pause korrekt vor
dem dritten Museumsbesuch eingeplant.

## Direkter Anschluss: echte Google-Distance-Matrix statt Luftlinie

Beim Live-Test der obigen Änderungen fiel dem Nutzer sofort ein drittes, unabhängiges Problem auf:
"die Zeiten sind falsch – wie werden die herangezogen?" Die angezeigten Fahrzeiten zwischen POIs
(siehe [Station 7](../07_stage7_mahlzeiten_mindestabstand/README.md)) waren unrealistisch niedrig
(z. B. "1 Min." zwischen Orten, die real deutlich weiter auseinanderliegen).

**Ursache:** `TOPTWInstanz.reisezeit_minuten` nutzte von Anfang an eine reine Luftlinien-Schätzung
(Koordinatenabstand ÷ konfigurierte Geschwindigkeit) – genau die Vereinfachung, die CLAUDE.md
unter "Optimierung 1", "Zentrale Anpassung" von Beginn an als noch zu erledigen markiert hatte:
"Distanzberechnung aus Koordinaten durch echte Reisezeiten aus der Google Distance Matrix
ersetzen". `MapsClient.distanzmatrix` existierte dafür bereits vollständig implementiert, war aber
nie mit Optimierung 1 verdrahtet.

**Fix:**
1. Neue Funktion `aufbereitung.py::hole_reisezeitmatrix` ruft einmal pro Depot-Kandidat die echte
   Distance Matrix für Depot+alle POIs ab und baut ein `(id_a, id_b) -> Minuten`-Lookup.
2. `TOPTWInstanz.reisezeiten_minuten` (neues Feld) wird von `reisezeit_minuten()` bevorzugt,
   Luftlinie bleibt Fallback für einzelne fehlende Paare (keine Route gefunden) – kein Absturz,
   keine erfundene Zeit.
3. `erstelle_toptw_instanz` bekommt einen neuen optionalen `client`-Parameter; ohne Angabe bleibt
   das alte Luftlinien-Verhalten erhalten (ältere Tests unberührt).
4. **Dabei gefundener, notwendiger Nachbesserung:** Ein einzelner Distance-Matrix-Aufruf mit ALLEN
   Orten gleichzeitig überschritt live Googles Elemente-Limit (`MAX_ELEMENTS_EXCEEDED`) schon bei
   mittelgroßen Reisen. `GoogleMapsClient.distanzmatrix` teilt seither selbst in 10×10-Kacheln auf.

Live-Verifikation: derselbe 3-Tage-Testfall zeigt jetzt 3–9 Minuten reale Fahrzeit zwischen
denselben Orten (statt zuvor 1–3 Minuten) – plausibel für tatsächliche Straßenrouten in Innsbruck.

## Tests

21 neue Tests insgesamt (Ernährung/Gehfähigkeit + Distanzmatrix) über `test_google_maps.py`,
`test_aufbereitung.py`, `test_toptw.py`. Komplette Suite danach: 200/200 grün.

## Nachbesserung (ENTSCHEIDUNGSLOG.md Phase 20, noch am selben Tag)

Beim Live-Test fiel auf: `gewichte_nach_naehe_zum_depot` lief nur INNERHALB von
`erstelle_toptw_instanz` – zu diesem Zeitpunkt hatte `waehle_top_pois` die Kandidaten aber schon
rein nach Interesse (ohne Distanzbezug) auf die Obergrenze gekappt, die Nähe-Gewichtung konnte die
Auswahl selbst nicht mehr beeinflussen. Fix: beide Aufrufer (`pipeline.py`, `vorschlaege.py`)
wenden dieselbe Gewichtung jetzt zusätzlich VOR der Kappung an (grober Zielort als Näherung, da
der echte Unterkunfts-Standort erst später feststeht).

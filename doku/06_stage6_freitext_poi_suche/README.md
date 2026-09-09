# Station 6 — POI-Suche: Freitext statt fester Google-Place-Type-Zuordnung

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 15)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `google_maps.py`, `typen.py`,
`aufbereitung.py`, `overpass.py` zum Zeitpunkt VOR dieser Änderung.

## Auslöser

Direkte, pointierte Nutzerrückmeldung nach einem Testlauf mit `pruefe_planung.py` (siehe
[Station 5](../05_stage5_bahn_teilstrecken/README.md)): "Ich möchte klettern und nicht ins Gym.
Das ist auf gar keinen Fall das Gleiche. [...] Ich möchte nicht, dass das in einen fixen Wert
geworfen wird. Die API soll dann ruhig nach Kletterrouten suchen. Das schafft die Google Maps API
schon." Weitere genannte Beispiele: "über Brücken spazieren gehen", "eine Runde laufen gehen" —
beides Interessen, die keiner der ~100 festen Google-Place-Type-Kategorien entsprechen.

## Ursache

`google_maps.py::suche_pois` presste jedes genannte Interesse über eine fest gepflegte
Schlüsselwort-Tabelle (`_KATEGORIE_ALIASE`) auf einen von Googles ~100 FESTEN Place Types, weil
die verwendete Google-Places-Nearby-Search zwingend einen solchen Typ verlangt. Für "Klettern" gab
es dort keinen passenden Typ — "gym" war der einzige halbwegs verwandte, vermischte aber
Kletterhallen mit gewöhnlichen Fitnessstudios. Für Interessen ganz ohne Tabelleneintrag
("Laufen", "Brücken") griff der generische Fallback `tourist_attraction` (Museen,
Sehenswürdigkeiten) — thematisch komplett daneben.

## Die Lösung: Google Places Text Search statt Nearby Search

Google bietet neben der typgebundenen Nearby Search auch eine **Text Search**
(`place/textsearch/json`), die beliebigen Freitext als `query` akzeptiert (z.B. "Klettern in
Innsbruck") und Googles eigene Suchrelevanz zur Interpretation nutzt — ohne dass ein fester Typ
vorgegeben werden muss. `suche_pois` ruft jetzt **eine Text Search pro genanntem Interesse** auf,
mit dem Interesse wörtlich als Suchtext.

Jeder Treffer trägt in einem neuen Feld `POI.nutzerinteresse` (`typen.py`) exakt den Text, für den
er gefunden wurde. Das Präferenz-Scoring (`aufbereitung.py::berechne_poi_score`) prüft seither nur
noch strukturell, ob `poi.nutzerinteresse` unter den aktuell genannten Präferenzen ist — die
gesamte vorherige Rate-Logik (Alias-Tabelle plus eine Sonderregel für den Gym/Kletterhallen-Fall)
entfällt ersatzlos, weil ein POI aus der Suche "Klettern" per Konstruktion ein Klettern-Treffer
ist.

## Was bewusst unverändert blieb

`overpass.py` (OSM-Zusatzquelle für Aktivitäten mit Schwierigkeitsgrad wie Klettern/Wandern/Ski)
behält seine feste Aktivitäts-Tag-Tabelle — dort ist das technisch nötig: OSM selbst taggt nur
eine feste, uneinheitliche Menge an Schlüsseln (`sport=climbing`, `route=hiking`, ...), es gibt
keine Textsuche, die das ersetzen könnte. Overpass-Treffer setzen jetzt aber ebenfalls
`nutzerinteresse`, damit sie im selben Scoring-Mechanismus landen wie Places-Treffer.

## Live-Verifikation (Berlin/Innsbruck-Beispiel)

Direkter Aufruf von `suche_pois("Innsbruck", ["Klettern"])`: liefert KI-Kletterzentrum Innsbruck,
Boulderanlage Amras, Höttinger Steinbruch — echte Kletterorte, kein einziges generisches
Fitnessstudio. `suche_pois("Innsbruck", ["über Brücken spazieren gehen"])`: liefert Innbrücke,
Freiburger Brücke, Mühlauer Brücke — echte Brücken. Beides wäre unter der alten Architektur gar
nicht oder falsch gefunden worden. End-to-End über `pruefe_planung.py` mit gemischten Interessen
(Klettern + Laufen + Brücken-Spaziergang) verifiziert: Optimierung 1 plant daraus einen
plausiblen Tag aus echten, interessenpassenden Orten.

## Tests

9 veraltete Tests entfernt (`_waehle_place_types`-Tests, Gym/Boulderhalle-Namensprüfungs-Tests –
beide auf die entfernte Logik zugeschnitten), 5 neue ergänzt (Text-Search-Query-Aufbau,
`nutzerinteresse`-Tagging, Score-Matching ohne Kategorie-Ratelogik). Komplette Suite: 178/178 grün.

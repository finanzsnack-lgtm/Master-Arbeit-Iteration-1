# Station 5 — Echte Bahn-Umstiegsdaten statt nur Gesamtdauer

**Zeitraum:** 12.08.2026
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `typen.py`, `google_maps.py`,
`reiseplan.py` zum Zeitpunkt dieser Änderung.

## Auslöser

Nutzerfrage: "Wieso werden keine Bahnverbindungen rausgesucht? Ich möchte, dass das Programm nicht
nur sagt 'mit Bahn brauchst du eine Stunde', sondern: die Bahn ... 30 min dahin, dann umsteigen in
die ... mit 5 min Wartezeit, dann 25 min Fahrzeit."

## Ursache

`google_maps.py::_hole_route` las von Googles Directions-Antwort nur `legs[0]` (Gesamtdauer,
Gesamtdistanz) — die `legs[0].steps`, in denen Google tatsächlich jede einzelne Teilstrecke einer
ÖPNV-Verbindung mit Linie, Ein-/Ausstiegshaltestelle und Zeitstempeln auflistet, wurden komplett
verworfen.

## Was geändert wurde

1. **Neuer Typ `Teilstrecke`** (`src/api/typen.py`): Modus (TRANSIT/WALKING), Linie,
   Ein-/Ausstiegshaltestelle, Fahrzeit, Wartezeit vor dem Abschnitt.
2. **`_teilstrecken_aus_steps`** (`src/api/google_maps.py`): liest `legs[0].steps` aus der echten
   Google-Directions-Antwort aus. Wartezeit wird als Zeitlücke zwischen der Ankunfts- und
   Abfahrtszeit zweier aufeinanderfolgender TRANSIT-Schritte berechnet — nur wenn Google beide
   Zeitstempel liefert, sonst bleibt sie `None` statt geraten zu werden (Grundprinzip 1: keine
   erfundenen Fakten).
3. **Ausgabe** (`src/ausgabe/reiseplan.py`, Text + HTML-Mail): zeigt zusätzlich zur Gesamtdauer
   jetzt die einzelnen Umstiege/Linien an (`_teilstrecken_zeilen`).

## Ein Bug während der Umsetzung gefunden und behoben

Der erste Live-Test gegen die echte API (Berlin → München) zeigte: Bei `mode=driving` liefert
Google zwar auch `steps`, aber das sind Abbiege-Kleinschritte ("links abbiegen" ...), keine
Umstiege. Ungefiltert hätte das zu über 20 sinnlosen "Fußweg"-Zeilen bei einer simplen Autofahrt
geführt. **Fix:** Teilstrecken werden nur noch für `mode=transit` (Bahn/Fernbus) gebaut, Auto
bleibt bei der einfachen Gesamtdauer — genau der Fall, den `Teilstrecke`s eigener Kommentar in
`typen.py` als Zweck beschreibt ("NUR bei Bahn/Fernbus gefüllt").

## Verifikation

- 4 neue Tests (`tests/test_google_maps.py`: Umstiegskette + Wartezeit-Berechnung;
  `tests/test_reiseplan.py`: Text-/HTML-Ausgabe mit und ohne Teilstrecken) — komplette Suite danach
  186/186 grün.
- Live gegen die echte Google-Directions-API getestet (Berlin Hauptbahnhof → München
  Hauptbahnhof): Bahn zeigt korrekt "ICE 1007: Berlin Hauptbahnhof → München Hauptbahnhof
  (249 min)"; eine simulierte Fernbus-Route mit drei echten Umstiegen zeigte plausible
  Wartezeiten je Umstieg.

## Einordnung

Reine Ausgabe-/Datenauswertungs-Erweiterung, keine Änderung an Optimierung 1/2 selbst — die
Wahl des Verkehrsmittels und dessen Gesamtdauer (für die Zielfunktion relevant) bleiben
unverändert, nur wird sie jetzt mit echten Details statt nur einer Zahl dargestellt.

# Station 25 — Geführte Touren: eigener reservierter Tag statt Optimierung 1, Performance-Fix

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 44)
**Kein Code-Duplikat:** Wie bei Station 24 wurde für diese Änderung KEIN Code-Stand-Snapshot vor
der Umsetzung angelegt (direkte Weiterarbeit während der laufenden Live-Diagnose). Transparent
vermerkt statt verschwiegen.

## Auslöser

Live-Vorfall in der Web-Oberfläche: der Chat blieb bei einer echten Anfrage (Rollstuhl, "geführte
Tour" + "Restaurants" + "Sehenswürdigkeiten" als Interessen) sichtbar hängen. Diagnose über das
echte Sitzungsprotokoll: `mobilitaetseinschraenkung_stufe="stark"` (Station 23) löst für JEDEN
Roh-Treffer einen eigenen, echten Google-Places-Details-Aufruf aus – durch die dritte Suche
("geführte Tour", erst seit Station 22 wirksam) stieg die Roh-Trefferzahl auf ~60, macht ~60
sequenzielle API-Aufrufe.

## Umsetzung

Geführte Touren laufen NIE durch Optimierung 1 (analog zu Restaurants, Station 22) UND werden VOR
jeder teuren Prüfung auf einen kleinen Pool begrenzt:

- Neue Erkennung `google_maps.py::ist_tour_bezogenes_interesse` über `POI.nutzerinteresse`.
- Neue Funktion `pipeline.py::_trenne_tour_beispiele_ab`: trennt Tour-Treffer VOR `filtere_pois_
  hart` ab, begrenzt auf 8 nächstgelegene zur Unterkunft, wählt daraus 3 aus — ohne Score/Ranking.
- Barrierefreiheits-Anforderung an die 3 gezeigten Touren, gestaffelt: "leicht"/None keine Prüfung;
  "mittel" mindestens die Hälfte eindeutig bestätigt barrierefrei; "stark" alle — reicht der Pool
  nicht aus, werden ehrlich weniger als 3 gezeigt statt eine unbestätigte Tour zu erfinden.
- Werden Touren gefunden, wird der LETZTE Tag komplett aus Optimierung 1 herausgenommen
  (`erstelle_toptw_instanz` bekommt einen neuen Parameter `anzahl_tage_override`) und bekommt
  stattdessen die 3 Touren direkt eingetragen (`Reiseplan.tour_tag_beispiele`).

## Verifikation

Live gegen die echte Google API smoke-getestet (dieselbe Kombination wie beim Live-Vorfall):
Laufzeit sank von "hängt sich sichtbar auf" auf ca. 37 Sekunden — Tag 3 zeigt korrekt 2 gefundene,
eindeutig bestätigt barrierefreie Touren, keine Tour taucht in Tag 1/2 oder doppelt in "Weitere
Empfehlungen" auf.

## Tests

Neue Tests in `test_pipeline.py`, `test_aufbereitung.py`, `test_reiseplan.py`. Komplette Suite:
284/284 grün.

## Offener Punkt

Die restlichen `ist_barrierefrei()`-Aufrufe für normale POI-Kandidaten laufen weiterhin sequenziell
— trägt zur verbleibenden Laufzeit (~37 Sek.) bei. Parallelisierung vorgeschlagen, noch nicht
beauftragt.

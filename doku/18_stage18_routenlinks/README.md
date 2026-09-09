# Station 18 — Google-Maps-Routen-Links für jede Etappe und die An-/Abreise

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 37)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Nutzer-Feedback nach dem ersten erfolgreichen Test der Etappen-Zeiten/Verkehrsmittel (Station 17):
"Das find ich auch ganz total gut [...] mich würde nur noch freuen, wenn [...] die Route mitgegeben
wird, wo Du direkt auf Google Maps kommst [...] und direkt Start-/Endpunkt hast [...] das soll alles
so bleiben, wie's ist, nur dass hinten dran halt noch ein Link gehangen wird."

Vor der Umsetzung als eigene Aufgabe formuliert und vom Nutzer bestätigt ("ja genau so") – bewusst
KEINE Rückfrage-Runde nötig, da die Aufgabe technisch eindeutig war (rein additiv, bestehendes
Directions-URL-Schema von Google).

## Umsetzung

- Neue Funktion `reiseplan.py::routen_link(ursprung, ziel, travelmode)` nutzt Googles
  dokumentiertes Directions-URL-Schema
  (`https://www.google.com/maps/dir/?api=1&origin=...&destination=...&travelmode=...`) – KEIN
  zusätzlicher API-Aufruf, reine Link-Konstruktion aus bereits vorhandenen Koordinaten/Orten.
  `ursprung`/`ziel` akzeptieren sowohl Koordinaten-Tupel (Etappen) als auch Ortsnamen-Strings
  (An-/Abreise, Google löst diese selbst auf). `None` bei fehlendem Punkt statt eines geratenen
  Startpunkts (Grundprinzip 1).
- Vor-Ort-Etappen (Unterkunft→POI, POI→POI): Koordinaten beider Punkte + `Besuch.anfahrt_modus`
  (Station 17) als `travelmode` – Googles interne Modus-Strings (walking/bicycling/transit/driving)
  sind bereits identisch zu den von der Directions-URL erwarteten Werten.
- Hinreise/Rückreise: neue Zuordnung `_TRAVELMODE_JE_VERKEHRSMITTEL` ("Bahn"/"Fernbus" → transit,
  "Auto" → driving), Ortsnamen (`anfrage.wohnort`/Zielort) statt Koordinaten.
- Neue Felder `Reiseplan.unterkunft_koordinaten`/`wohnort`/`zielort` – NUR für diese Links, die
  eigentliche Optimierung nutzt weiterhin `anfrage.*` direkt (pipeline.py). Von `plane_reise` aus
  bereits vorhandenen lokalen Variablen befüllt.
- Eingebaut in `als_text`/`als_html`/`als_kartendaten` (`reiseplan.py`) + `static/index.html`
  ("Route ansehen"-Link je Karte) – rein additiv, bestehender Text/bestehende Struktur unverändert.

## Verifikation

Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) – Links für
Etappen (Koordinaten) UND Hin-/Rückreise (Ortsnamen) korrekt gebildet.

## Tests

10 neue Tests in `test_reiseplan.py` (4 für `routen_link` direkt, 6 für die Einbindung in
als_text/als_html/als_kartendaten). Komplette Suite: 249/249 grün.

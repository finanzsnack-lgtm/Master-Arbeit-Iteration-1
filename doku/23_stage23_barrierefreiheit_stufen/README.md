# Station 23 — Barrierefreiheit in drei Stufen statt einem Bool

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 42)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Direkte Rückfrage nach Station 22: *"Bei Barrierefreiheit sollte es aber verschiedene Stufen
geben... jemand, der einfach nur ein bisschen langsamer geht als jemand, der im Rollstuhl ist, das
sind Unterschiede."* Auf Bitte des Nutzers zuerst eine Recherche, welche Stufen sich anhand echter
verfügbarer Daten überhaupt sinnvoll unterscheiden lassen (keine erfundene Steigungs-/
Stufen-Erkennung) — die einzige strukturierte Barrierefreiheits-Quelle ist `wheelchair_accessible_
entrance` (Google Places), es gibt keine Steigungs-/Terrain-Daten für einzelne Orte oder Fußwege.

## Umsetzung

`ReiseAnfrage.barrierefreiheit_bedenklich: bool` (Station 22) ersetzt durch `mobilitaetseinschraen
kung_stufe: str | None` mit drei Werten, vom LLM per Tool-Argument bei `speichere_feld` gesetzt
(überschreibbar, kann im Gesprächsverlauf verfeinert werden):

- **"leicht"** (z. B. altersbedingt langsameres Tempo): jeder Ort bleibt nutzbar, kein POI-/
  Unterkunft-Ausschluss — nur die bestehenden Tempo-/Pausen-/Nähe-Anpassungen.
- **"mittel"** (z. B. Krücken/Gehhilfe): schließt zusätzlich Orte aus, die explizit als nicht
  barrierefrei bestätigt sind — unbekannte bleiben (bisheriges Standardverhalten).
- **"stark"** (z. B. Rollstuhl): nur eindeutig bestätigt barrierefreie Orte/Unterkünfte gelten als
  unbedenklich — ein unbekannter Status zählt hier zusätzlich als Ausschlussgrund.

Umgesetzt in `vertraeglichkeit.py::_barrierefreiheits_kriterium` (gemeinsame Konflikt-Logik für
`filtere_pois_hart`/`filtere_unterkuenfte_barrierefrei`/`pruefe_barrierefreiheit_des_plans`).
`katalog.py` (F09/F10/F15) weist das LLM in den `kontext_hinweis`-Texten auf die drei Stufen hin.

## Verifikation

Live gegen die echte Google API smoke-getestet (Testfall mit `mobilitaetseinschraenkung_stufe:
"stark"`): ein Museum mit unbekanntem Barrierefreiheits-Status wurde korrekt als nicht eindeutig
bestätigt erkannt (Warnhinweis, da einziger Treffer der Kategorie); Tempo/Pausen griffen wie
erwartet.

## Tests

Bestehende Barrierefreiheit-Tests auf die drei Stufen umgestellt, neue Tests je Stufe. Komplette
Suite: 271/271 grün.

# Station 27 — Lokaler Kontakt (F19): Mittags-Zeitblock für Markt/Café statt totem Feld

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 47)
**Kein Code-Duplikat:** Wie bei den Stationen 24–26 wurde für diese Änderung kein
Code-Stand-Snapshot vor der Umsetzung angelegt. Transparent vermerkt statt verschwiegen.

## Auslöser

`lokaler_kontakt_wichtig` (F19) war ein viertes totes Feld (nach `reiseleitung_gewuenscht`,
`lernaktivitaeten_interesse`, siehe Stationen 22/26). Auf Bitte des Product Owners erst konkrete
Beispiele erarbeitet, dann ein eigenständiges Konzept entwickelt — ausdrücklich NICHT einfach das
Touren-/Lernaktivitäten-Schema kopiert ("wir teilen jetzt nicht alles nach dem gleichen Konzept, es
wirkt sehr unprofessionell").

## Umsetzung

Ein drittes Strukturmuster, weder "eigener reservierter Tag" (Touren/Lernaktivitäten) noch "keine
Tagesbindung" (Restaurants):

- An "vollen" Tagen (nicht Anreise-, nicht Abreisetag) bekommt Optimierung 1 120 Minuten weniger
  Tagesbudget — der Algorithmus lässt den Mittagsblock dadurch von selbst frei.
- Neue Funktion `pipeline.py::_trenne_markt_beispiele_ab` (Café- und Markt-POIs) liefert 3 echte,
  nächstgelegene Beispiele je vollem Tag, rotierend, nicht an einen bestimmten Tag gebunden.
- Der bestehende Beispielrestaurants-Mechanismus wurde ergänzt statt verdoppelt: `besuchsklasse ==
  "bar"` wird jetzt zusätzlich erfasst (Kneipen landen bei Google oft unter "bar"), und F19 löst bei
  Bedarf einen zusätzlichen Kneipen-Suchbegriff aus.
- `_trenne_sonderkategorie_ab` (Touren/Lernaktivitäten) wurde generalisiert: Prädikat prüft jetzt
  den ganzen POI statt nur `nutzerinteresse`, da Café-Erkennung über `besuchsklasse` läuft.
- Erkennung bleibt bewusst nur die Antwort auf F19 selbst, nicht der gesamte Gesprächsverlauf.
- Touren/Kochkurse mit Einheimischen und Vereine bewusst NICHT mit reingenommen.

## Verifikation

Live gegen die echte Google API smoke-getestet (4-Tage-Reise): Tag 1/4 zeigen korrekt keine
Markt-Beispiele, Tag 2/3 zeigen je 3 echte, unterschiedliche Wochenmärkte, Beispielrestaurants
enthalten jetzt echte Kneipen, reduziertes Budget an Tag 2/3 sichtbar (weniger Programm als Tag 1/4).

## Tests

Neue Tests für `_trenne_markt_beispiele_ab`, `ist_markt_bezogenes_interesse`, Bar-Erfassung in
`_trenne_beispielrestaurants_ab`, bestehende Sonderkategorie-Tests auf die generalisierte
POI-Prädikat-Signatur umgestellt. Komplette Suite: 291/291 grün.

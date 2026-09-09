# Station 26 — Lernaktivitäten (F17): konkrete Kurse wie geführte Touren, unkonkrete Antworten bekommen eine Empfehlung

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 46 — siehe dort auch Phase 45, Härtetest-Schwelle
95%→80%, kleine Konfigurationsänderung ohne eigene Station)
**Kein Code-Duplikat:** Wie bei den Stationen 24/25 wurde für diese Änderung KEIN
Code-Stand-Snapshot vor der Umsetzung angelegt. Transparent vermerkt statt verschwiegen.

## Auslöser

Nutzerfrage: "Was macht der Code, wenn ich angebe, ich möchte auf der Reise etwas lernen?" –
Recherche ergab: `lernaktivitaeten_interesse` (F17) war ein totes Feld, exakt derselbe Zustand wie
`reiseleitung_gewuenscht` vor dessen Verdrahtung (Station 22). Auf Bitte des Product Owners erst ein
Konzept für mögliche Antwortkategorien erarbeitet, dann per Rückfragen bestätigt.

## Umsetzung

**Bucket A – konkrete, ortsgebundene Aktivität (z. B. "Kochkurs"):** Genau wie geführte Touren
behandelt (Rückfrage-Ergebnis: *"das möchte ich auf jeden Fall lernen"* darf nie vom
Optimierungsalgorithmus aussortiert werden können). `pipeline.py::_trenne_tour_beispiele_ab` wurde
zu `_trenne_sonderkategorie_ab` verallgemeinert (nimmt ein `gehoert_zur_kategorie`-Prädikat statt
fest auf Touren zu prüfen) – dieselbe Pool-Begrenzung, Beispielanzahl und
Barrierefreiheits-Staffelung gilt jetzt für beide Kategorien. Neue Erkennung `google_maps.py::
ist_lernaktivitaet_bezogenes_interesse`. Werden beide Kategorien gefunden, werden zwei getrennte
Tage reserviert (`reiseplan.py::_reservierte_sondertage` ordnet sie den letzten Tagen zu).

**Bucket B – unkonkrete Aussage (z. B. "ich möchte offen sein und dazulernen"):** Keine echten Daten
zu suchen, aber das LLM soll nicht stumm weitergehen – `katalog.py` F17 weist es an, eine kurze,
allgemeine Empfehlung zu geben (bekannte, real existierende Angebote wie "Duolingo" dürfen beim
Namen genannt werden, keine erfundenen Fakten über den konkreten Zielort).

## Prozess-Hinweis (Doku-Format)

Product Owner wollte kein neues, separates Dokument für "Konzepte je Frage". Auflösung: CLAUDE.md
ist bereits das lebende, stets aktuelle Dokument für den Jetzt-Zustand, ENTSCHEIDUNGSLOG.md bleibt
bewusst das unveränderliche, chronologische Warum.

## Verifikation

Live gegen die echte Google API smoke-getestet (Interessen `["Museum", "geführte Tour",
"Kochkurs"]`, 4-Tage-Reise): Tag 1+2 normal optimiert, Tag 3 zeigt 3 echte Tour-Anbieter, Tag 4
zeigt 3 echte Kochschulen – keine Überschneidung.

## Tests

`_trenne_tour_beispiele_ab`-Tests auf die generalisierte `_trenne_sonderkategorie_ab` umgestellt,
neue Tests für Lernaktivitäts-Erkennung und getrennte Tage. Komplette Suite: 287/287 grün.

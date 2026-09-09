# Station 19 — Präzisere Hin-/Rückreise-Routen-Links

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 38)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Zwei Nachbesserungen direkt nach dem Ausprobieren der Routen-Links (Station 18), beide vor der
Umsetzung per Rückfrage geklärt (Analyse zuerst vorgelegt, Nutzer hat bestätigt/präzisiert):

1. Der Hinreise-/Rückreise-Link zeigte nur grob zwischen Wohnort und Zielstadt, nicht zur
   tatsächlich bestätigten Unterkunft — "die Links zeigen nur auf das Element", "das ist schon mal
   halbwegs gut".
2. Bahnhöfe tauchten am An-/Abreisetag als eigene POI-Karten (Foto+Link) in der Web-UI auf —
   "das möchte ich natürlich nicht haben. Ich möchte da nur die POIs drinnen stehen haben."

## Umsetzung

- `reiseplan.py::_hinreise_ziel_fuer_link` bevorzugt die genauen Unterkunft-Koordinaten
  (`Reiseplan.unterkunft_koordinaten`, seit Station 18 vorhanden), Rückfall auf den groben
  Zielort-Namen nur ohne bestätigte Unterkunft. Hinreise-Link: Wohnort → genaue Unterkunft.
  Rückreise-Link: genaue Unterkunft → Wohnort. Vor-Ort-Etappen-Links (POI-zu-POI) waren bereits
  präzise, unverändert. **Bleibt bestehen.**
- Für Punkt 2 zunächst eine pauschale Ausschlussliste für Bahnhof-Place-Types in `suche_pois`
  gebaut – **direkt danach auf Nutzerwunsch wieder vollständig zurückgenommen** (siehe
  ENTSCHEIDUNGSLOG.md Phase 38, Nachtrag): Bahnhöfe sollen als POI-Kandidat grundsätzlich weiter
  möglich bleiben ("ich möchte mir die Bahnhöfe angucken [können]"), eine pauschale
  Typ-Ausschlussliste war "nicht zielführend". Das ursprünglich gemeldete Symptom (Bahnhof-Karten
  am ersten/letzten Tag, gelabelt "An- und Abreise") ist damit **weiterhin offen** – siehe
  ENTSCHEIDUNGSLOG.md, "Offene Punkte".

## Verifikation

Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) — Hinreise-/
Rückreise-Link zeigt jetzt korrekt auf die Unterkunft-Koordinaten statt nur die Stadt.

## Tests

1 neuer Test (`test_reiseplan.py`: präzise Hin-/Rückreise-Link-Bevorzugung) + 1 bestehender Test
angepasst. Komplette Suite: 250/250 grün.

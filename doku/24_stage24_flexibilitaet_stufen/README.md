# Station 24 — Flexibilitätspräferenz als LLM-beurteilte 1-5-Skala

**Zeitraum:** 17.08.2026 (ENTSCHEIDUNGSLOG.md Phase 43)
**Kein Code-Duplikat:** Anders als bei den übrigen Stationen wurde für diese Änderung KEIN
Code-Stand-Snapshot vor der Umsetzung angelegt (Implementierung begann direkt nach Bestätigung der
Stufen-Tabelle im Gespräch) — analog zur bereits in Phase 32 dokumentierten Ausnahme. Transparent
vermerkt statt verschwiegen.

## Auslöser

Direkte Anschlussfrage nach Station 23 (Barrierefreiheits-Stufen): F05 (`flexibilitaet_praeferenz`)
wurde zwar abgefragt, aber der bisherige Mechanismus zählte nur Schlüsselwörter und wirkte sich
ausschließlich auf die reine Anzahl POIs pro Tag aus — keine Wirkung auf die zeitliche Verteilung
innerhalb des Tages. Nutzerwunsch: ein "flexibler" Tag soll nicht nur weniger Stopps haben, sondern
auch zwischendrin echten Freiraum bieten (z. B. für spontanen Kaffee/Kuchen).

## Umsetzung

Neues Feld `ReiseAnfrage.flexibilitaet_stufe: int | None` (1–5), vom LLM per Tool-Argument bei
`speichere_feld` gesetzt — ausdrücklicher Nutzerwunsch: *"Der soll jetzt nicht genau fragen, wie
flexibel Sie von eins bis fünf sein wollen, sondern er soll die Konversation führen und daraus
schließen."* Ersetzt die frühere Schlüsselwort-Zählung vollständig. Zwei Hebel je Stufe:

| Stufe | max_pois_pro_tag | Pufferpause |
|---|---|---|
| 1 (ganz durchgeplant) | kein Deckel | keine |
| 2 | 6 | keine |
| 3 | 5 | alle 3h, 15 Min. |
| 4 | 3 | alle 2,5h, 20 Min. |
| 5 (extrem flexibel) | 2 | alle 1,5h, 30 Min. |

Die Pufferpause nutzt denselben Mechanismus wie die Barrierefreiheits-Pause — treffen beide
gleichzeitig zu, gewinnt das kürzere Intervall.

## Verifikation

Live gegen die echte Google API smoke-getestet (`flexibilitaet_stufe: 5`): Optimierung 1 plante
korrekt genau 2 POIs pro Tag.

## Tests

`test_aufbereitung.py` — alte Schlüsselwort-Tests durch stufenweise Tests ersetzt. Komplette Suite:
273/273 grün.

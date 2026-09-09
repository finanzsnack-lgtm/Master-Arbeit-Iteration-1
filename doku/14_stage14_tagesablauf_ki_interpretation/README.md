# Station 14 — Tagesablauf-Zeitfenster (F20) vom LLM interpretiert statt per Regex

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 33)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Nutzerwunsch beim Blick auf `aufbereitung.py`: "Werden die Parameter für den Tagesablauf nicht
noch mit in die Anfrage für die KI mit eingesetzt, sondern hier jetzt schon wieder in Aufbereitung
noch mal extra als Code dargestellt. Das möchte ich bitte nicht [...] ohne diese Interpretation
der KI kommt da am Ende kein vernünftiger Datensatz bei raus, wenn man nur den Nutzer fragt."

## Umsetzung

`aufbereitung.py::parameter_fuer_tagesablauf` (ein Regex-Parser: erste/letzte erkannte Uhrzeit im
Freitext, sonst Standardannahme) ist komplett entfernt. Stattdessen bekommt `speichere_feld` zwei
neue, nur bei F20 (`tagesstart_praeferenz`) relevante Tool-Argumente:
`tagesstart_minuten`/`tagesende_minuten` (Minuten seit Mitternacht) — das LLM interpretiert die
Freitext-Antwort selbst und liefert diese Werte, statt dass ein starres Zahlenmuster danach sucht.
Neue Felder direkt auf `ReiseAnfrage` (schema.py).

**Wichtiger Nebenbefund:** beim Umbau fiel auf, dass der bisherige Enduhrzeit-Wert nie tatsächlich
verwendet wurde — `pipeline.py` griff nur auf `[0]` (den Start) für die Anzeige zu, das
Tagesbudget der Optimierung war immer der feste Konfigurations-Default. Die Umstellung behebt das
gleich mit: `pipeline.py::plane_reise` berechnet das Basis-Tagesbudget jetzt aus der Differenz
`tagesende_minuten - tagesstart_minuten`, wenn beide vom LLM gesetzt wurden — ein genanntes
Zeitfenster wirkt sich damit erstmals wirklich auf die Optimierung aus, nicht nur auf die
Uhrzeiten-Anzeige im fertigen Reiseplan.

## Tests

2 Tests für den entfernten Regex-Parser entfernt, 2 neue Tests für die Tool-Argument-
Persistierung in `test_agent_tools.py` ergänzt. Komplette Suite: 191/191 grün (Netto-Null).

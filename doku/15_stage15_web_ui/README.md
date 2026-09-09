# Station 15 — Web-Oberfläche (webapp.py) mit Foto-Karten statt reiner Konsole

**Zeitraum:** 13.08.2026 (ENTSCHEIDUNGSLOG.md Phase 34)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Nutzerwunsch (im Anschluss an die Code-Review-Runde aus Station 13): "ich hab keinen Bock mehr,
über die Konsole das anzusteuern [...] hätte gerne immer noch diesen normalen Chat halt offen, um
das zu testen [...] wenn ich Vorschläge bekomme [...] dass ich nicht nur da stehen hab, hier ist
ein Link zu dem und dem Hotel, sondern direkt so einen kleinen Overview, [...] Foto drin, kurz
beschrieben, was das ist, [...] Genau das Gleiche bei den POIs."

Vor der Umsetzung wurden vier Rahmenentscheidungen per Rückfrage geklärt: FastAPI (async-nativ,
passt zum bestehenden `ClaudeSDKClient`/asyncio-Code), WebSocket-Transport, Karten NUR im fertigen
Reiseplan (nicht live während des Gesprächs), Fotos serverseitig "bei API-Abruf" statt über einen
client-seitigen Key-Proxy (der Google-Maps-Key darf laut ausdrücklicher Nutzervorgabe nie im
Browser sichtbar werden).

## Umsetzung

- `src/audio/kanal.py`: `IOKanal` (Protocol) sowie `TextKanal`/`AudioKanal` auf `async def
  bot_sagt`/`async def nutzer_antwortet` umgestellt – nötig, damit ein WebSocket-basierter Kanal
  auf eine Browser-Nachricht warten kann, ohne die Event-Loop zu blockieren. Für TextKanal/
  AudioKanal selbst unschädlich (weiterhin intern blockierend, aber `chat.py` läuft ohnehin als
  einzelner Konsolen-Prozess ohne Nebenläufigkeit).
- `chat.py`: alle `io_kanal`-Aufrufe entsprechend `await`-iert; `hauptablauf` gibt jetzt den
  finalen `AgentSessionState` zurück (vorher `None`), damit ein Aufrufer wie `webapp.py` nach
  Gesprächsende noch etwas mit dem Ergebnis (Reiseplan, Maps-Client) tun kann.
- `src/api/typen.py`: `POI.foto_referenz`/`Unterkunft.foto_referenz` (aus `photos[0].
  photo_reference` der ohnehin schon laufenden Places-Suche, kein zusätzlicher API-Aufruf).
- `src/fragekatalog/schema.py`: `ReiseAnfrage.unterkunft_foto_referenz`, `src/fragekatalog/
  agent_tools.py`: beim Bestätigen der Unterkunft (F15) mit übernommen, `src/ausgabe/reiseplan.py`:
  `Reiseplan.unterkunft_foto_referenz`, `src/pipeline.py`: durchgereicht.
- `src/api/google_maps.py`: `suche_pois`/`suche_unterkuenfte` befüllen `foto_referenz` aus der
  Places-Antwort; neue Methode `MapsClient.lade_foto(foto_referenz, ziel_pfad, max_breite)` –
  `GoogleMapsClient` lädt echt über die Place Photo API herunter, `MockGoogleMapsClient` liefert
  `False` (kein erfundenes Bild, Grundprinzip 1).
- Neues Modul `src/ausgabe/fotos.py::lade_fotos_fuer_plan`: lädt EIN Foto für die Unterkunft sowie
  jeden tatsächlich eingeplanten POI herunter (bewusst NICHT `weitere_aktivitaeten_empfehlungen`),
  gibt nur Einträge für tatsächlich geglückte Downloads zurück.
- `src/ausgabe/reiseplan.py`: `_maps_link` in das öffentliche `maps_link` umbenannt (wird jetzt
  auch außerhalb des Moduls gebraucht); neue Funktion `als_kartendaten(plan, foto_url_fuer_place_id)`
  baut die strukturierten Karten-Daten (Unterkunft + POIs je Tag), kennt selbst keine URLs/Pfade
  (Callback-Parameter hält reiseplan.py frei von Web-/Dateisystem-Wissen).
- Neues `webapp.py` (Projekt-Wurzel): FastAPI-App, `WebIOKanal` (bindet WebSocket an `IOKanal`),
  `GET /` liefert `static/index.html`, `WS /ws/chat` führt `chat.py::hauptablauf` mit dem
  Web-Kanal aus und schickt nach Abschluss ein `{"typ": "ergebnis", ...}`-JSON mit Volltext,
  Nachhaltigkeits-Nudge und den Kartendaten (inkl. Foto-URLs unter `/fotos/<sitzung_id>/...`).
  `chat.py`/`pruefe_planung.py` lösen weiterhin KEINEN Foto-Download aus – nur webapp.py, damit im
  normalen Konsolen-Betrieb keine zusätzlichen API-Kosten entstehen.
- Neues `static/index.html`: eine einzelne, abhängigkeitsfreie Seite (Chat-Verlauf + WebSocket-
  Anbindung in Vanilla-JS + Ergebnis-Kartenraster), kein Build-Schritt/Frontend-Framework.
- `requirements.txt`: `fastapi`, `uvicorn[standard]` ergänzt.

## Tests

12 neue Tests: `tests/test_fotos.py` (neu, 4 Tests für `lade_fotos_fuer_plan` mit Fake-Client),
`tests/test_google_maps.py` (4 Tests für `foto_referenz`-Übernahme + `lade_foto`),
`tests/test_reiseplan.py` (3 Tests für `als_kartendaten`), plus ein manueller Smoke-Test von
`webapp.py` über Starlettes `TestClient` (Index-Route, Static-Mount) außerhalb der pytest-Suite.
Keine WebSocket-/LLM-Ende-zu-Ende-Tests in pytest – wie bei `chat.py` auch wird das eigentliche
Gesprächsverhalten manuell verifiziert, nicht automatisiert gegen echte LLM-Kosten getestet.
Komplette Suite: 203/203 grün (191 + 12 neue).

## Noch offen

Ein echter Browser-Ende-zu-Ende-Test (Chat-Durchlauf im Browser inkl. Foto-Karten mit echtem
Google-Maps-Key) steht noch aus – siehe ENTSCHEIDUNGSLOG.md, "Offene Punkte".

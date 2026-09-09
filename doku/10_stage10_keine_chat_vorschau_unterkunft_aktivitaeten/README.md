# Station 10 — Keine Hotel-/POI-Auswahl mehr im Chat

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 29)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `katalog.py`, `regelwerk.py`,
`agent_tools.py`, `vorschlaege.py` zum Zeitpunkt VOR dieser Änderung.

## Auslöser

Nutzerwunsch: "Es soll keine Auswahl mehr geben an Hotels. Es soll selber ein Hotel rausgesucht
werden nach den Maßgaben, genau dieses eine Hotel wird dann genommen [...] auf Basis dieses Hotels
kann dann die Optimierung besser durchgeführt werden." Auf Rückfrage präzisiert: "Ein Hotel soll
ausgesucht werden und dann in der Mail angegeben. Nicht nochmal im Chat aufgezeigt. Das Selbe soll
mit den POI's gemacht werden."

## Ausgangslage (wichtiger Befund vor der Umsetzung)

Bei der Klärung stellte sich heraus: die WIRKLICH final genutzte Unterkunft entstand schon vorher
automatisch — `pipeline.py::_plane_bestes_depot` testet bis zu 5 echte Kandidaten per
vollständiger Optimierung durch und nimmt den, der die beste Gesamtroute ergibt; ebenso wählt
`aufbereitung.py::waehle_top_pois` die POIs rein nach Score aus. Der Nutzer "wählte" in der
bisherigen Chat-Vorschau also gar nicht wirklich etwas aus — die Vorschau war eine reine
Zwischenanzeige, keine echte Entscheidung. Per `AskUserQuestion` wurde deshalb geklärt, ob nur die
Chat-Anzeige verschwinden soll oder auch der Auswahl-Mechanismus selbst umgebaut werden soll
(z.B. Hotel früh, vor der POI-Suche, einmalig festlegen, damit die Nähe-Gewichtung schon eine
reale Koordinate statt der groben Zielort-Koordinate bekommt). Der Nutzer entschied sich für die
einfachere Variante: nur die Chat-Anzeige entfernen, der bestehende automatische Auswahl-
Mechanismus bleibt unverändert.

## Umsetzung

F15 (`unterkunft_anforderungen`) und F16 (`aktivitaeten_interessen`) sind in `katalog.py` keine
Typ-C-Fragen (Dialogfrage mit API-Vorschau + Zustimmungsschleife) mehr, sondern normale
Typ-B-Wertfragen: das LLM erfragt nur noch die reine Anforderung/das reine Interesse als Text und
speichert sie direkt per `speichere_feld` — ohne `hole_api_daten`, ohne Kandidaten-Namen im
Gespräch, ohne Zustimmungsschleife. `verkehrsmittel_praeferenz` (F13) bleibt als einziges
Typ-C-Feld bestehen, da dort eine echte Nutzerentscheidung (Bahn/Auto/Fernbus, mit
Nachhaltigkeits-Nudge) gewollt ist.

`vorschlaege.py::hole_echte_daten_fuer_vorschlag` wurde entsprechend gekürzt: die beiden toten
Zweige (Unterkunfts-Kandidatenliste, POI-Vorschau samt Kappung/Warnschwellen-Rückfrage/
Anfahrtsempfehlung je POI) wurden vollständig entfernt, ebenso die dafür nötigen Konstanten und
Hilfsfunktionen. `trenne_bereits_im_paket_enthalten` (All-Inclusive-Sonderfall) bleibt bestehen,
da sie direkt von `agent_tools.py::speichere_feld` gebraucht wird, unabhängig von einer
Chat-Vorschau.

## Live-Verifikation

Da die eigentliche Auswahl-Logik (`_plane_bestes_depot`, `waehle_top_pois`) unverändert bleibt,
war keine neue Live-Verifikation der Planungsqualität nötig — nur die Chat-Ebene wurde entfernt.

## Tests

17 Tests entfernt (`test_vorschlaege.py`), die ausschließlich die entfernten Chat-Vorschau-Zweige
prüften; 1 Test in `test_agent_tools.py` ersetzt (prüft jetzt die Ablehnung von
`aktivitaeten_interessen` als Nicht-mehr-Typ-C-Feld). Komplette Suite: 190/190 grün.

## Nachtrag 1 (siehe ENTSCHEIDUNGSLOG.md Phase 30)

Der Aktivitäten-Teil dieser Station wurde noch am selben Tag nach einem Live-Test wieder
zurückgenommen: `aktivitaeten_interessen` (F16) ist wieder ein Typ-C-Feld mit voller
Chat-Vorschau. Nur `unterkunft_anforderungen` (F15) bleibt bei der hier beschriebenen
Vereinfachung.

## Nachtrag 2 (siehe ENTSCHEIDUNGSLOG.md Phase 31)

Auch bei F15 war "kein `hole_api_daten`-Aufruf mehr" zu weitgehend: Nutzer-Korrektur "doch es soll
die Hotel API abrufen, das ist falsch! Es soll nur nicht nochmal im Chat erwähnt werden." F15 ruft
seit Phase 31 `hole_api_daten` wieder ganz normal auf (`api_abruf_noetig=True`, echte Kandidaten
werden geholt) – nur das Ergebnis wird dem Nutzer nicht mehr vorgelesen, keine Zustimmung zu einem
bestimmten Hotel eingeholt. Der Titel dieser Station ("keine Hotel-Auswahl mehr im Chat") bezieht
sich also präzise auf die fehlende Kandidaten-Diskussion, NICHT auf einen fehlenden API-Aufruf.

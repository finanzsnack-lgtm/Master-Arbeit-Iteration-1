# Station 13 — Code-Review-Runde: sieben strukturelle Änderungen

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 32)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung. `hotelbeds.py`/`flightapi.py` fehlen darin: sie wurden vor dem
Snapshot gelöscht (Fehler des Assistenten) und wurden in dieser Sitzung nie vollständig gelesen —
für sie gibt es daher nur diese Textbeschreibung, keinen Code-Stand (wie bei Station 1).

## Auslöser

Der Nutzer legte eine eigene Code-Review mit elf Punkten (gegliedert nach Datei) vor und bat
ausdrücklich: "formuliere dir selber aus jeder Aussage eine Aufgabe und frage mich dann ab, ob ich
das wirklich so haben will wie du es interpretierst, dann setze deine Aufgaben um." Zu jedem
Punkt wurde die Absicht per `AskUserQuestion` bestätigt — dabei fielen zwei echte Widersprüche
zwischen einzelnen Review-Punkten auf (All-Inclusive sollte laut einem Punkt ausgebaut, laut einem
anderen entfernt werden; die Verkehrsmittel-Optimierung ließ zwei gegensätzliche Lesarten zu), die
erst durch Rückfrage aufgelöst wurden, bevor irgendetwas umgesetzt wurde.

## Die sieben Änderungen

1. **All-Inclusive/Flug komplett entfernt.** `src/api/hotelbeds.py`, `src/api/flightapi.py` samt
   Tests gelöscht; alle Felder/Sonderpfade in `schema.py`, `vorschlaege.py`, `agent_tools.py`,
   `pipeline.py`, `chat.py`, `pruefe_planung.py`, `emissionsfaktoren.py` entfernt. Grundprinzip 5
   ("Flüge ausgeschlossen") ist damit eine echte Hard-Rule ohne Ausnahme.
2. **Barrierefreiheit + eingeschränkte Gehfähigkeit zusammengelegt.** `schema.py` hat jetzt EINE
   Methode `barrierefreiheit_oder_eingeschraenkt()` statt zwei getrennter mit unterschiedlichen
   Konsequenzen — harter Ausschluss UND Tempo-/Pausen-/Nähe-Anpassung lösen jetzt immer gemeinsam
   aus.
3. **Sicherheit LLM-erkannt.** Die Schlüsselwort-Heuristik `sicherheit_ist_wichtig()` ist weg,
   ersetzt durch `sicherheit_bedenklich` — vom LLM aus dem Gesamtkontext gesetzt (Tool-Argument
   bei `speichere_feld`), inkl. neuer Regelwerk-Anweisung, bei erkennbar problematischem Ziel
   proaktiv eine sicherere Alternativregion vorzuschlagen.
4. **Unterkunftswahl umgebaut.** `_plane_bestes_depot` (testete bis zu 5 echte Hotels per
   vollständiger Optimierung durch) ist weg. `vorschlaege.py::suche_unterkunft` sucht jetzt GENAU
   EINE Unterkunft direkt bei F15, das LLM schlägt sie vor und holt eine einfache Bestätigung ein
   — F15 ist wieder Typ C, aber mit nur einem Kandidaten statt einer Liste.
5. **Verleih-Suche an die KI übergeben.** Die deterministische Verleih-Suche in `pipeline.py` ist
   weg, ersetzt durch `vorschlaege.py::suche_verleih_nahe_unterkunft` — läuft über `hole_api_daten`
   für F14, braucht eine bereits bestätigte Unterkunft (F15) und wählt den Verleih mit der
   geringsten Distanz dazu.
6. **Verkehrsmittel-Nudge vorgezogen.** Die Nachhaltigkeits-Gewichtung lief bisher nur einmal ganz
   am Ende — zu spät, um die F13-Entscheidung noch zu beeinflussen. Läuft jetzt zusätzlich schon
   in der F13-Chat-Vorschau selbst.
7. **Nachplanungs-Prüfung für Barrierefreiheit.** Neu: `pruefe_barrierefreiheit_des_plans` prüft
   nach der Optimierung den TATSÄCHLICHEN Plan noch einmal gegen echte Daten. Erfüllt er die
   Anforderung nicht, schlägt der Abschluss fehl und verlangt (nach Rückfrage beim Nutzer) eine
   strengere Neuplanung mit denselben Daten.

## Bewusst nicht umgesetzt

Zwei weitere, vom Nutzer im selben Gespräch geäußerte Wünsche wurden explizit auf "danach"
vertagt (Nutzerinstruktion: "mache den anderen Prompt erst fertig, dann kümmer dich um die zwei
Punkte"): die Tagesablauf-Parameter-Interpretation an die KI übergeben statt eines Regex-Parsers,
und eine Web-Oberfläche mit Bild-/Kurzinfo-Vorschau für Hotels/POIs statt der Konsole. Beide stehen
in "Offene Punkte" (ENTSCHEIDUNGSLOG.md).

## Tests

Umfangreicher Umbau: `test_vorschlaege.py`, `test_agent_tools.py` größtenteils neu geschrieben;
`test_fragekatalog.py`, `test_aufbereitung.py`, `test_reiseplan.py`, `test_vertraeglichkeit.py`,
`test_emissionsfaktoren.py` angepasst/ergänzt; `test_hotelbeds.py`/`test_flightapi.py` gelöscht.
Komplette Suite: 191/191 grün.

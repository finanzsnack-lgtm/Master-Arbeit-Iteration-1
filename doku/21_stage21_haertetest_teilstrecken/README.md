# Station 21 — Monte-Carlo-Härtetest umgestellt: An-/Abreise-Umstiege statt POI-Vor-Ort-Route

**Zeitraum:** 16.08.2026 (ENTSCHEIDUNGSLOG.md Phase 40)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien der betroffenen Dateien zum
Zeitpunkt VOR dieser Änderung.

## Auslöser

Auf Nutzerwunsch entstand zunächst `pruefe_algorithmus.py` (eigenständiges, von Hand nachrechenbares
Beispiel mit rundem Score/Reisezeiten), das jedes einzelne Datenfeld zeigt, das Optimierung 1 UND
der Härtetest bekommen. Beim Durchsehen der Reisezeiten-Matrix fiel dem Nutzer auf: der Härtetest
lief bisher auf den POI-zu-POI-Bewegungen VOR ORT (Tagesroute) – dort ist die Verpassgefahr durch
ein paar Minuten Fußweg/Fahrrad zwischen zwei Sehenswürdigkeiten praktisch irrelevant ("das bringt
ja eigentlich gar nix"). Der eigentlich riskante Teil einer Reise sind reale Bus-/Bahn-UMSTIEGE bei
der An-/Abreise: "Was ist, wenn dieser Bus fünf Minuten Verspätung hat, bekomme ich dann noch die
Bahn?"

## Umsetzung

- Der komplette bisherige POI-basierte Härtetest (`monte_carlo.py::haertetest`,
  `_instanz_mit_gestoerten_fahrzeiten`) wurde entfernt, NICHT parallel weitergeführt.
- Neue Funktion `monte_carlo.py::haertetest_teilstrecken(teilstrecken, ...)` simuliert die
  `Teilstrecke`-Kette (`typen.py`, aus echten Google-Directions-Schritten befüllt – dieselben Daten,
  die für die Umstiegsanzeige ohnehin schon abgerufen werden, kein neuer API-Aufruf): jede
  Teilstrecken-Dauer wird log-normal gestreut, bei jedem TRANSIT-Umstieg mit bekanntem
  `wartezeit_minuten`-Puffer wird geprüft, ob die aufgelaufene Verspätung noch hineinpasst. Reicht
  der Puffer nicht, gilt der Lauf als Verletzung – einfaches binäres Modell (verpasster Anschluss =
  gescheiterter Lauf), KEINE Prüfung auf eine mögliche spätere Ersatzverbindung.
- `pipeline.py::plane_reise` ruft den Härtetest nur für Hinreise/Rückreise auf, und nur wenn
  `teilstrecken` nicht leer ist (Auto oder fehlende Schritt-Details → `None` statt eines erfundenen
  Ergebnisses).
- `Reiseplan.robustheit` wurde durch `hinreise_robustheit`/`rueckreise_robustheit` ersetzt;
  `als_text`/`als_html` zeigen beide Ergebnisse getrennt ("Verbindungssicherheit
  Hinreise/Rückreise: ...").
- `src/ausgabe/debug.py` (Abschnitt 5 der Debug-Datei) zeigt für beide Richtungen die vollständige
  Teilstrecken-Kette (Linie, von/nach, Dauer, Umstiegspuffer) statt der alten TOPTW-Instanz/Route.
- `pruefe_algorithmus.py` demonstriert den neuen Härtetest an einem eigenständigen Beispiel (Bus →
  Regionalbahn → ICE über einen fiktiven "Nordhafen") – bewusst getrennt vom Optimierung-1-
  POI-Beispiel, da beide Algorithmen in der echten Pipeline ebenfalls unterschiedliche Daten
  bekommen.

## Rückfrage-Verlauf (drei Runden)

1. Erster eigener Vorschlag (Härtetest zusätzlich zum bestehenden, mit "trotz verpasstem Anschluss
   doch noch ankommen"-Logik) war falsch verstanden – Nutzer stellte klar: der POI-Test wird
   ERSETZT, nicht ergänzt, läuft nur bei Bahn/Fernbus.
2. Die Idee, bei einem verpassten Anschluss eine SPÄTERE Verbindung zu prüfen, wurde vom Nutzer
   selbst wieder verworfen, nachdem klar wurde, dass dafür Daten fehlen, die der Härtetest gar nicht
   bekommt – "sonst müssten wir wieder Daten abprüfen, und das will ich nicht".
3. Ergebnis: einfaches binäres Modell, kein zusätzlicher API-Aufruf, keine Rückfrage-Logik im
   Härtetest selbst.

## Nebenbefund (dokumentiert, NICHT behoben)

Beim manuellen Nachrechnen des `pruefe_algorithmus.py`-Optimierung-1-Beispiels wurde eine
strukturelle Schwäche der ILS-Reparaturschritt-Logik gefunden (`toptw.py::iterated_local_search`
hängt reparierte POIs nach `_shake()` immer HINTER den unveränderten Präfix an, statt auch
Positionen davor/dazwischen zu versuchen) – am Beispiel konkret nachgewiesen (Score 13 statt
möglicher 15, per `simuliere_route()` verifiziert). Nicht Teil dieser Station, siehe
ENTSCHEIDUNGSLOG.md "Offene Punkte".

## Verifikation

Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`): Hinreise und
Rückreise (jeweils EIN direkter S4-Umstieg ohne Zwischenhalt) laufen beide zu 100 % robust durch den
neuen Härtetest, Debug-Datei zeigt Abschnitt 5 korrekt in zwei Teilen.

## Tests

`test_monte_carlo.py` komplett neu (5 Tests), `test_debug.py`/`test_reiseplan.py`/
`test_agent_tools.py`/`test_fotos.py` an die neuen Felder angepasst. Komplette Suite: 254/254 grün.

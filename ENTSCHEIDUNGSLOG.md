# Entscheidungslog — Reisebot-Prototyp

Dieses Dokument hält den Programmierprozess nachvollziehbar fest: **was**
wann geändert/gebaut wurde und **warum** (bzw. warum nicht anders). Es
ergänzt die [CLAUDE.md](../CLAUDE.md) (dort stehen die grundsätzlichen,
bereits in der Konzeptionsphase getroffenen Architekturentscheidungen) um
die Entscheidungen, die *während* der Implementierung anfielen — meist
ausgelöst durch Live-Tests, bei denen sich Annahmen aus der Konzeption als
lückenhaft herausstellten.

Zielgruppe: du selbst (Begründung deiner Design-Entscheidungen in der
Masterarbeit) sowie jeder, der den Code liest und verstehen will, warum er
so aussieht, wie er aussieht. Quelle der Einträge bis 08.08. sind die
Claude-Code-Sitzungsprotokolle sowie die Rationale-Kommentare direkt in den
Modul-Docstrings (dort teils ausführlicher als hier).

**Konvention für die Zukunft:** Jede nicht-triviale Design-Entscheidung
(nicht: reine Tippfehler-/Bugfixes ohne Verhaltensänderung) bekommt hier
einen neuen Eintrag unter dem aktuellen Datum, im Format Was/Warum, 2–5
Sätze. Chronologisch anhängen, ältere Einträge nicht umschreiben.

---

## Phase 0 — Konzeption (vor 03.08.)

Vollständig in CLAUDE.md dokumentiert und dort bereits mit Quellen belegt
(Peffers et al. 2007 für DSR, Jeng & Fesenmaier 2002 / Choi et al. 2012 für
die Fragekatalog-Stufenlogik, Vansteenwegen et al. 2009/2011 und Gavalas et
al. 2014 für TOPTW/ILS). Hier nicht dupliziert.

## Phase 1 — Grundgerüst & Erstimplementierung (03.–06.08.)

- **Modulstruktur nach Architekturschichten** (`src/api`, `src/fragekatalog`,
  `src/datenaufbereitung`, `src/optimierung`, `src/ausgabe`, `src/audio`).
  *Warum:* spiegelt die Lanes aus dem Prozessmodell 1:1 — API-Zugriff,
  regelbasierte Anwendung und Optimierung bleiben eigenständig testbar und
  austauschbar (Mock- vs. Echt-Client je Schicht).

- **Fragekatalog (`katalog.py`) aus dem Rohmaterial konsolidiert**, dabei
  bewusst *transparent korrigiert statt stillschweigend repariert*: F08
  (`wohnort`) wurde ergänzt, weil Optimierung 2 einen Startort braucht, den
  das Originalmaterial nirgends erfasste; die Frage "Welches Reiseerlebnis
  streben Sie an?" wurde entfernt, weil sie sich im Praxistest mit dem freien
  Einstieg (a1) überschnitt und Nutzer dieselbe Antwort zweimal geben
  mussten. *Warum dokumentiert statt kommentarlos geändert:* Nachvollziehbarkeit
  für die Herleitung des finalen Fragekatalogs in der Arbeit.

- **Zwei Interpreter-Implementierungen** (`RegelbasierterInterpreter` für
  Tests/`main.py`, `ClaudeAntwortInterpreter` via Claude Agent SDK für den
  echten Chat). *Warum:* automatisierte Tests dürfen nicht von einem
  externen LLM-Aufruf abhängen (Kosten, Nichtdeterminismus, Netzabhängigkeit);
  gleichzeitig soll der echte Chat die volle Sprachfähigkeit des LLM nutzen.

- **Claude Agent SDK statt eigenem `ANTHROPIC_API_KEY`**: nutzt die
  bestehende Claude-Code-Anmeldung/das Abo. *Warum:* kein zusätzlicher,
  separat abzurechnender API-Key nötig.

- **TOPTW/ILS als eigenständige Python-3-Neuimplementierung, kein Direkt-Port**
  von `github.com/Constantino/TOPTW`. *Warum:* die Referenzdatei lag beim
  Bau nicht lokal vor; die Umsetzung orientiert sich an der in CLAUDE.md
  dokumentierten Struktur (Greedy-Start, ILS mit `NoImprovementCounter`,
  `shake(R,S)`). *Offen:* gegen die Referenzimplementierung abgleichen,
  sobald verfügbar.

- **Monte-Carlo-Härtetest** mit den (noch vorläufigen) Defaults 20 %
  Lognormal-Streuung, 1000 Läufe, 95 %-Schwelle. *Warum vorläufig:* CLAUDE.md
  verlangt explizit Rückfrage beim Product Owner zu Verteilung/Läufen/
  Kriterium — die Werte sind ein begründeter erster Vorschlag, kein
  abgestimmter Endwert.

- **CO2-Faktoren als feste Tabelle (`emissionsfaktoren.py`) statt Live-API**
  (Climatiq o. ä. bewusst NICHT angebunden). *Warum:* zitierfähige, stabile
  Werte für die Masterarbeit sind wichtiger als Aktualität einer Live-Quelle;
  eine Live-API wäre zudem ein weiterer Ausfallpunkt. *Offen:* Platzhalterwerte
  (Bahn 19 g/Pkm u. a.) müssen vor Verwendung in der Arbeit gegen eine
  offizielle Quelle (Umweltbundesamt) verifiziert werden.

- **Audio-Kanal als Protokoll-Abstraktion** (`IOKanal`, Text- vs.
  Audio-Implementierung), mit zwei Anbietern (`google_cloud` vs. `lokal`
  über Whisper+pyttsx3). *Warum:* der eigentliche Dialogablauf soll den
  Unterschied zwischen Tastatur- und Sprachein-/ausgabe nicht kennen müssen;
  die lokale Variante existiert, damit Sprachmodus auch ganz ohne
  zusätzlichen API-Key nutzbar ist.

- **Prompt-Protokollierung (`protokoll.py`)**: jeder LLM-Aufruf (Prompt +
  Antwort) sowie Sitzungsmeilensteine werden pro Sitzung als JSONL unter
  `protokolle/` mitgeschrieben, bewusst NICHT eingecheckt. *Warum:*
  Reproduzierbarkeit für die Fehleranalyse in der Evaluation und Beleg der
  deklarierten KI-Nutzung gemäß Uni-Vorgaben; die Dateien enthalten
  potenziell personenbezogene Testdaten (Name, E-Mail, Gesundheitsangaben),
  daher kein Repo-Artefakt.

- **Amadeus-Anbindung (`amadeus.py`) als eng begrenzte, bewusste Ausnahme**
  vom Grundprinzip "Flüge sind ausgeschlossen": Flugsuche wird NUR
  angeboten, wenn der Nutzer nach einem Alternativ-Ziel-Vorschlag
  ausdrücklich auf dem ursprünglichen, mit Bahn/Auto nicht mehr sinnvoll
  erreichbaren Ziel besteht; dieselben Credentials decken zusätzlich eine
  All-Inclusive-Hotelsuche ab, nur wenn der Nutzer das bei der
  Unterkunftsfrage ausdrücklich verlangt. *Warum keine Erfindung von
  Amenities/IATA-Codes:* Airport-Codes werden über die Amadeus-Referenzdaten
  aufgelöst statt geraten; Hotel-Amenities werden über eine
  Bestätigungsabfrage geprüft statt aus einer nicht existierenden Amenity-
  Liste erfunden (Grundprinzip 1). *Status:* implementiert, aber mangels
  Key bislang nicht live gegen die echte API getestet.

## Phase 2 — Iteration nach erstem Live-Test (05.08., Abend)

Auslöser: erstes echtes Testgespräch mit echtem Google-Maps-Key deckte
mehrere Lücken auf.

- **POI-Suche fand nur "Attraktionen"** statt auch Restaurants/Bars/Spas.
  *Ursache:* `suche_pois` fragte pro Aufruf nur eine einzige, exakt
  passende Google-Place-Type ab; unbekannte Formulierungen fielen auf
  `tourist_attraction` zurück. *Fix:* `_KATEGORIE_ALIASE` als
  Schlüsselwort-Teilstring-Suche, die mehrere Kategorien gleichzeitig
  treffen kann; Restaurant/Bar/Spa werden jetzt zusätzlich zu den erkannten
  Interessen immer mitgesucht.

- **Mail-Versand war nur Platzhalter** (`sende_mail` warf bewusst
  `NotImplementedError`). *Fix:* echte Anbindung an Mailjet Send API v3.1,
  inkl. HTML-Mail mit klickbaren Google-Maps-Links zu Unterkunft/POIs
  (dafür `place_id` bis in `Unterkunft`/`POI`/`Reiseplan` durchgereicht).
  *Warum HTML mit Links statt Text:* explizite Nutzeranforderung, die
  Vorschläge in der Mail direkt durchklicken zu können.

- **Fehlende Ortssprache**: Places lieferte Ortsnamen mal auf Litauisch,
  Arabisch, Russisch statt Deutsch. *Fix:* `language=de` fest bei jeder
  Places-Anfrage.

- **Aktivitäten wurden nicht tief genug hinterfragt** ("ich will klettern"
  reichte als vollständige Antwort, ohne Schwierigkeitsgrad/Zugang zu
  klären; bei Aktivitätswunsch wurden trotzdem generische Vorschläge wie
  Museen gemacht). *Fix:* `kontext_hinweis` von F16 erweitert, sodass das
  Vollständigkeits-Gateway (b3) bei Aktivitäten wie Klettern/Wassersport/
  Ski gezielt nachhakt, bevor die Antwort als abgeschlossen gilt — über den
  bestehenden Rückfrage-Mechanismus, ohne neue State-Machine-Logik.

- **OpenStreetMap/Overpass API als generische Zusatzquelle** für
  Aktivitäten, die Places strukturell nicht abdeckt (Klettern, Wandern mit
  `sac_scale`, Ski mit `piste:difficulty`, Tauchen, ...). *Warum Overpass
  statt einzelner Spezial-APIs pro Sportart:* eine einzige, kostenlose,
  schlüsselfreie Quelle statt zehn kommerziellen Einzelanbindungen; OSM
  taggt genau diese Aktivitäten bereits strukturiert. *Wichtige
  Leitplanke:* die Entscheidung, OB Overpass für eine genannte Aktivität
  befragt wird, trifft ausschließlich das LLM im Dialog
  (`spezialrecherche_aktivitaeten`) — der eigentliche Abruf bleibt
  regelbasierter, deterministischer Code ohne LLM-Beteiligung
  (Grundprinzip 1). Nicht erzwungen, nur bei Bedarf. Zwei Stolpersteine
  dabei behoben: Overpass lehnt den Standard-`requests`-User-Agent mit 406
  ab (eigener User-Agent gesetzt); Schwierigkeitsgrad-Tags sind uneinheitlich
  benannt (`climbing:grade:uiaa` vs. `:french` u. a.) — mehrere
  Tag-Kandidaten werden der Reihe nach geprüft.

- **POI-Scoring-Bug**: `berechne_poi_score` verglich Nutzerpräferenzen per
  rohem Substring gegen `poi.kategorie`. Bei echten Google-Places-Daten ist
  `kategorie` der rohe *englische* Place Type ("museum"), während
  Nutzerpräferenzen deutscher Freitext sind ("Kultur") — der Vergleich traf
  praktisch nie, alle POIs bekamen effektiv denselben Score. *Fix:*
  zentrale, wiederverwendbare Alias-Auflösung (`alias_place_types_fuer`)
  statt duplizierter Kategorie-Logik in `google_maps.py`/`overpass.py`;
  live verifiziert (vorher überall Score 1.0, danach korrekt differenziert).

- **Vergleichende Präferenzfrage statt Zahlenbewertung**: auf die Frage, wie
  POIs bei zu vielen Treffern eingegrenzt werden sollen, wurde zunächst eine
  Bewertungsfrage pro POI erwogen (skaliert schlecht, bis zu 30 POIs, im
  Audio-Modus unzumutbar) und dann verworfen zugunsten von "hast du mehr
  Lust auf X oder Y" — eine vergleichende Gewichtung der bereits genannten
  Kategorien statt einer Einzelbewertung jedes Ortes. *Warum:* geringerer
  Dialogaufwand für den Nutzer, passt in die bestehende Typ-C-Frageschleife;
  feuert nur, wenn tatsächlich zu viele POIs gefunden wurden, nicht
  standardmäßig.

## Phase 3 — Konfigurationsabgleich (08.08.)

- **`.env` war gegenüber `.env.example` unvollständig**: `LLM_MODELL`,
  `AUDIO_ANBIETER`, `GOOGLE_CLOUD_SPEECH_API_KEY`, `AMADEUS_API_KEY`,
  `AMADEUS_API_SECRET` fehlten komplett (nicht nur leer) in der echten
  `.env`, liefen also unbemerkt über die Code-Defaults in `config.py`.
  *Fix:* `.env` an `.env.example` angeglichen, damit alle konfigurierbaren
  Werte sichtbar/einstellbar sind, ohne bestehende gesetzte Werte
  (`GOOGLE_MAPS_API_KEY` etc.) anzufassen. Tests währenddessen durchgehend
  grün (122/122).

## Phase 4 — Zwischen 08.08. und 10.08.

Mehrere nicht-triviale Entscheidungen aus diesem Zeitraum (u. a. Korrekturschleife für
nachträgliche Antwortänderungen mitten im Dialog, Anfahrtsempfehlung je Aktivität, Tag-1-Budget
ab tatsächlicher Ankunftszeit statt ab t=0, lokaler-Transport-abhängiger Suchradius/
Geschwindigkeit, Migration der Flug-/Hotelsuche von Amadeus — Self-Service-Portal am 17.07.2026
eingestellt — auf FlightAPI.io/Hotelbeds, POI-Score-Fix gegen branchenfremde Zufallstreffer wie
Gym/Spa/Physiotherapeut) sind **nicht rückwirkend in diesem Log dokumentiert** — nur im
Gesprächsverlauf und in den jeweiligen Modul-Docstrings nachvollziehbar. Ab hier (10.08.) wird
die Konvention wieder laufend eingehalten.

## Phase 5 — "Grobe Struktur statt fertiger Plan" + harte Einschränkungs-Prüfung (10.08.)

- **Ausgabe zeigt "grobe Struktur + Empfehlungen" statt einer vollkommen fertig geplanten
  Reise.** Optimierung 1 (TOPTW/ILS) bleibt algorithmisch unverändert und liefert weiterhin
  genau EINE realisierbare, zeitfenstergeprüfte Tagesroute je Tag. Neu (`reiseplan.py`,
  `pipeline.py`): POIs, die als Kandidaten gefunden, aber NICHT in die gewählte Tagesroute
  übernommen wurden, landen als `Reiseplan.weitere_aktivitaeten_empfehlungen` zusätzlich in der
  Mail statt verworfen zu werden; Formulierungen wechseln von "Tag X:"/"gewählt" zu "Tag X –
  unser Vorschlag"/"unsere Empfehlung unter mehreren geprüften Kandidaten". *Warum:*
  Nutzerwunsch, dass Hotels/Aktivitäten als Empfehlungen präsentiert werden, aus denen sich der
  Nutzer selbst seine Reise zusammenstellt, statt eine einzige, starre Buchung vorgesetzt zu
  bekommen. Bei der Rückfrage zum Umfang wurde bewusst die Variante gewählt, die Optimierung 1
  als Kernbeitrag der Arbeit NICHT abschwächt (Alternative "nur grobe Tages-Gruppierung ohne
  feste Reihenfolge" wurde explizit abgelehnt); Unterkunft blieb unverändert, da sie bereits vor
  dieser Änderung alle Kandidaten statt nur den gewählten zeigte.

- **Neues Modul `src/datenaufbereitung/vertraeglichkeit.py`: harte Ausschlusskriterien getrennt
  von der weichen Präferenz-Gewichtung.** Prüft POI-/Unterkunft-Kandidaten NACH der Suche, VOR
  dem Präferenz-Scoring, gegen zwei vom Nutzer genannte harte Einschränkungen: Ernährung/
  Allergien (F18, namensbasierte Schlüsselwort-Heuristik gegen den POI-Namen — keine API liefert
  Zutatendaten) und Barrierefreiheit (F09/F10/F15, neue Methode `ReiseAnfrage.
  barrierefreiheit_wichtig()`, geprüft über ein echtes Datenfeld: `GoogleMapsClient.
  ist_barrierefrei()` fragt `wheelchair_accessible_entrance` per Google Place Details ab, NUR
  bei genanntem Bedarf wegen der zusätzlichen Aufrufe pro Kandidat). Ausschluss nur, wenn eine
  unbedenkliche Alternative derselben Kategorie übrig bleibt, sonst bleibt der einzige Treffer
  erhalten, aber mit Warnhinweis (`Reiseplan.einschraenkungshinweise`). Läuft identisch in der
  Chat-Vorschau UND der finalen Planung. *Warum:* Nutzerwunsch, dass eine genannte Fischallergie
  tatsächlich verhindert, dass ein auf Fisch spezialisiertes Restaurant vorgeschlagen wird (bisher
  floss F18 nur als Freitext-Suchbegriff in die Google-Places-Suche ein, ohne dass die
  gefundenen Ergebnisse aktiv dagegen geprüft wurden) — ausdrücklich auch für Barrierefreiheit
  gefordert, nicht nur für Ernährung.

## Phase 6 — Wiederverwendbare Testfälle für main.py (10.08.)

- **`testfaelle/*.json` statt einer einzigen, hart in main.py programmierten Beispielantworten-
  Liste.** Jede Datei bildet Katalog-Feldnamen (nicht Position) auf Rohtext-Antworten ab;
  main.py lädt sie per Namen (`python main.py <name>`, Default `standard`, `--liste` zeigt alle
  vorhandenen) und speichert die Ausgabe als `reiseplan_{name}.txt/.json` statt einer fest
  benannten Datei. *Warum:* Nutzerwunsch, verschiedene Antwortkombinationen durchzuspielen
  ("das Resultat sehen"), ohne bei jedem Mal alle 19 Fragen neu einzutippen oder main.py selbst
  zu editieren – ein neuer Testfall ist jetzt nur eine neue JSON-Datei. Feldname statt Position
  gewählt, damit eine künftige Umsortierung in katalog.py bestehende Testfälle nicht stillschweigend
  verfälscht (klarer Fehler statt falsch zugeordneter Antworten).
- **main.py nutzt jetzt IMMER `MockGoogleMapsClient` statt `erzeuge_client()`.** *Warum:* seit ein
  echter `GOOGLE_MAPS_API_KEY` in der `.env` steht, wählte `erzeuge_client()` automatisch den
  echten Client – main.py verlor dadurch stillschweigend seine ursprüngliche Rolle als schneller,
  kostenloser, offline lauffähiger Testfall-Runner (Testfälle mit Platzhalter-Ortsnamen wie
  "Zielregion" scheiterten dann an der echten Directions-API). Für einen Testlauf gegen die
  echte API bleibt ein eigenes, disposables Skript der richtige Ort (siehe bisherige `_smoke_*.py`-
  Praxis in diesem Projekt), main.py bleibt bewusst Mock-only.

## Phase 7 — Lokaler Fahrzeugwechsel + Verleih-Suche (10.08.)

- **F14 (lokaler_transport_praeferenz) hakt jetzt gezielt nach, wenn die gewünschte lokale
  Fortbewegung ein Fahrzeug braucht, das die Anreise nicht zwangsläufig mitbringt** (z.B. Anreise
  mit Bahn, vor Ort aber Auto oder Fahrrad gewünscht), und sucht bei Bestätigung eines Leihwunschs
  real nach einem Verleih in der Nähe. *Was:* F14s `kontext_hinweis` (katalog.py) weist das LLM an,
  die Antwort gegen die bereits bestätigte `verkehrsmittel_praeferenz` (F13) zu vergleichen und bei
  einem Fahrzeug-Bruch nachzufragen, ob eines mitgebracht oder vor Ort geliehen wird; dafür musste
  der bisher auf reine Änderungswunsch-Erkennung beschränkte Prompt-Hinweis zu `bereits_erfasst`
  (llm_interpreter.py::interpretiere) verallgemeinert werden. Die eigentliche Suche läuft
  deterministisch in `pipeline.py` (`aufbereitung.py::erkenne_leihwunsch` liest den bestätigten
  F14-Text aus, `google_maps.py` sucht mit den neuen, echten Place Types `car_rental`/
  `bicycle_store`), Ergebnis (Fund ODER ehrliche Fehlanzeige) landet in `Reiseplan.
  lokales_leihfahrzeug_gewuenscht`/`lokaler_verleih_poi`. *Warum:* Nutzerwunsch – ein Fahrzeug-
  wechsel gegenüber der Anreise soll aktiv erfragt werden, aber NUR dann (Anreise mit Auto + lokal
  Auto braucht keine Rückfrage), und ein bestätigter Leihwunsch soll zu einer echten Prüfung führen,
  nicht nur im Freitext verschwinden. Bewusste Einschränkung: Google Places kennt keinen eigenen
  "Fahrradverleih"-Typ, nur "bicycle_store" (Laden) – Ausgabe benennt das ehrlich statt einen
  garantierten Verleih vorzutäuschen (Grundprinzip 1).

## Reflektierte, aber NICHT umgesetzte Idee (10.08.)

- Nutzer-Idee: Optimierung 1 (oder die Ausgabe) könnte PRO AKTIVITÄT/ETAPPE empfehlen, mit welchem
  Verkehrsmittel man am besten dorthin kommt ("da wär's gut, mit dem Fahrrad hinzufahren, da eher
  mit Öffis") – über die reine Text-Anfahrtsempfehlung im Chat hinaus (siehe unten) auch in die
  Optimierung selbst einfließend. *Kurze Einschätzung:* Zwei bereits vorhandene Bausteine würden
  das erleichtern, sind aber noch nicht verbunden: (1) `vorschlaege.py::_anfahrtsempfehlung_je_poi`
  berechnet das schon (echte Distance-Matrix-Zeiten je Modus), landet aber NUR im Chat-Vorschlag
  (b5), nicht im finalen `Reiseplan`/der Mail – wäre die naheliegendste erste Erweiterung. (2)
  `TOPTWInstanz.geschwindigkeit_kmh` ist aktuell EINE globale Geschwindigkeit für die ganze Reise
  (aus F14 abgeleitet, siehe schema.py-Kommentar zu `lokaler_transport_praeferenz`, dort bereits als
  TODO vermerkt) statt einer modusabhängigen Zeit PRO Etappe – das wäre der tiefere, größere Eingriff
  (würde `reisezeit_minuten` und die Distanzmatrix-Berechnung in toptw.py betreffen). Nicht
  umgesetzt, nur als Idee festgehalten.

## Phase 8 — Diagnose: leere Tagesrouten in main.py (10.08.)

- **`python main.py` lieferte für den Testfall `standard` an jedem Tag "kein
  Programm eingeplant"**, trotz klarer Aktivitätswünsche. Zwei getrennte
  Ursachen gefunden und behoben/dokumentiert:
  1. `RegelbasierterInterpreter._parse` (Mock-Interpreter, siehe
     `zustandsmaschine.py`) zerlegt Mehrfachantworten nur an Kommas. Die
     Testfall-Antwort "nur kletern oder wandern und abends … Bars" enthielt
     keine Kommas und landete dadurch als EIN einziger Riesen-Präferenzstring
     statt als Liste — passte zu keiner POI-Kategorie. *Fix:* `testfaelle/
     standard.json` auf kommagetrennte Form gebracht (entspricht dem
     dokumentierten, bewusst einfachen Format des Mock-Interpreters).
     Betrifft NUR main.py/Tests — der echte `chat.py`-Pfad nutzt das LLM zur
     Extraktion und ist von diesem Bug nicht betroffen.
  2. Selbst mit sauber getrennter Liste ("Klettern, Wandern, Restaurants,
     Bars") blieb es leer: `mock_data.py::BEISPIEL_POIS` nutzt als
     `kategorie` bewusst grobe deutsche Bucket-Namen ("kultur", "natur",
     "kulinarik" — siehe `test_aufbereitung.py:54`, das genau dieses Format
     testet), während die Alias-Auflösung (`alias_place_types_fuer`) echte,
     englische Google-Place-Types wie "restaurant" erwartet (so wie sie
     `GoogleMapsClient` bei ECHTEN Daten liefert). "Restaurants"/"Bars"
     treffen daher weder den Bucket-Namen noch den Alias-Wert. Zusätzlich
     können "Klettern"/"Wandern" in `main.py` grundsätzlich NIE erscheinen,
     obwohl passende Mock-POIs existieren (`BEISPIEL_SPEZIAL_POIS`,
     Klettergarten/Wanderweg): die entscheiden nur über die Overpass-
     Zusatzquelle, deren Aktivierung (`spezialrecherche_aktivitaeten`) laut
     Design ausschließlich das LLM trifft — der `RegelbasierterInterpreter`
     liefert dafür laut eigenem Docstring immer einen leeren Wert. *Fix:*
     Testfall auf die vom Mock-Modus tatsächlich verstandenen Begriffe
     ("Kultur, Natur, Kulinarik") umgestellt, damit `main.py` sein Programm
     zeigt; Klettern/Wandern-Vorschläge sind bewusst nur über den echten
     `chat.py`-Pfad (LLM + Overpass) sichtbar, nicht als Fehler zu werten.
  *Warum nicht stattdessen `mock_data.py`-Kategorien auf echte Place-Types
  umbenannt:* mehrere bestehende Tests (`test_aufbereitung.py`,
  `test_monte_carlo.py`, `test_toptw.py`) prüfen exakt die Bucket-Namen
  "kultur"/"natur"/"kulinarik" — eine Umbenennung hätte diese Tests
  gebrochen und wäre eine größere, hier nicht angefragte Änderung gewesen.

## Phase 9 — main.py von Mock-Modus auf echten, skriptgesteuerten Ablauf umgestellt (10.08.)

- **Kehrt die main.py-Hälfte von Phase 6 ("main.py bleibt bewusst Mock-only")
  bewusst um** — explizite, spätere Anforderung desselben Tages: keine
  Mockups mehr im Programm. `main.py` erzeugte bisher IMMER einen
  `MockGoogleMapsClient` mit erfundenen Beispiel-POIs, unabhängig von der
  `.env` (Phase 6/8), und interpretierte Testfall-Antworten über den
  einfachen `RegelbasierterInterpreter` (Komma-Split, kein LLM). Die
  pytest-Suite (`tests/test_*.py`) bleibt bewusst weiter gemockt — schnell,
  kostenlos, deterministisch, ohne Internet/Key lauffähig, das ist normale
  Unit-Test-Praxis und wurde vom Product Owner explizit so bestätigt (siehe
  CLAUDE.md: "Entwicklung immer mit Mock-Modus", gilt weiterhin für die
  automatisierten Tests). Nur main.py als Demo-/Testfall-Runner soll jetzt
  realistische Ergebnisse liefern statt eines schnellen Offline-Smoke-Tests.

- **Fix:** `main.py` dupliziert die Dialoglogik nicht mehr eigenständig,
  sondern ruft `chat.py::hauptablauf()` (jetzt parametrisiert mit
  `io_kanal`/`protokoll_praefix`/`ausgabe_basisname`) mit einem neuen
  `SkriptKanal` (`src/audio/kanal.py`) auf. Der Ablauf ist dadurch
  IDENTISCH zu einer echten `chat.py`-Sitzung — echtes LLM
  (`ClaudeAntwortInterpreter`), echte `erzeuge_client()`/
  `erzeuge_flug_client()`/`erzeuge_hotel_client()` gemäß `.env` — nur die
  Herkunft der Nutzerantworten unterscheidet sich: `SkriptKanal` gibt eine
  vorbereitete Liste (`testfaelle/*.json`, Feld `antworten`) nacheinander
  aus statt auf Tastatureingabe zu warten. *Warum Wiederverwendung statt
  eigenem Ablauf:* keine zweite, potenziell abweichende Implementierung der
  b2..b6-Gateways pflegen (dieselbe Begründung wie bei
  `alias_place_types_fuer` in Phase 2).

- **Testfall-Format geändert**: von einem starren Feld->Text-Mapping
  (`{"reisezeitraum_rohtext": "..."}`, exakt 1 Antwort pro Katalogfrage) zu
  einer geordneten Liste von Antworten, die einfach der Reihe nach
  "eingetippt" werden. *Warum nötig:* der echte, LLM-geführte Dialog stellt
  je nach Formulierung Rückfragen, überspringt kontextabhängig einzelne
  Fragen (z.B. F11 Sicherheit bei einem unbedenklichen Ziel) und braucht bei
  Typ-C-Fragen zusätzliche Zustimmungsrunden — ein starres 1:1-Mapping pro
  Feld passt nicht mehr. *Bewusster Kompromiss:* die Zuordnung
  Antwort-zu-Frage ist dadurch nicht mehr exakt garantiert (bei
  übersprungenen Fragen verschiebt sich die Liste); Testfälle sollten daher
  großzügig formulierte, in sich verständliche Antworten statt knapper
  Stichworte enthalten. Läuft das Skript vorzeitig aus, bricht `SkriptKanal`
  mit einer klaren Fehlermeldung ab (`SkriptEndeFehler`) statt endlos auf
  Eingabe zu warten.

## Phase 10 — Architekturwechsel: LLM-autonome Dialogsteuerung (11.08.)

- **Was:** Die feste Python-Zustandsmaschine (`zustandsmaschine.py::Dialogschleife`, ging
  `FRAGEKATALOG` strikt der Reihe nach durch, rief das LLM pro Schritt mit erzwungenem
  JSON-Schema für GENAU einen Zweck auf) wurde vollständig ENTFERNT und durch eine einzige,
  durchgehende Agenten-Session ersetzt: das LLM bekommt den kompletten Fragekatalog + fünf
  Werkzeuge (`speichere_feld`, `hole_api_daten`, `fehlende_pflichtfelder`,
  `plane_reise_und_abschliessen`, `breche_planung_ab` — neues Modul
  `src/fragekatalog/agent_tools.py`, In-Process-SDK-MCP-Tools über `claude_agent_sdk.tool`/
  `create_sdk_mcp_server`) und entscheidet SELBST, welche Frage wann gestellt/übersprungen wird.
  `chat.py` wurde komplett neu geschrieben (einzelne Query-Response-Schleife statt b2..b6-
  Funktionen); `src/fragekatalog/zustandsmaschine.py` und `src/fragekatalog/llm_interpreter.py`
  wurden gelöscht (ihre Fachlogik — API-Aufrufe, Optimierung, All-Inclusive-/Aktivitäten-
  Sonderfälle — lebt unverändert in `vorschlaege.py`/`pipeline.py`/`reiseplan.py` weiter, nur die
  ORCHESTRIERUNG wurde ersetzt). `main.py` musste NICHT angepasst werden — es ruft bereits seit
  Phase 9 nur noch `chat.py::hauptablauf(io_kanal, ...)` auf, dessen Signatur unverändert blieb.
  CLAUDE.md wurde an den betroffenen Stellen (Grundprinzip 1/3, neuer Abschnitt
  "Dialogsteuerung", Fragekatalog-Abschnitt) mit-aktualisiert.

  Der `RegelbasierterInterpreter` (Mock-Interpreter für Tests ohne LLM) entfällt ebenfalls
  ersatzlos — Skip-/Ablaufentscheidungen sind jetzt inhärent LLM-Aufgabe, ein deterministischer
  Mock dafür ergibt architektonisch keinen Sinn mehr. Deterministisch bleibt NUR, was sich
  objektiv prüfen lässt: `speichere_feld`s Typvalidierung, `fehlende_pflichtfelder()`,
  `plane_reise_und_abschliessen()`s harte Sperre — dafür neue Datei `tests/test_agent_tools.py`
  (17 Tests, ruft die rohen `SdkMcpTool.handler`-Coroutinen direkt auf, kein SDK-Server nötig).
  `tests/test_fragekatalog.py` wurde auf die von der Ablaufsteuerung unabhängigen Tests gekürzt
  (Katalog/Schema-Konsistenz, `sicherheit_ist_wichtig`/`barrierefreiheit_wichtig`).

- **Warum:** Nutzerwunsch: "Ich gebe meinem Chatbot all die Tools, all die Fragen, all den
  Regelkatalog und lasse mit diesen Informationen dann den User einfach nur mit dem Chatbot
  kommunizieren, ohne irgendeine Zwischeninstanz über meinen Code" — bei Unsicherheit soll immer
  gefragt werden, bei sicherem Ausschluss (Kontext/Planungsentscheidung) nicht mehr. Dem Nutzer
  wurde vor der Umsetzung explizit erklärt, dass das den bisherigen, in CLAUDE.md als "nicht
  verhandelbar" markierten Grundprinzipien 1+3 sowie der bisherigen kostenlosen, deterministischen
  End-zu-Ende-Testbarkeit widerspricht (Alternative "nur die bestehende Skip-Logik generalisieren,
  Kontrollfluss bleibt regelbasiert" wurde als Empfehlung angeboten) — der Nutzer hat sich nach
  dieser Aufklärung bewusst FÜR den vollständigen Umbau entschieden. Ausdrücklich akzeptierter
  Kompromiss: Gesprächsverhalten (was das Modell fragt/überspringt) ist nicht mehr per pytest
  automatisiert testbar, nur die reinen Werkzeug-/Validierungsfunktionen bleiben es; main.py-
  Testfälle (`testfaelle/*.json`) laufen jetzt zwangsläufig gegen die echte, kostenpflichtige
  LLM-Session statt kostenlos im Mock-Modus.

- **Live verifiziert** (kein Unit-Test kann eine echte Agenten-Session ersetzen): zwei volle
  End-zu-Ende-Läufe über `python main.py` (echtes LLM, echte Google-Maps-API, ~25–30
  Gesprächsrunden) zeigten korrektes Verhalten über viele Dimensionen — echte Tool-Aufrufe mit
  echten Daten (Bahn/Auto/Fernbus-Preise, echte Hotels, echte POI-Suche inkl. Overpass-
  Spezialrecherche für Klettern), korrekte Ablehnung generischer Stadt-Sehenswürdigkeiten als
  Klettern/Wandern-Treffer (dieselbe Sorgfalt wie der Gym-Fix aus Phase 8-Umfeld, jetzt vom LLM
  selbst angewendet statt nur vom Code erzwungen), korrektes Nachhaken bei zu vielen Treffern statt
  stillschweigend zu kappen, und – besonders wichtig – die am Vortag gebaute F14-Fahrzeugwechsel-
  Nachfrage (siehe Phase 7) feuerte korrekt durch die neue Architektur. Ein gezielter dritter,
  kurzer Testlauf (eigenes Skript, NICHT die volle Konversation) hat zusätzlich
  `plane_reise_und_abschliessen` bestätigt: echte Optimierung 1+2 + Monte-Carlo-Härtetest liefen
  durch, Reiseplan wurde als Datei gespeichert, fehlender Mailjet-Key wurde ehrlich als Fehlschlag
  gemeldet statt verschwiegen. Kein einziger `speichere_feld`-Aufruf über beide vollen Läufe hatte
  einen Typvalidierungsfehler – Claude liefert Tool-Argumente zuverlässig korrekt typisiert.

  Nebenbefund (kein Bug der neuen Architektur, vorbestehend in `vorschlaege.py::
  hole_echte_daten_fuer_vorschlag`): die Warnhinweis-Formulierung bei zu vielen Rohtreffern zeigt
  "Vorschau, {ziel_max} von {len(alle_pois)}" auch wenn `ziel_max` (bis zu 30 bei einer 10-Tage-
  Reise) GRÖSSER ist als die tatsächliche Trefferzahl (z.B. "30 von 15") — verwirrender Text, aber
  keine Datenauswirkung (die tatsächliche Kappung passiert unverändert korrekt in
  `waehle_top_pois`). Siehe Offene Punkte.

## Phase 11 — Nachbesserungen nach erstem Live-Test der neuen Architektur (11.08.)

Ausgelöst durch einen echten `chat.py`/`main.py`-Testlauf des Nutzers (hypothetische Reise nach
Innsbruck) direkt nach Phase 10 – deckte zwei funktionale Bugs UND einen breiten Verständnis-
Bedarf auf. Auf ausdrücklichen Wunsch ("führe alle Punkte um, priorisiere sie, setze sie alle
um") an einem Stück umgesetzt, hier zusammengefasst:

- **BEHOBENER BUG: Restaurants/Cafés wurden nie gesucht, obwohl genannt.** `vorschlaege.py::
  hole_echte_daten_fuer_vorschlag`s `aktivitaeten_interessen`-Zweig las `anfrage.
  aktivitaeten_interessen` – das ist beim ERSTEN Durchlauf durch eine Typ-C-Frage aber noch LEER
  (wird erst NACH Zustimmung über `speichere_feld` gesetzt), wodurch die POI-Suche faktisch mit
  einer leeren Kategorienliste lief und auf den generischen Fallback "tourist_attraction" zurück-
  fiel (nur Museen/Sehenswürdigkeiten, nie Restaurants/Cafés/Bars). *Fix:* neuer Parameter
  `aktivitaeten_aktuell` sowohl in `hole_echte_daten_fuer_vorschlag` als auch im Tool
  `hole_api_daten` (agent_tools.py) – das LLM übergibt jetzt explizit die VOLLSTÄNDIGE, noch
  unbestätigte Interessenliste. System-Prompt (regelwerk.py) weist das LLM zusätzlich an, dabei
  wirklich ALLE genannten Interessen mitzugeben, nicht nur die mit Vertiefungsbedarf.
- **BEHOBENER BUG: ein im Dialog bestätigtes Verkehrsmittel wurde von Optimierung 2 überstimmt.**
  `pipeline.py::plane_reise` bewertete IMMER alle echten Alternativen (Bahn/Auto/Fernbus) nach
  Zeit/Kosten/CO2 und nahm die objektiv beste – das ignorierte eine bereits im Dialog getroffene,
  konkrete Entscheidung des Nutzers vollständig (CO2-Gewichtung/Bahn-Nudging aus Grundprinzip 5
  begünstigt strukturell die Bahn). *Fix:* neue Funktion `_nur_bestaetigte_verkehrsmittel` –
  Optimierung 2 bewertet weiterhin gewichtet, aber NUR NOCH innerhalb der vom Nutzer bestätigten
  Auswahl (Fallback auf alle Alternativen nur bei unklarem Freitext, kein Absturz).
- **Code-Review/Aufräumen** (siehe Nutzerwunsch: "Code reviewed, alles rausgeschmissen, was aus
  der alten Architektur unnötig ist"): `schema.py::FrageZustand` (verwaist seit Phase 10) und
  `Protokollierer.llm_aufruf` (nirgends mehr aufgerufen) entfernt; `regelwerk.py::
  baue_regelwerk_text`s `tool_modus=False`-Zweig (kompletter alter Gateway-Text) war seit Phase 10
  toter Code (einziger Aufrufer nutzt immer `tool_modus=True`) – Parameter entfernt, Funktion
  entsprechend vereinfacht. Diverse Docstrings/Kommentare in katalog.py, schema.py, vorschlaege.py,
  poi_sammlung.py, overpass.py, google_speech.py, protokoll.py verwiesen noch auf die gelöschten
  Module `zustandsmaschine.py`/`llm_interpreter.py` – korrigiert. Dabei ZWEI weitere echte
  Funktionslücken gefunden (nicht nur Kosmetik): `aktivitaeten_mit_spezialrecherche` (Overpass-
  Flag) und `aktivitaeten_gewichtung` (vergleichende Präferenz) wurden von `speichere_feld` bisher
  NIRGENDS auf `ReiseAnfrage` persistiert – die Chat-Vorschau nutzte sie korrekt (direktes
  Tool-Argument), aber die SPÄTERE finale Planung (`pipeline.py`) hätte sie nie gesehen. Beide
  Werte sind jetzt zusätzliche optionale Argumente von `speichere_feld`.
- **Architektur-Schema als Artifact veröffentlicht** (siehe Nutzerwunsch: "ein Schema, sodass ich
  erkenne, was mit dem Code läuft") – Diagramm des Anfrage-Flusses durch die vier Schichten
  (Dialog/Werkzeuge/API/Planung) plus Tabelle der fünf Werkzeuge, siehe verlinktes Artifact in der
  Projektkonversation vom 11.08.
- **Neu: F20 `tagesstart_praeferenz`** (Ergänzung, nicht aus dem Rohmaterial, analog zu F08/F10) –
  grobe Start-/Enduhrzeit für einen normalen Reisetag. Zwei Auswirkungen:
  1. `aufbereitung.py::wende_tageszeitfenster_an` hebt `POI.opening` je nach Place Type auf eine
     kategoriebezogene Mindest-Tageszeit relativ zum jeweiligen Tagesbeginn an (siehe
     google_maps.py `_MINDEST_TAGESZEIT_MINUTEN_JE_TYP`, z.B. Bar erst ab 8h in den Tag hinein) –
     behebt "ich soll nicht direkt nach dem Aufstehen in die Bar gehen", OHNE eine absolute
     Uhrzeit zu kennen (Grundprinzip 1: reine, dokumentierte Modellannahme wie schon
     `_BESUCHSDAUER_JE_TYP_MINUTEN`, keine erfundene Tatsache über einen konkreten Ort).
  2. `reiseplan.py` zeigt AB TAG 2 echte Uhrzeiten (`tagesstart_minuten + relative Zeit`) statt
     "nach Xmin", NUR wenn der Nutzer F20 tatsächlich beantwortet hat (sonst bliebe die reine
     09:00-Standardannahme fälschlich als scheinbar reale Uhrzeit stehen). Tag 1 bleibt IMMER
     relativ – die tatsächliche Ankunftsuhrzeit der Hinreise steht nirgends real fest (kein echtes
     Ticket vorhanden). Live per Mock-Smoke-Test verifiziert: Tag 1 relativ, Tag 2/3 mit
     "09:04 Uhr" usw., inkl. Hinweistext, der den Unterschied erklärt.
- **Neu: POI-Übersichts-Export als CSV** (siehe Nutzerwunsch: "ich brauch ein Dokument, wo mir
  alle POIs aufgezeigt werden, sodass ich sagen kann, dass dieser Optimierungsalgorithmus
  funktioniert") – `reiseplan.py::speichere_poi_uebersicht` schreibt eine Zeile pro POI-Kandidat
  (nicht nur die eingeplanten): Score, Zeitfenster, Besuchsdauer, Quelle, UND ob/wann eingeplant.
  Semikolon-getrennt mit UTF-8-BOM (deutsches Excel). Wird automatisch bei jedem erfolgreichen
  `plane_reise_und_abschliessen` mitgeschrieben (`{ausgabe_basisname}_pois.csv`, neben Text/JSON).

## Phase 12 — Aufräumen Projekt-Wurzelverzeichnis + README (11.08.)

- **Was:** Generierte Reiseplan-Ausgaben (Text/JSON/POI-CSV) landen jetzt gesammelt in `ergebnisse/`
  statt einzeln lose im Projekt-Wurzelverzeichnis (`src/fragekatalog/agent_tools.py`,
  `_ERGEBNISSE_VERZEICHNIS`) – main.py/chat.py geben weiterhin nur einen Basisnamen vor (z.B.
  `reiseplan_chat`), der Zielordner ist jetzt zentral an einer Stelle festgelegt. Bestehende, teils
  verwaiste Dateien (u.a. `reiseplan_allergie_barrierefrei.*` – der zugehörige Testfall existiert
  längst nicht mehr) dorthin verschoben statt gelöscht. `.gitignore` entsprechend auf `ergebnisse/`
  vereinfacht (vorher mehrere `reiseplan_*`-Einzelmuster). Neues `README.md` im Projektordner
  erklärt kurz, was jedes Top-Level-Verzeichnis/jede Datei ist und wie man startet.
- **Warum:** Nutzerwunsch: "Wozu ist das alles? Das sieht nicht nötig aus" (Frage zu den lose im
  Root liegenden `reiseplan_*`-Dateien) + "strukturier den Code einmal komplett vernünftig,
  sodass er gut nachvollziehbar ist". `src/` selbst blieb unverändert (bereits durch die vier
  Schichten aus Phase 10/dem Architektur-Artifact klar gegliedert) – der eigentliche Störfaktor
  waren generierte Laufzeit-Ausgaben, die im selben Verzeichnis wie der Quellcode lagen.

## Phase 13 — Echte Bahn-Umstiegsdaten statt nur Gesamtdauer (12.08.2026)

- **Was:** `google_maps.py::_hole_route` las bisher nur `legs[0]` (Gesamtdauer/-distanz) einer
  Google-Directions-Antwort, `legs[0].steps` (Linie, Umstiegshaltestellen, Zeitstempel je
  Teilstrecke) wurde komplett verworfen. Neuer Typ `Teilstrecke` (`typen.py`), neue Funktion
  `_teilstrecken_aus_steps` (`google_maps.py`) wertet die `steps` jetzt aus; Wartezeit beim
  Umstieg wird aus der Zeitlücke zwischen Ankunfts- und Abfahrtszeitstempel zweier
  aufeinanderfolgender TRANSIT-Schritte berechnet, nur wenn Google beide liefert (sonst `None`
  statt geraten, Grundprinzip 1). `reiseplan.py` (Text + HTML-Mail) zeigt die Umstiegskette jetzt
  zusätzlich zur Gesamtdauer an. *Bug während der Umsetzung gefunden:* bei `mode=driving` liefert
  Google ebenfalls `steps`, aber Abbiege-Kleinschritte statt Umstiege — ungefiltert hätte das zu
  über 20 sinnlosen "Fußweg"-Zeilen bei einer Autofahrt geführt (live gegen die echte API
  verifiziert). *Fix:* Teilstrecken werden nur noch für `mode=transit` (Bahn/Fernbus) gebaut.
- **Warum:** Nutzerwunsch: "nicht nur sagen 'mit Bahn brauchst du eine Stunde', sondern 30 min
  dahin, dann umsteigen mit 5 min Wartezeit, dann 25 min Fahrzeit" — die reine Gesamtdauer war für
  eine echte Bewertbarkeit der Bahnverbindung zu grob.
- Live gegen die echte Google-Directions-API verifiziert (Berlin Hauptbahnhof → München
  Hauptbahnhof: korrekte ICE-Verbindung; eine simulierte Fernbus-Route mit drei echten Umstiegen
  zeigte plausible Wartezeiten). 4 neue Tests, komplette Suite danach 186/186 grün. Details:
  [`doku/05_stage5_bahn_teilstrecken/`](doku/05_stage5_bahn_teilstrecken/README.md) (inkl.
  Code-Duplikat des Standes zu diesem Zeitpunkt).

## Phase 14 — `doku/`-Ordner: Entwicklungsstationen rückwirkend aufbereitet (12.08.2026)

- **Was:** Neuer Ordner `doku/` mit einem Unterordner je Entwicklungsstation (Stage 1–5),
  rückwirkend aus diesem Log sowie dem Gesprächsverlauf aufbereitet. Jede Station beschreibt
  Was/Warum/verworfene Alternativen in eigenen Worten (nicht nur ein Log-Auszug); wo der
  betreffende Code noch existiert (Stationen 2 und 5), liegt zusätzlich ein echtes 1:1-Duplikat
  der Dateien zu diesem Zeitpunkt bei (`code_stand/`). Für Station 1 (regelbasierte
  Dialogsteuerung, Code seit Phase 10 gelöscht) gibt es bewusst NUR eine Textbeschreibung, keine
  Code-Rekonstruktion aus dem Gedächtnis — um nichts als "Original" auszugeben, was tatsächlich
  keins mehr ist.
- **Warum:** Nutzerwunsch, den Entwicklungsprozess separat von diesem (chronologisch
  durchlaufenden) Log so aufzubereiten, dass sich einzelne Architektur-Stationen gezielt
  nachschlagen lassen ("so hab ich angefangen, so hat sich die Architektur geändert") — Grundlage
  für die Design-Science-Research-Darstellung in der Masterarbeit. Explizit rückwirkend für den
  gesamten bisherigen Verlauf angefordert, nicht nur ab jetzt.
- **Kein Git in diesem Projekt** (ausdrückliche Nutzerentscheidung bei Rückfrage: Ordner-Duplikate
  statt Versionskontrolle). Deshalb neue Konvention ab sofort: vor jeder künftigen
  nicht-trivialen Architektur-/Infrastruktur-Änderung werden die betroffenen Dateien zuerst 1:1 in
  einen neuen `doku/`-Unterordner kopiert, bevor der Code geändert wird — sonst wäre "vorher" ohne
  Git nach der Änderung nicht mehr rekonstruierbar.
- **Zusätzliche, ab jetzt geltende Konvention:** bei künftigen vom Nutzer angestoßenen
  Architektur-/Infrastruktur-Änderungen wird zuerst nach dem **Warum** gefragt (statt es im
  Nachhinein aus dem Kontext zu erschließen), damit die Begründung direkt und ohne Verlust in
  dieses Log bzw. `doku/` einfließt.

## Phase 15 — POI-Suche: Freitext statt fester Google-Place-Type-Zuordnung (12.08.2026)

- **Was:** `google_maps.py::suche_pois` presste Nutzerinteressen bisher über eine fest gepflegte
  Schlüsselwort-Tabelle (`_KATEGORIE_ALIASE`, ENTFERNT) auf einen von Googles ~100 FESTEN Place
  Types (Nearby Search verlangt zwingend einen solchen Typ) – z.B. "Klettern" -> "gym", weil Google
  keinen eigenen Kletter-Typ kennt. Ersetzt durch Google Places **Text Search**: für JEDES genannte
  Interesse EIN Aufruf mit dem Interesse WÖRTLICH als `query` (z.B. "Klettern in Innsbruck"), kein
  fester Typ mehr nötig. Jeder Treffer trägt in `POI.nutzerinteresse` (neues Feld, `typen.py`)
  GENAU das Interesse, für das er gefunden wurde. `aufbereitung.py::berechne_poi_score` matcht
  seither strukturell gegen `nutzerinteresse` statt gegen eine nachträglich geratene
  Kategorie-Zuordnung – die gesamte Alias-/Namensprüfungs-Logik (`_KATEGORIE_ALIASE`,
  `alias_place_types_fuer`, `kategorie_alias_eintraege`, `_kategorie_passt_zu_praeferenz`,
  `_UNPRAEZISE_ALIAS_SCHLUESSELWOERTER`) entfällt ersatzlos. `overpass.py` (Aktivitäten mit
  OSM-Schwierigkeitsgrad wie Klettern/Wandern/Ski) bleibt UNVERÄNDERT bei seiner festen
  Aktivitäts-Tag-Tabelle – dort ist die feste Zuordnung technisch nötig (OSM selbst taggt nur eine
  feste, uneinheitliche Menge an Schlüsseln, keine Textsuche verfügbar), setzt aber jetzt ebenfalls
  `nutzerinteresse` für konsistentes Scoring. Details/Code-Duplikat des Vorher-Stands:
  [`doku/06_stage6_freitext_poi_suche/`](doku/06_stage6_freitext_poi_suche/README.md).
- **Warum:** Nutzerwunsch, sehr pointiert: "Ich möchte klettern und nicht ins Gym. Das ist auf gar
  keinen Fall das Gleiche. [...] Die API soll dann ruhig nach Kletterrouten suchen. Das schafft die
  Google Maps API schon." Live verifiziert: Interesse "Klettern" liefert jetzt echte Kletterorte
  (KI-Kletterzentrum, Boulderanlage Amras, Höttinger Steinbruch) statt Fitnessstudios; Interessen
  ohne jede feste Kategorie-Entsprechung ("eine Runde laufen gehen", "über Brücken spazieren
  gehen") liefern erstmals überhaupt sinnvolle, thematisch passende Treffer (echte Laufwege/Brücken)
  statt vorher entweder falscher Kategorie oder dem generischen "tourist_attraction"-Fallback.
- **Nebeneffekt (Regression behoben):** `_KATEGORIE_ALIASE` deckte auch die interne Verleih-Suche
  ab ("Autoverleih"->"car_rental", "Fahrradverleih"->"bicycle_store", siehe pipeline.py
  `_VERLEIH_KATEGORIE_JE_FAHRZEUG`) – funktioniert unter Text Search unverändert (Freitext
  "Autoverleih"/"Fahrradverleih" wird direkt verstanden), `mock_data.py`s Verleih-Fixtures wurden
  entsprechend auf den neuen Freitext-Abgleich umgestellt (`kategorie` trägt jetzt den Suchbegriff
  statt eines Google-Place-Types).
- Komplette Testsuite nach dem Umbau: 178/178 grün (9 veraltete `_waehle_place_types`-/Gym-
  Namensprüfungs-Tests entfernt, 5 neue Tests für die Text-Search-Suche/das nutzerinteresse-basierte
  Scoring ergänzt). Live gegen die echte API über `pruefe_planung.py` mit gemischten Interessen
  (Klettern + Laufen + Brücken-Spaziergang) end-to-end verifiziert, inkl. Optimierung 1.

## Phase 16 — Mindestabstand zwischen Mahlzeiten in Optimierung 1 (12.08.2026)

- **Was:** Neue harte Nebenbedingung im ILS-Kern (`toptw.py::simuliere_route`): POIs bekommen über
  `POI.besuchsklasse` (neues Feld, `typen.py`) eine grobe Einordnung ("mahlzeit"/"kaffee"/"bar"), aus
  Googles eigenem zurückgelieferten Typ abgeleitet (`google_maps.py::besuchsklasse_fuer_typ`).
  `TOPTWInstanz.mindestabstand_je_klassenpaar` (Default `_STANDARD_MINDESTABSTAND_MINUTEN`) definiert
  je Klassenpaar einen Mindestabstand AM SELBEN TAG: zwei "mahlzeit"-Besuche (Restaurants) brauchen
  4h Abstand, "kaffee"+"bar" 1h; alle anderen Kombinationen (insbesondere Restaurant+Kaffee) sind
  UNEINGESCHRÄNKT. Da `plane_gesamte_reise` bereits verplante POIs tageweise aus dem Pool entfernt,
  verteilen sich mehrere gewünschte Restaurantbesuche dadurch automatisch auf mehrere Tage, OHNE dass
  irgendjemand (KI oder Code) explizit einen Tag zuweisen muss. Café bekommt zusätzlich einen
  moderaten Tageszeit-Mindestwert (2h nach Tagesbeginn statt sofort, siehe `_MINDEST_TAGESZEIT_
  MINUTEN_JE_TYP`).
- **Dabei gefundener, vorbestehender Bug** (nicht neu durch diese Änderung, nur durch sie erstmals
  bemerkt): `haupttyp = types[0]` (seit Phase 2/Station 6) nahm blind den ERSTEN Eintrag aus Googles
  `types`-Array – Google sortiert dieses Array aber NICHT nach Spezifität, ein generischer
  Sammeltyp wie "establishment" steht oft VOR dem eigentlich interessanten ("restaurant"). Live
  verifiziert: eine Restaurant-Text-Search lieferte durchgehend `types=['establishment', 'food',
  'point_of_interest', 'restaurant', ...]` – `haupttyp` war dadurch praktisch NIE "restaurant"/
  "cafe"/"bar", wodurch Besuchsdauer-Schätzung, Tageszeit-Mindestwert UND die neue Besuchsklasse ins
  Leere liefen. *Fix:* neue Funktion `_waehle_haupttyp` wählt den ersten Eintrag, der tatsächlich in
  einer unserer eigenen Typ-Tabellen vorkommt, statt blind `types[0]`.
- **Warum:** Nutzerwunsch nach dem POI-Fix (Station 6): "ich möchte nicht um 13:13 essen und um
  14:07 schon wieder in einem Restaurant sitzen [...] dass man eher mittags oder abends essen geht
  und nicht abends nochmal Kaffee trinken, wenn man gerade gegessen hat." Ausdrücklich verworfene
  Alternative: die KI vergibt selbst Tages-Indizes je Restaurant (Rückfrage, siehe Gesprächsverlauf)
  – abgelehnt, weil die KI zum Zeitpunkt der Dialogantwort weder Geografie noch Reisezeiten noch die
  tatsächliche Tagesroute kennt und das daher nicht zuverlässig entscheiden könnte (Grundprinzip
  1/3: die eigentliche Planungsentscheidung bleibt beim deterministischen Optimierer). Konkrete
  Abstandsregeln (Kaffee direkt nach Restaurant ausdrücklich erlaubt, Kaffee/Bar mit Abstand
  zueinander, Restaurant/Restaurant mit 4h) nach Rückfrage vom Nutzer bestätigt.
  Mehrere-Unterkünfte-je-Rundreise-Etappe (verwandter Wunsch, "morgens Checkout, abends Check-in ins
  nächste Hotel") wurde nach Rückfrage bewusst NICHT mit umgesetzt – eigenständige, größere
  Erweiterung (mehrere Depots/Zielorte je Reise), aktuell nicht Teil des Modells.
- Live gegen die echte API verifiziert (3-Tage-Innsbruck-Testfall mit Restaurants+Cafés+Bars+
  Klettern): vorher 3 Restaurants direkt hintereinander an einem Tag, nach dem Fix verteilt auf
  unterschiedliche Tage mit sinnvollem Abstand zu Café-Besuchen. 5 neue Tests (`test_toptw.py`),
  komplette Suite: 183/183 grün. Details/Code-Duplikat des Vorher-Stands:
  [`doku/07_stage7_mahlzeiten_mindestabstand/`](doku/07_stage7_mahlzeiten_mindestabstand/README.md).

## Phase 17 — Fahrzeit zwischen POIs in der Tagesansicht (12.08.2026)

- **Was:** `reiseplan.py` (Text + HTML) zeigt vor jedem Besuch jetzt eine eigene Zeile "→ X Min.
  von <vorheriger Ort/Unterkunft>". Neue Funktion `_fahrzeit_vor_besuch` – reine Anzeige, KEINE
  neue Berechnung: die Fahrzeit steckt bereits exakt in der Differenz zwischen der Ankunftszeit
  eines Besuchs und der Abfahrtszeit des vorherigen (bzw. für den ersten Besuch direkt in dessen
  Ankunftszeit, da der Tag bei `uhrzeit=0` beginnt, siehe `toptw.py::simuliere_route`). Keine
  Änderung an Optimierung 1 selbst.
- **Warum:** Nutzerwunsch: "wär's noch gut, wenn ich in diesen Tagesansichten die Routenlänge
  zwischen den einzelnen POIs kennen würde – wie lange brauch ich von dem dahin?"
- Live gegen die echte API verifiziert. 2 neue Tests (`test_reiseplan.py`), komplette Suite:
  185/185 grün. Keine eigene `doku/`-Station (reine additive Anzeige-Erweiterung, kein Architektur-
  /Infrastruktur-Eingriff).

## Phase 18 — Ernährungspräferenz in der Restaurant-Suche + eingeschränkte Gehfähigkeit (12.08.2026)

- **Was (Ernährung):** `google_maps.py::suche_pois` bekommt einen neuen Parameter
  `ernaehrung_einschraenkungen`. Erkennt ein Interesse selbst als essen-bezogen (neue Funktion
  `_ist_essen_bezogenes_interesse`, Schlüsselwörter "restaurant"/"essen"/"kulinarik"/...), wird die
  genannte Ernährungspräferenz (z.B. "vegetarisch") VOR den Interesse-Text in die Places-Text-
  Search-Query gesetzt ("vegetarisch Restaurants in Innsbruck" statt nur "Restaurants in
  Innsbruck") – nutzt Googles eigene Suchrelevanz, erfindet nichts selbst. Durchgereicht von
  `sammle_pois` (neuer Parameter) bis zu den beiden Aufrufern (`pipeline.py`, `vorschlaege.py`).
  Ersetzt NICHT die bestehende harte Nachprüfung in `vertraeglichkeit.py` (Namens-Ausschluss bei
  Allergien bleibt als Sicherheitsnetz bestehen).
- **Warum (Ernährung):** Nutzerwunsch: "wenn eine Ernährungspräferenz geäußert wird, müssen die
  ausgewählten Restaurants den Ausprägungen angepasst werden." Live verifiziert (vegetarisch,
  Innsbruck): u.a. "One green table" unter den Top-Treffern.

- **Was (Gehfähigkeit):** Neue Methode `ReiseAnfrage.eingeschraenkte_gehfaehigkeit()` (schema.py,
  eigenständig neben `barrierefreiheit_wichtig()` – andere Konsequenz: keine Orts-/Unterkunfts-
  Filterung, sondern Anpassung der Planung selbst). Bei Zutreffen drei Anpassungen in
  `aufbereitung.py::erstelle_toptw_instanz`:
  1. Geschwindigkeit auf `_GESCHWINDIGKEIT_EINGESCHRAENKT_KMH` (2.0 km/h statt 4.5) gesenkt – NUR
     wenn ohnehin zu Fuß unterwegs (ein bestätigtes Auto/ÖPNV-Tempo bleibt unverändert).
  2. Neues `TOPTWInstanz.pause_intervall_minuten`/`pause_dauer_minuten` (toptw.py
     `simuliere_route`): nach 120 Minuten kumulierter Fahr-/Aktivitätszeit wird vor dem nächsten
     Besuch automatisch eine 20-Minuten-Pause eingeplant (als zusätzliche Wartezeit, keine eigene
     Pseudo-Station). In der Ausgabe (reiseplan.py) jetzt sichtbar als "davon X Min.
     Pause/Wartezeit" bei jedem betroffenen Besuch.
  3. Neue Funktion `gewichte_nach_naehe_zum_depot` (aufbereitung.py): erhöht relativ den Score
     näher an der Unterkunft gelegener POIs (glatt abfallender Faktor, Referenzdistanz 1.5 km),
     angewendet VOR dem Zeitfenster-Schritt.
- **Warum (Gehfähigkeit):** Nutzerwunsch: "wenn ich angebe, dass ich Schwierigkeiten habe zu
  gehen, dann müssen die Gehzeiten neu berechnet werden, Pausen eingeplant werden, dazu sollten
  POIs die nah am Hotel liegen höher gewichtet werden." Alle drei Werte (2.0 km/h, 120min/20min,
  1.5 km) sind dokumentierte, literaturunabhängige Modellannahmen (wie die bereits bestehenden
  Besuchsdauer-/Tageszeit-Konstanten), keine erfundenen Fakten über eine konkrete Person.
- Live verifiziert (Innsbruck, Museen+Restaurants, "Schwierigkeiten zu gehen" + zu Fuß): Scores
  nicht mehr einheitlich 3.0 (Nähe-Gewichtung sichtbar wirksam, z.B. 2.7/2.3/2.0), eine Pause von
  20 Minuten korrekt vor dem dritten Museumsbesuch eingeplant (sichtbar an "bis"-Zeit +
  Pause-Hinweis in der Ausgabe). Details/Code-Duplikat:
  [`doku/08_stage8_ernaehrung_und_gehfaehigkeit/`](doku/08_stage8_ernaehrung_und_gehfaehigkeit/README.md).
- 13 neue Tests (`test_google_maps.py`, `test_aufbereitung.py`, `test_toptw.py`). Komplette Suite
  danach: 200/200 grün.

## Phase 19 — Echte Google-Distance-Matrix statt Luftlinie in Optimierung 1 (12.08.2026)

- **Was:** UMSETZUNG von CLAUDE.md, Abschnitt "Optimierung 1", "Zentrale Anpassung":
  "Distanzberechnung aus Koordinaten durch echte Reisezeiten aus der Google Distance Matrix
  ersetzen" – bisher nie umgesetzt, obwohl `MapsClient.distanzmatrix` bereits seit Längerem
  vollständig implementiert war, nur nie mit Optimierung 1 verdrahtet. Neue Funktion
  `aufbereitung.py::hole_reisezeitmatrix` ruft EINMAL pro Depot-Kandidat die echte Distance Matrix
  für Depot+alle POIs ab und baut ein `(id_a, id_b) -> Minuten`-Lookup; `TOPTWInstanz.
  reisezeiten_minuten` (neues Feld, toptw.py) und `reisezeit_minuten()` bevorzugen diese echten
  Werte, fallen NUR bei fehlendem Einzelpaar (keine Route gefunden) auf die bisherige
  Luftlinien-Schätzung zurück – kein Absturz, keine erfundene Zeit. `erstelle_toptw_instanz`
  bekommt dafür einen neuen optionalen `client`-Parameter (ohne Angabe: unverändertes
  Luftlinien-Verhalten, ältere Aufrufer/Tests unberührt); `pipeline.py` reicht den echten
  `MapsClient` jetzt durch.
- **Modus-Erkennung konsolidiert:** `aufbereitung.py::_TRANSPORT_PARAMETER` bekommt einen dritten
  Tabellenwert (Google-`mode`-String), neue Funktion `modus_fuer_lokalen_transport` – dieselbe
  Schlüsselwort-Erkennung wie `parameter_fuer_lokalen_transport` (F14), keine zweite, potenziell
  abweichende Zuordnung.
- **Dabei gefundenes, notwendiges Batching:** Ein einzelner Distance-Matrix-Aufruf mit ALLEN
  Orten gleichzeitig als Origins UND Destinations überschritt live Googles Elemente-Limit
  (`MAX_ELEMENTS_EXCEEDED`) schon bei mittelgroßen Reisen (>10 POIs). *Fix:*
  `GoogleMapsClient.distanzmatrix` teilt jetzt selbst in 10×10-Kacheln auf und setzt die
  Antworten zu einer vollständigen Matrix zusammen – für Aufrufer transparent, keine
  Schnittstellenänderung.
- **Warum:** Nutzerrückmeldung nach einem Live-Test: "die Zeiten sind falsch – 1 Min. von X, 3
  Min. von Y" für Orte, die real deutlich weiter auseinanderliegen. Ursache: die
  Luftlinien-Schätzung (Koordinatenabstand ÷ konfigurierte Geschwindigkeit) ignoriert
  Straßennetz/Umwege komplett – bei "Auto" als lokalem Fortbewegungsmittel (40 km/h) wirkten selbst
  mehrere Kilometer Luftlinie wie 1–3 Minuten Fahrzeit.
- Live verifiziert: derselbe 3-Tage-Testfall zeigt jetzt 3–9 Minuten reale Fahrzeit zwischen
  denselben Orten (statt zuvor 1–3 Minuten) – plausibel für tatsächliche Straßenrouten in
  Innsbruck. 8 neue Tests, komplette Suite: 200/200 grün.
- **Bewusst nicht umgesetzt** (siehe `hole_reisezeitmatrix`-Doku): kein Cache der POI-zu-POI-
  Distanzen über mehrere Unterkunfts-Kandidaten hinweg – bei maximal 5 Kandidaten (`_MAX_
  UNTERKUNFT_KANDIDATEN`) aktuell nicht nötig, aber ein möglicher künftiger Optimierungspunkt bei
  mehr Kandidaten oder häufigeren Aufrufen (Kosten/Latenz).

## Phase 20 — Nähe-Gewichtung greift schon vor der Kandidaten-Kappung (12.08.2026)

- **Was:** `gewichte_nach_naehe_zum_depot` (Phase 18, eingeschränkte Gehfähigkeit) lief bisher NUR
  innerhalb von `erstelle_toptw_instanz` – zu diesem Zeitpunkt hatte `waehle_top_pois`
  (`pipeline.py::plane_reise`/`vorschlaege.py::hole_echte_daten_fuer_vorschlag`) die Kandidatenliste
  aber bereits rein nach Interesse (ohne jeden Distanzbezug) auf `max_pois_fuer_reise()` gekappt –
  die spätere Nähe-Gewichtung konnte die Auswahl selbst nicht mehr beeinflussen, nur noch die
  Einfüge-Reihenfolge INNERHALB der bereits (potenziell geografisch verstreuten) Auswahl. *Fix:*
  beide Aufrufer wenden `gewichte_nach_naehe_zum_depot` jetzt zusätzlich VOR der Kappung an, mit dem
  groben Zielort (`client.geocode(ziel)`) als Näherung – der tatsächliche Unterkunfts-Standort steht
  zu diesem Zeitpunkt noch nicht fest (folgt erst in `_plane_bestes_depot`), aber Unterkünfte liegen
  typischerweise ebenfalls zentral, daher eine sinnvolle Vorab-Näherung. Die spätere, depot-genaue
  Gewichtung in `erstelle_toptw_instanz` verfeinert danach weiter.
- **Warum:** Nutzerrückmeldung: "es braucht auch die Abstände zwischen den POIs untereinander, denn
  ich will ja nicht nach jedem POI zurück ins Hotel." Klargestellt: die eigentliche Routenbildung
  (Greedy/ILS) berücksichtigt POI-zu-POI-Distanzen bereits strukturell über die echten Reisezeiten
  (Phase 19) bei der Einfüge-Kostenberechnung – die hier behobene Lücke betraf spezifisch die VOR-
  AUSWAHL der Kandidaten für Nutzer mit eingeschränkter Gehfähigkeit, nicht die Streckenführung
  selbst.
- Live erneut verifiziert (derselbe Testfall wie Phase 18): weiterhin ein kompakter, kurzer
  Streckenverlauf (1–13 Minuten zwischen aufeinanderfolgenden Orten), keine Regression. Komplette
  Suite weiterhin 200/200 grün (keine neuen Unit-Tests nötig – `gewichte_nach_naehe_zum_depot`
  selbst bereits in Phase 18 getestet, hier nur der Aufrufzeitpunkt verschoben).

## Phase 21 — Unabhängige Prüfung von Optimierung 1 gegen Google OR-Tools (12.08.2026)

- **Was:** Neuer Ordner `evaluierung/` mit `vergleiche_optimierung_mit_ortools.py`: ein kleiner,
  von Hand nachvollziehbarer Beispiel-Datensatz (6 POIs + Depot, absichtlich knappes Tagesbudget,
  sodass eine echte Auswahlentscheidung nötig ist) wird mit DREI unabhängigen Methoden gelöst –
  dem eigenen `iterated_local_search` (unverändert), Google OR-Tools (etabliertes, fremdes
  Optimierungs-Toolkit, über den Standard-"Prize-Collecting"-Trick als TOPTW modelliert) und einer
  reinen Brute-Force-Suche (alle 64 Teilmengen × Reihenfolgen, garantiertes mathematisches Optimum
  bei dieser Größe). Alle drei erhalten exakt dieselbe, einmal berechnete Reisezeit-Matrix.
- **Warum:** Nutzerwunsch: "ich möchte nicht, dass du genau deinen eigenen Code nutzt, um das zu
  prüfen, sondern vielleicht irgendein Tool, um das mit diesem Algorithmus zu prüfen" –
  `tests/test_toptw.py` prüft ausschließlich mit demselben Code, der auch die Lösung erzeugt; ein
  systematischer Fehler in der ILS-Logik selbst würde dort nicht auffallen. Rückfrage zur
  Werkzeugwahl (Google OR-Tools bestätigt, Empfehlung) und Datensatzgröße (klein/von Hand
  nachvollziehbar bestätigt) vor der Umsetzung geklärt.
- **Ergebnis:** Alle drei Methoden erreichen exakt denselben Score (31,0 von möglichen 35,0 bei
  Besuch aller 6 POIs) – Museum, Park, Restaurant, Aussichtspunkt, Kirche werden besucht, "Markt"
  (niedrigster Score) korrekt ausgelassen, weil er ins Tagesbudget nicht mehr reinpasst. Eigener
  Code und Brute-Force liefern sogar dieselbe Reihenfolge; OR-Tools findet eine andere, aber
  gleichwertige Reihenfolge. Starker Beleg für die Korrektheit der Kernlogik (Zeitfenster-Prüfung,
  Tagesbudget, Scoring/Auswahl) bei einer Instanz mit echtem Auswahl-Kompromiss (kein trivialer
  "alles passt rein"-Fall). Details, Einschränkungen dieser Prüfung und Aufruf:
  [`evaluierung/README.md`](evaluierung/README.md).
- Neue, separate Abhängigkeit `requirements-evaluierung.txt` (nur Google OR-Tools) – kein Teil des
  normalen Programmbetriebs, analog zu `requirements-audio.txt`.

## Phase 22 — Kontextbasierte statt wortbasierte Interessen-Gewichtung (12.08.2026)

- **Was (Prompt):** `aktivitaeten_gewichtung` durfte laut System-Prompt (`regelwerk.py`) und
  Werkzeug-Beschreibung (`agent_tools.py::speichere_feld`) bisher NUR gesetzt werden, wenn es wegen
  zu vieler Treffer eine explizite vergleichende Rückfrage gab ("Reizt dich X oder Y mehr?"). Jetzt:
  das bleibt ein gültiger Auslöser, aber nicht der einzige – das LLM soll die Gewichtung aus dem
  GESAMTEN bisherigen Gesprächskontext ableiten (Betonung, Wiederholung, ein genannter Grund, eine
  erkennbare Rangfolge), nicht nur aus dem wörtlichen Wort "wichtig" oder der einen Rückfrage-Situation.
  Ausdrücklich weiterhin: bei erkennbar neutralen/gleichrangigen Interessen KEIN Gewicht erfinden.
- **Warum:** Nutzerwunsch: "ich möchte nicht, dass das nur durch das Wort 'wichtig' ausgelöst wird,
  sondern dem Nutzerkontext entsprechend gewichtet werden soll."

- **Was (Scoring):** `aufbereitung.py::berechne_poi_score` von additiv (`1.0 + gewichtung*2.0`) auf
  multiplikativ (`_BASIS_SCORE * gewichtung`, `_BASIS_SCORE=3.0`) umgestellt. Bei neutralem Gewicht
  unverändert 3.0 (Rückwärtskompatibilität), aber doppeltes Gewicht verdoppelt jetzt den Score
  TATSÄCHLICH (vorher nur +67%) – setzt sich dadurch klarer sowohl bei der Kandidaten-Kappung
  (`waehle_top_pois`) als auch bei der Greedy-Einfüge-Priorität durch.
- **Warum:** Die additive Formel differenzierte zu schwach, um sich gegen zahlreiche neutral
  gewichtete Treffer durchzusetzen – die (jetzt kontextbasierte) Gewichtung hätte in der Praxis kaum
  etwas verändert.
- **Verworfene Zusatz-Idee:** zunächst zusätzlich erwogen, stark gewichtete Interessen zwangsweise
  über mehrere Tage zu verteilen (analog, aber invers, zum Mahlzeiten-Mindestabstand aus Phase 16).
  Nach Rückfrage vom Nutzer korrekt zurückgewiesen: anders als bei Mahlzeiten (echter physischer
  Grund, zwei volle Mahlzeiten in 50 Minuten ergeben keinen Sinn) gibt es bei zwei hoch gewichteten
  Aktivitäten am selben Tag (z.B. Surfen + danach ein Restaurant) keinen vergleichbaren Grund gegen
  Häufung – wenn es zeitlich/geografisch passt, ist das die korrekte Optimierung, keine künstliche
  Verteilung nötig. Nicht umgesetzt.
- 1 neuer Test (`test_berechne_poi_score_gewichtung_ist_multiplikativ`), komplette Suite: 201/201
  grün.

## Phase 23 — Fragereihenfolge: Lernaktivität/Ernährung/lokaler Kontakt vor Aktivitäten (12.08.2026)

- **Was:** `katalog.py`: F17 (`lernaktivitaeten_interesse`), F18 (`ernaehrung_einschraenkungen`),
  F19 (`lokaler_kontakt_wichtig`) stehen jetzt VOR F16 (`aktivitaeten_interessen`) in der Liste
  `FRAGEKATALOG` – alle vier bleiben in Stufe 7, nur die Reihenfolge INNERHALB der Stufe ändert
  sich. Die F-Nummern selbst bleiben unverändert (Rückführbarkeit auf das Original-
  Fragenkatalog-Dokument bleibt erhalten, siehe Moduldoku dort) – nur die Position in der Liste,
  die `regelwerk.py::_fragekatalog_uebersicht()` unverändert in Listen-Reihenfolge an das LLM
  weitergibt und an der sich das LLM beim Gesprächsablauf orientiert.
- **Warum:** Nutzerwunsch: diese drei Fragen "gehören ja schon irgendwie mit dazu" zu den
  Aktivitäten, sollen nicht als isolierte Einzelfragen irgendwo im Katalog stehen, sondern direkt
  vor der Aktivitäten-Frage. Zusätzlich ein konkreter technischer Vorteil, der die Umsetzung noch
  bekräftigt: F18 (Ernährungseinschränkungen) fließt seit Station 8 direkt in die Restaurant-Text-
  Search-Query ein (`google_maps.py::_ist_essen_bezogenes_interesse`) – war F18 bisher noch nicht
  beantwortet, wenn F16 zum ersten Mal eine Restaurant-Suche auslöste, bekam genau diese erste
  Suche keine Ernährungsanpassung (erst eine spätere Korrektur hätte sie nachgetragen).
- Klargestellt: verletzt NICHT das in CLAUDE.md/katalog.py zitierte Stufenmodell (Choi et al.
  2012/Gavalas et al. 2014) – das definiert Stufen, keine strikte Reihenfolge innerhalb einer
  Stufe. Komplette Suite weiterhin 201/201 grün (keine Tests hingen von der Listenreihenfolge ab).

## Phase 24 — main.py: zweites, bequemeres Testfall-Format unterstützt (12.08.2026)

- **Was:** `main.py::lade_testfall` erkennt jetzt automatisch, ob `antworten` im JSON eine Liste
  (Standardformat seit Phase 9) oder ein Objekt Feldname->Antwort ist. Im zweiten Fall wird
  automatisch in eine geordnete Liste umgewandelt: ein optionaler Top-Level-Schlüssel
  `reiseerlebnis_beschreibung` zuerst als a1-Freitext-Einstieg, danach die Werte in der im JSON
  geschriebenen Reihenfolge – kein echtes 1:1-Feld-zu-Frage-Mapping (der LLM-geführte Dialog fragt
  nicht zwingend in exakt dieser Reihenfolge), die Werte werden einfach der Reihe nach als
  nächste Nutzerantwort ausgegeben.
- **Warum:** Nutzer hat drei neue Testfälle (`Testfall_Annegret.json`, `Testfall_Jakob.json`,
  `Testfall_Thomas.json`) im Feldname->Antwort-Format angelegt (bequemer beim Schreiben, da
  sofort ersichtlich, welche Antwort zu welchem Feld gehört) – das seit Phase 9 aktive
  Listenformat hätte diese Dateien nicht korrekt eingelesen (`list(dict)` hätte nur die
  Feldnamen selbst als "Antworten" geliefert). Statt die drei bereits befüllten Dateien manuell
  umzuschreiben, unterstützt `lade_testfall` jetzt beide Formate.
- Die drei neuen Testfälle decken thematisch mehrere zuvor gebaute Features gezielt ab: Annegret
  (eingeschränkte Gehfähigkeit, All-Inclusive), Jakob (Klettern/Freitext-POI-Suche), Thomas
  (Familie mit Kindern, Ernährung/Kultur-Fokus). Komplette Suite weiterhin 201/201 grün.

## Phase 25 — main.py: robusteres Testfall-Format, zwei API-Robustheits-Bugs behoben (12.08.2026)

- **Was (Testfall-Format):** `main.py::lade_testfall` übergibt beim Feldname->Antwort-Format
  (siehe Phase 24) jetzt EINEN konsolidierten Block (alle Felder als "feld: wert"-Zeilen) als
  erste Nachricht statt vieler einzelner Werte in strikter Reihenfolge, dazu ein Sicherheitsnetz
  aus generischen Zustimmungen und danach den Einzelwerten. *Warum:* Nutzerrückmeldung:
  "SkriptKanal nimmt strikt die nächste Antwort aus der Liste, egal was der Bot tatsächlich
  gefragt hat – eine unerwartete Rückfrage verschiebt ab da alles"; ein einziger, umfassender
  Freitext-Block (wie beim Nutzer selbst live erprobt: "ich hab das einfach übergeben und eine
  Antwort bekommen") lässt das LLM selbstständig extrahieren, ist robuster.
- Live verifiziert (`python main.py Testfall_Jakob`, kompletter Durchlauf, Mail verschickt) –
  funktioniert, auch wenn eine zu vage Zielangabe im Testfall selbst ("österreichische Alpen")
  noch mehrfaches Nachhaken der KI auslöste, bevor sie selbst eine begründete Annahme traf.
- **Empfehlung an den Nutzer (siehe Projektkonversation):** für schnelles, zuverlässiges Testen
  der PLANUNG (POIs/Routen/Zeiten) `pruefe_planung.py` (kein LLM, Sekunden statt Minuten)
  verwenden; `main.py`/echter Chat nur noch gezielt für das Gesprächsverhalten selbst, das
  `pruefe_planung.py` naturgemäß nicht prüft.
- **Bug 1 (dabei gefunden, live):** `pruefe_planung.py` stürzte mit einer zu vagen Zielangabe
  ("Mittelmeerraum") mit einem rohen `RuntimeError: Google-Maps-API-Fehler (NOT_FOUND)` ab –
  derselbe Absturz würde einer echten Nutzerin im Live-Chat passieren. *Fix:*
  `google_maps.py::_hole_route` behandelt den Directions-Status NOT_FOUND jetzt wie ZERO_RESULTS
  (keine Route für DIESE Alternative statt eines harten Fehlers) – andere Fehlerstatus (z.B.
  REQUEST_DENIED) werden weiterhin durchgereicht.
- **Bug 2 (Folgefehler von Bug 1):** Liefert KEINE einzige Verkehrsmittel-Alternative eine Route
  (z.B. Ziel komplett unauflösbar), stürzte `pipeline.py::plane_reise` mit einem kryptischen
  `IndexError` auf `bewertete[0]` ab. *Fix:* klare, verständliche `ValueError`-Meldung
  ("Ortsangabe zu ungenau, bitte konkreteren Ort verwenden") statt eines rohen Tracebacks.
- Testfälle `planungs_testfaelle/Annegret.json`, `Jakob.json`, `Thomas.json` neu angelegt (aus den
  drei vom Nutzer erstellten `testfaelle/*.json`-Personas abgeleitet, für den schnellen
  `pruefe_planung.py`-Pfad) – dabei bewusst konkretere Zielorte gewählt (Mallorca/Innsbruck/
  München statt Mittelmeerraum/österreichische Alpen/Deutschland), weil Regions-/Länder-Ebene für
  eine sinnvolle lokale POI-/Routensuche zu grob ist (siehe schema.py `zielregionen`-Doku). Alle
  drei laufen jetzt fehlerfrei durch. Komplette Suite weiterhin 201/201 grün.

## Phase 26 — Eine Frage pro Nachricht statt gebündelter Rückfragen (12.08.2026)

- **Was:** `regelwerk.py::_TOOL_ANLEITUNG` verlangt jetzt explizit: GENAU eine Frage pro
  Nachricht, nie mehrere nummerierte Katalogfragen gebündelt. Eine kurze, erkennbar
  zusammengehörige Zusatzangabe INNERHALB einer Frage bleibt erlaubt (z.B. "wie alt sind die
  Kinder ungefähr?" als Ergänzung zur Reisebegleitungs-Frage).
- **Warum:** Live beobachtet (Nutzer-Test mit `Testfall_Thomas`): die KI stellte drei
  nummerierte Katalogfragen (Anrede, Wohnort, Reisebegleitung) gleichzeitig in einer einzigen
  Nachricht. Bisher gab es dafür keine explizite Anweisung im System-Prompt – nur "stelle
  grundsätzlich jede Frage", nichts zur Bündelung.
- Reine Prompt-Änderung, keine Logikänderung – wirkt erst in NEU gestarteten Sitzungen (der
  System-Prompt wird einmalig bei Sitzungsstart geladen), nicht rückwirkend in einem bereits
  laufenden Chat. Komplette Suite weiterhin 201/201 grün (keine Codeänderung betroffen).

## Phase 27 — main.py/testfaelle/SkriptKanal vollständig entfernt (12.08.2026)

- **Was:** `main.py`, der komplette `testfaelle/`-Ordner (inkl. `Testfall_Annegret.json`,
  `Testfall_Jakob.json`, `Testfall_Thomas.json`) sowie `SkriptKanal`/`SkriptEndeFehler`
  (`src/audio/kanal.py`, wurden ausschließlich von `main.py` instanziiert) ENTFERNT. Stale
  Kommentar-Referenzen auf `main.py` in `chat.py`, `google_maps.py`, `hotelbeds.py`,
  `aufbereitung.py`, `agent_tools.py`, `katalog.py`, `schema.py`, `pipeline.py` korrigiert.
  `README.md` entsprechend angepasst. `tests/*.py` (pytest-Suite, 201 Tests) UND
  `planungs_testfaelle/*.json` + `pruefe_planung.py` bleiben unangetastet – explizit vom Nutzer
  ausgenommen.
- **Warum:** Die Chat-Dialog-Simulation (main.py + testfaelle/*.json, siehe Phase 24/25) blieb
  trotz der Nachbesserungen (konsolidierter Info-Dump, Sicherheitsnetz) strukturell fragil –
  SkriptKanal gibt immer stur die nächste vorbereitete Antwort aus, unabhängig davon, ob sie zur
  tatsächlich gestellten Frage passt, was bei unerwarteten Rückfragen kaskadierend zu falschen
  Antworten führt. Nutzerentscheidung: künftig manuell über `python chat.py` testen statt über
  eine automatisierte, aber unzuverlässige Chat-Simulation. `tests/*.py` blieb explizit erhalten,
  nachdem klargestellt wurde, dass die pytest-Suite ein unabhängiges, deterministisches,
  kostenloses Testverfahren ohne LLM-Beteiligung ist und mit der Fragilität der Dialog-Simulation
  nichts zu tun hat – laut Nutzer aber langfristig ebenfalls zur Disposition ("das kommt später
  auch noch raus"), nur nicht jetzt.
- Komplette Suite weiterhin 201/201 grün (keine Testabhängigkeit von main.py/testfaelle/
  SkriptKanal bestand).

## Phase 28 — Flexibilitätspräferenz begrenzt POIs pro Tag (12.08.2026)

- **Was:** `ReiseAnfrage.flexibilitaet_praeferenz` (F05) wurde bisher abgefragt und gespeichert,
  aber NIRGENDS im deterministischen Layer ausgewertet – ein toter Fragekatalog-Eintrag. Neue
  Funktion `aufbereitung.py::max_pois_pro_tag_fuer_flexibilitaet` (Schlüsselwort-Zählung, siehe
  `_FLEXIBEL_SCHLUESSELWOERTER`/`_UNFLEXIBEL_SCHLUESSELWOERTER`): bei klarem Signal in eine
  Richtung liefert sie eine Tages-Obergrenze für die reine ANZAHL POI-Besuche (flexibel: 2,
  unflexibel/durchgeplant: 6) – bei fehlender ODER gemischter/widersprüchlicher Angabe (z.B.
  "ein fester Plan ist ganz nett, aber ich möchte auch spontan sein") heben sich die Signale
  bewusst auf, `None` (keine zusätzliche Einschränkung), statt eine Präferenz zu erfinden. Neues
  Feld `TOPTWInstanz.max_pois_pro_tag` (toptw.py `simuliere_route`) setzt das als harte
  Nebenbedingung durch – unabhängig davon, ob zeitlich noch mehr POIs reinpassen würden.
- **Warum:** Nutzerwunsch: "Flexibilitätspräferenz soll auch Auswirkungen auf die POIs am Tag
  haben – bei flexibel nur ein gewisses Fenster an POIs pro Tag, bei unflexibel ein höheres Maß."
- Live verifiziert (`pruefe_planung.py Jakob`, "eher flexibel"): exakt 2 POIs pro Tag statt vorher
  5–6, spürbar mehr freie Zeit. 6 neue Tests (`test_aufbereitung.py`, `test_toptw.py`). Komplette
  Suite: 207/207 grün.

## Phase 29 — Keine Hotel-/POI-Auswahl mehr im Chat (12.08.2026)

- **Was:** F15 (`unterkunft_anforderungen`) und F16 (`aktivitaeten_interessen`) sind keine
  Typ-C-Fragen (Dialogfrage mit API-Vorschau + Zustimmungsschleife) mehr, sondern normale
  Typ-B-Wertfragen (`katalog.py`): das LLM erfragt nur noch die reine Anforderung/das reine
  Interesse als Text und speichert sie direkt per `speichere_feld` – ohne `hole_api_daten`
  aufzurufen, ohne konkrete Hotelnamen/POI-Namen im Gespräch zu zeigen, ohne Zustimmungsschleife.
  `agent_tools.py::hole_api_daten` akzeptiert dadurch nur noch `verkehrsmittel_praeferenz` (F13,
  bleibt Typ C – hier ist eine echte Nutzerentscheidung mit Nachhaltigkeits-Nudge gewollt).
  `vorschlaege.py::hole_echte_daten_fuer_vorschlag` wurde entsprechend um die beiden toten Zweige
  (samt Kandidaten-Kappung, Warnschwellen-Rückfrage, Anfahrtsempfehlung je POI) gekürzt – die
  eigentliche Auswahl war schon vorher rein deterministisch: `pipeline.py::_plane_bestes_depot`
  testet weiterhin mehrere echte Unterkunfts-Kandidaten per vollständiger Optimierung durch und
  nimmt die mit der besten Route, `aufbereitung.py::waehle_top_pois` wählt weiterhin die POIs nach
  Score – beides UNVERÄNDERT, nur eben nie im Chat gezeigt, sondern erst im fertigen
  Reiseplan/der Mail sichtbar.
- **Warum:** Nutzerwunsch: "Es soll keine Auswahl mehr geben an Hotels. Es soll selber ein Hotel
  rausgesucht werden nach den Maßgaben, genau dieses eine Hotel wird dann genommen [...] auf Basis
  dieses Hotels kann dann die Optimierung besser durchgeführt werden." Auf Rückfrage präzisiert:
  "Ein Hotel soll ausgesucht werden und dann in der Mail angegeben. Nicht nochmal im Chat
  aufgezeigt. Das Selbe soll mit den POI's gemacht werden." Da die finale Auswahl schon vorher
  automatisch (ohne echte Nutzerwahl aus der Chat-Vorschau) geschah, war die Chat-Vorschau selbst
  die eigentlich überflüssige Zwischenstufe – Entfernen macht den Dialog kürzer, ohne die
  Planungsqualität zu verändern.
- Bewusst NICHT umgesetzt (siehe Rückfrage, vom Nutzer nicht gewählt): das frühe, einmalige
  Festlegen EINES Hotels direkt nach F15 (vor der POI-Suche), das der Nähe-Gewichtung schon beim
  ersten Kandidatenlauf eine echte statt einer groben Zielort-Koordinate gegeben hätte – bleibt
  ein möglicher künftiger Schritt, falls gewünscht.
- Aufgeräumt: `_MAX_UNTERKUNFT_KANDIDATEN`, `_WARNSCHWELLE_ROHTREFFER`, `_ANFAHRT_*`-Konstanten,
  `_anfahrtsempfehlung_je_poi`, `_mit_hinweisen` (vorschlaege.py) sowie 17 Tests, die ausschließlich
  die entfernten Chat-Vorschau-Zweige prüften (`test_vorschlaege.py`); 1 Test in
  `test_agent_tools.py` ersetzt (prüft jetzt die Ablehnung von `aktivitaeten_interessen` als
  Nicht-mehr-Typ-C-Feld statt der entfernten Vorschau-Weiterleitung). `trenne_bereits_im_paket_
  enthalten` (All-Inclusive-Sonderfall) bleibt unverändert, da direkt von `speichere_feld`
  gebraucht, unabhängig von der Chat-Vorschau. CLAUDE.md (Abschnitt "Fragekatalog"/"APIs &
  Dienste") entsprechend aktualisiert. Komplette Suite: 190/190 grün.

## Phase 30 — Aktivitäten/POIs (F16) zurück zu Typ C, nur Unterkunft (F15) bleibt vereinfacht (12.08.2026)

- **Was:** Teilrücknahme von Phase 29 – `aktivitaeten_interessen` (F16) ist wieder eine
  Typ-C-Dialogfrage (`katalog.py`: `fragetyp=Fragetyp.DIALOG`, `api_abruf_noetig=True`) mit voller
  Chat-Vorschau (echte POI-Kandidaten, Vertiefungs-Nachfragen bei unklaren Aktivitäten wie
  Klettern/Wassersport, Warnschwellen-Rückfrage bei zu vielen Treffern, Anfahrtsempfehlung je POI –
  alles 1:1 wie vor Phase 29 wiederhergestellt, siehe `vorschlaege.py::hole_echte_daten_fuer_
  vorschlag`, `agent_tools.py::hole_api_daten`, `regelwerk.py`). `unterkunft_anforderungen` (F15)
  bleibt UNVERÄNDERT bei der Phase-29-Vereinfachung (Typ B, keine Chat-Vorschau).
- **Warum:** Direkte Nutzerrückmeldung nach einem Live-Test: "POI sollten vielleicht doch noch mal
  ein bisschen besser nachgefragt werden [...] weil grade hatte sehr, sehr gut nachgefragt weiter
  bei meinen POIs." Auf Rückfrage bestätigt und präzisiert: "Macht die POIs einfach genauso, wie
  sie vorher waren, das war sehr, sehr gut. Nur mit den Unterkünften soll das anders sein." Die
  Vertiefungs-Nachfrage-Logik + echte Kandidatenvorschau bei Aktivitäten hat sich in der Praxis
  bewährt und wurde bei Unterkünften nicht vermisst (dort war die automatische Auswahl schon vorher
  die eigentliche Entscheidung, siehe Phase 29) – die beiden Felder unterscheiden sich also
  tatsächlich in der Praxis, nicht nur in der Theorie.
- Restauriert (aus dem Station-10-Code-Snapshot, `doku/10_.../code_stand/`): `_ANFAHRT_*`-
  Konstanten, `_WARNSCHWELLE_ROHTREFFER`, `_anfahrtsempfehlung_je_poi`, der komplette
  `aktivitaeten_interessen`-Zweig in `hole_echte_daten_fuer_vorschlag`, die zugehörigen
  `hole_api_daten`-Tool-Argumente (`aktivitaeten_aktuell`, `spezialrecherche_aktivitaeten`). 10
  Tests in `test_vorschlaege.py`/`test_agent_tools.py` wiederhergestellt bzw. angepasst. CLAUDE.md
  entsprechend korrigiert (nur noch F15 als Ausnahme genannt, F16 wieder als Typ-C-Feld gelistet).
  Komplette Suite: 200/200 grün.
- Offen/vertagt (aus derselben Nachricht, noch NICHT umgesetzt): (1) die Chat-Übersicht am Ende
  soll immer ALLE Tage zeigen statt nur den letzten; (2) "Essen" (Restaurants/Cafés/Bars) soll aus
  der Aktivitäten-Planung herausgenommen werden, Umfang noch in Klärung; (3) die Tagesausgabe soll
  von einem uhrzeitbasierten Zeitplan zu einer reinen geordneten Aktivitätenkette pro Tag ("vom
  Hotel zu A, dann B, dann C", Tagesstruktur/-obergrenze bleibt) umgebaut werden. Nutzer hat
  danach das Gespräch unterbrochen, um sich zunächst den kompletten Code erklären zu lassen –
  diese drei Punkte sind für eine spätere Sitzung vorgemerkt.

## Phase 31 — Unterkunft (F15) ruft hole_api_daten weiterhin auf, nur still (12.08.2026)

- **Was:** Präzisierung von Phase 29: `unterkunft_anforderungen` (F15) bekommt in `katalog.py`
  wieder `api_abruf_noetig=True` und ist damit technisch wieder ein Typ-C-Feld – `hole_api_daten`
  wird für F15 GENAUSO aufgerufen wie für jedes andere Typ-C-Feld, holt also echte Unterkunfts-
  Kandidaten (Google Places bzw. Hotelbeds bei erkanntem All-Inclusive-Wunsch, siehe
  `vorschlaege.py::hole_echte_daten_fuer_vorschlag`, Zweig `unterkunft_anforderungen` vollständig
  aus dem Stand vor Phase 29 wiederhergestellt, inkl. `_MAX_UNTERKUNFT_KANDIDATEN`-Kappung und
  Barrierefreiheits-Filter). NEU gegenüber dem alten Verhalten: liefert die Suche wirklich gar
  nichts, gibt es jetzt einen expliziten ehrlichen Hinweistext statt einer leeren Kandidatenliste
  (wichtig, weil das Ergebnis dem Nutzer nicht mehr vorgelesen wird – das LLM braucht trotzdem ein
  eindeutiges Signal für Transparenz, Grundprinzip 1). Einzige Änderung gegenüber dem klassischen
  Typ-C-Ablauf: laut `regelwerk.py` (Systemprompt) nennt das LLM dem Nutzer aus dem Ergebnis KEINE
  Hotelnamen/Kandidaten und holt KEINE Zustimmung zu einem bestimmten Hotel ein, sondern speichert
  direkt die reine Anforderung als Text – kein Vorschlag+Zustimmung-Dialog wie sonst bei Typ-C.
- **Warum:** In Phase 29 wurde `hole_api_daten` für F15 komplett deaktiviert (`api_abruf_noetig=
  False`), nicht nur die Chat-Vorschau entfernt. Nutzer-Korrektur: "doch es soll die Hotel API
  abrufen, das ist falsch! Es soll nur nicht nochmal im Chat erwähnt werden." Der eigentliche
  Wunsch war also nie, den API-Abruf selbst wegzulassen (das würde Grundprinzip 1 – nie ohne
  echten Datenabgleich – für dieses Feld faktisch aufheben) – sondern nur, dass das Ergebnis nicht
  mehr im Gespräch mit dem Nutzer diskutiert wird. Die finale Unterkunftswahl war ohnehin nie von
  diesem Chat-Abruf abhängig (das übernimmt unverändert `pipeline.py::_plane_bestes_depot`), daher
  ändert dieser stille Abruf an der Planungsqualität nichts – er dient nur als Realitätscheck
  während des Dialogs.
- 9 Tests in `test_vorschlaege.py` aus dem Stand vor Phase 29 wiederhergestellt (plus ein neuer
  Test für die "keine Treffer"-Ehrlichkeitsmeldung), 1 Test in `test_agent_tools.py` ersetzt (prüft
  jetzt, dass `hole_api_daten` für `unterkunft_anforderungen` wieder funktioniert statt
  abzulehnen). CLAUDE.md korrigiert. Komplette Suite: 209/209 grün.

## Phase 32 — Code-Review-Runde: sieben strukturelle Änderungen (12.08.2026)

Der Nutzer legte eine eigene Code-Review mit elf Punkten vor ("bitte formuliere dir selber aus
jeder Aussage eine Aufgabe und frage mich dann ab, ob ich das wirklich so haben will") – zu jedem
Punkt wurde per `AskUserQuestion` die genaue Absicht bestätigt (inkl. Auflösung von zwei
Widersprüchen zwischen einzelnen Punkten), erst danach umgesetzt. Sieben strukturelle Änderungen:

- **All-Inclusive/Flug komplett entfernt** (`src/api/hotelbeds.py`, `src/api/flightapi.py` inkl.
  Tests gelöscht – OHNE vorherigen Code-Stand-Snapshot, da beide Dateien in dieser Sitzung nie
  vollständig gelesen wurden; hier nur als Text dokumentiert, analog zu Station 1). Betroffene
  Felder (`all_inclusive_gewuenscht`, `all_inclusive_hotel_*`, `aktivitaeten_noch_per_poi_
  zu_planen`) aus `schema.py` entfernt, alle Sonderpfade in `vorschlaege.py`/`agent_tools.py`/
  `pipeline.py`/`chat.py`/`pruefe_planung.py` entfernt, `EMISSIONSFAKTOREN_G_PRO_PKM["flug"]`
  entfernt (nie mehr abgefragt). Grundprinzip 5 ("Flüge ausgeschlossen") ist damit ein echtes
  Hard-Rule ohne die vorherige eng begrenzte Ausnahme.
- **Barrierefreiheit + eingeschränkte Gehfähigkeit zusammengelegt**: `schema.py::
  barrierefreiheit_wichtig()`/`eingeschraenkte_gehfaehigkeit()` (zwei Methoden mit
  unterschiedlichen Konsequenzen) sind jetzt EINE Methode `barrierefreiheit_oder_
  eingeschraenkt()` – löst beide Effekte (harter Ausschluss UND Tempo/Pausen/Nähe-Anpassung)
  immer gemeinsam aus.
- **Sicherheit LLM-erkannt statt Schlüsselwort-Heuristik**: `sicherheit_ist_wichtig()` entfernt,
  ersetzt durch das vom LLM aus dem Gesamtkontext gesetzte Feld `sicherheit_bedenklich`
  (Tool-Argument bei `speichere_feld`, siehe katalog.py F11). Neu: bei erkennbar problematischem
  Ziel soll das LLM proaktiv eine sicherere Alternativregion vorschlagen (Regelwerk-Anweisung,
  analog zur bestehenden Distanz-Alternative).
- **Unterkunftswahl umgebaut**: `pipeline.py::_plane_bestes_depot` (testete bis zu 5 echte
  Kandidaten per vollständiger Optimierung durch) entfernt. Stattdessen sucht `vorschlaege.py::
  suche_unterkunft` GENAU EINE Unterkunft direkt bei F15, das LLM schlägt sie dem Nutzer vor und
  holt eine einfache Bestätigung ein ("passt das für dich?", F15 wieder Typ C), `speichere_feld`
  übernimmt Name/Koordinaten/place_id auf die Anfrage. `pipeline.py::plane_reise` nutzt danach
  GENAU diese Koordinaten als Depot – keine zweite, unabhängige Suche mehr. `_MAX_UNTERKUNFT_
  KANDIDATEN`, `Reiseplan.alle_unterkunft_kandidaten` entfernt (nur noch 1 Unterkunft, keine
  "weiteren Empfehlungen"-Liste für Hotels).
- **Verleih-Suche an die KI übergeben**: `pipeline.py::_suche_lokalen_verleih` (deterministisch,
  wählte nach generischem POI-Score) entfernt. Stattdessen sucht `vorschlaege.py::
  suche_verleih_nahe_unterkunft` (neuer direkter Pfad über `hole_api_daten`, feld=
  lokaler_transport_praeferenz) bei erkanntem Leihwunsch einen echten Verleih und wählt den mit
  der geringsten Koordinaten-Distanz zur BEREITS BESTÄTIGTEN Unterkunft (F15) – braucht deshalb
  ein abgeschlossenes F15, sonst liefert das Werkzeug nur einen Hinweis, es später erneut zu
  versuchen. Ergebnis wird deterministisch (ohne Zustimmungsschleife) auf `anfrage.
  lokaler_verleih_gewaehlt` übernommen, da die Auswahl rein auf Distanz beruht.
- **Verkehrsmittel-Nudge vorgezogen**: die Zeit/Kosten/CO2-Gewichtung (`bewerte_alternativen`/
  `nachhaltigkeits_nudge`) lief bisher nur EINMAL, ganz am Ende nach der kompletten Planung – der
  Nudge erreichte den Nutzer also nie VOR seiner F13-Entscheidung. Läuft jetzt zusätzlich schon in
  `vorschlaege.py::hole_echte_daten_fuer_vorschlag` (verkehrsmittel_praeferenz-Zweig), der Nudge
  erscheint direkt in der Chat-Vorschau. Die bestehende Regel "bestätigtes Verkehrsmittel wird
  respektiert" (`_nur_bestaetigte_verkehrsmittel`, Phase 11) bleibt unverändert – die Optimierung
  darf eine Nutzerentscheidung weiterhin nicht überstimmen.
- **Nachplanungs-Prüfung für Barrierefreiheit**: neu `vertraeglichkeit.py::pruefe_
  barrierefreiheit_des_plans` – prüft nach Abschluss der Optimierung den TATSÄCHLICH geplanten
  Reiseplan (nicht nur die Kandidatenliste davor) noch einmal gegen echte Google-Daten. Erfüllt er
  eine genannte Anforderung nicht, schlägt `plane_reise_und_abschliessen` mit `is_error` fehl und
  weist das LLM an, den Nutzer zu fragen, ob eine strengere Neuplanung (mit denselben Daten, siehe
  neuer Parameter `barrierefreiheit_strikt` in `filtere_pois_hart`/`pipeline.py::plane_reise`) in
  Ordnung ist – erst der erneute Aufruf mit `barrierefreiheit_bereits_gepruft=true` schließt ab.

Nicht umgesetzt (laut Nutzer bewusst zurückgestellt, siehe Prompt-Ende: "mache den anderen Prompt
erst fertig, dann kümmer dich um die zwei Punkte"): (1) die Tagesablauf-Parameter-Interpretation
(`aufbereitung.py::parameter_fuer_tagesablauf`, aktuell ein Regex-Parser) soll stattdessen der KI
zur Interpretation übergeben werden; (2) eine Web-Oberfläche (HTML-Seite statt Konsole) mit
Bild-/Kurzinfo-Vorschau für Hotels und POIs (ähnlich der Google-Maps-Ergebnisvorschau), der
bestehende Text-Chat bleibt parallel bestehen. Beides für eine spätere Sitzung vorgemerkt.

Umfangreicher Test-Umbau (test_vorschlaege.py, test_agent_tools.py, test_fragekatalog.py,
test_aufbereitung.py, test_reiseplan.py, test_vertraeglichkeit.py, test_emissionsfaktoren.py neu
geschrieben/ergänzt) sowie ein Kommentar-Sweep in den am stärksten betroffenen Dateien (historische
"Projektkonversation"/"BEHOBENER BUG"-Verweise durch gegenwartsbasierte Beschreibungen ersetzt, auf
Wunsch des Nutzers: "die Doku im Code sollte immer gegenwartsbasiert sein"). Komplette Suite:
191/191 grün.

## Phase 33 — Tagesablauf-Zeitfenster (F20) vom LLM interpretiert statt per Regex (12.08.2026)

- **Was:** `aufbereitung.py::parameter_fuer_tagesablauf` (Regex-Parser: erste/letzte erkannte
  Uhrzeit im Freitext, sonst Standardannahme 09:00–21:00) komplett entfernt. Stattdessen
  interpretiert das LLM die F20-Antwort selbst und übergibt `tagesstart_minuten`/`tagesende_
  minuten` (Minuten seit Mitternacht) als neue Tool-Argumente bei `speichere_feld` (analog zu
  `sicherheit_bedenklich`/`aktivitaeten_gewichtung`) – neue Felder direkt auf `ReiseAnfrage`
  (schema.py), keine Zwischenspeicherung nötig. `pipeline.py::plane_reise` nutzt diese Werte jetzt
  AKTIV als Basis-Tagesbudget für Optimierung 1 (Differenz Ende−Start), statt wie bisher nur den
  Start-Wert für die Anzeige zu berechnen und den Rest zu verwerfen – ein vom Nutzer genanntes
  Zeitfenster wirkt sich damit erstmals tatsächlich auf die Optimierung aus, nicht nur auf die
  Uhrzeiten-Anzeige im Reiseplan.
- **Warum:** Nutzer-Feedback: "Werden die Parameter für den Tagesablauf nicht noch mit in die
  Anfrage für die KI mit eingesetzt, sondern hier jetzt schon wieder in Aufbereitung noch mal
  extra als Code dargestellt. Das möchte ich bitte nicht [...] ohne diese Interpretation der KI
  kommt da am Ende kein vernünftiger Datensatz bei raus, wenn man nur den Nutzer fragt." Ein
  Regex-Muster erkennt nur exakte Uhrzeit-Zahlen ("9 Uhr", "09:00") und scheitert an natürlicher
  Sprache ("eher früh los, nicht so spät zurück") – das LLM versteht solche Formulierungen
  zuverlässig. Zusätzlicher, beim Nachfragen selbst aufgefallener Bonus: der bisherige Enduhrzeit-
  Wert wurde SOWIESO nie verwendet (nur `[0]`, der Start, ging in den Reiseplan ein) – die
  Umstellung behebt das gleich mit, statt eine zweite tote Berechnung nur umzuformulieren.
- Tests: `test_parameter_fuer_tagesablauf_*` (2 Tests, testeten den entfernten Regex-Parser direkt)
  entfernt, 2 neue Tests in `test_agent_tools.py` für die Tool-Argument-Persistierung ergänzt.
  Komplette Suite: 191/191 grün (Netto-Null-Änderung an der Testanzahl).

## Phase 34 — Web-Oberfläche (webapp.py) mit Foto-Karten statt reiner Konsole (13.08.2026)

- **Was:** Zweiter Einstiegspunkt `webapp.py` (FastAPI + WebSocket, `/ws/chat`) neben dem
  bestehenden `chat.py` – führt DENSELBEN Dialog (`chat.py::hauptablauf`, unverändert in seiner
  Logik) über einen Browser-Chat statt die Konsole. Dafür wurde `IOKanal` (src/audio/kanal.py,
  bisher synchron) auf `async def bot_sagt`/`async def nutzer_antwortet` umgestellt (TextKanal/
  AudioKanal bleiben intern weiterhin blockierend, das ist für eine Konsolen-Anwendung unschädlich)
  – ein neuer `WebIOKanal` (webapp.py) bindet WebSocket-Nachrichten an dieselbe Schnittstelle an.
  `hauptablauf` gibt jetzt den finalen `AgentSessionState` zurück (vorher `None`), damit webapp.py
  nach Gesprächsende noch den fertigen Reiseplan weiterverarbeiten kann.
  Der fertige Reiseplan zeigt zusätzlich, NUR am Ende (nicht live während des Gesprächs, siehe
  Rückfrage unten), Karten mit Foto/Kurzbeschreibung/Google-Maps-Link je Unterkunft und
  eingeplantem POI (`reiseplan.py::als_kartendaten`) – analog zur kleinen Vorschau, die Google Maps
  beim Anklicken eines Ortes zeigt. Neue Felder `POI.foto_referenz`/`Unterkunft.foto_referenz`
  (typen.py, aus `photos[0].photo_reference` der ohnehin schon laufenden Places-Suche, KEIN
  zusätzlicher API-Aufruf) sowie `ReiseAnfrage.unterkunft_foto_referenz`/
  `Reiseplan.unterkunft_foto_referenz`, durchgereicht bis in agent_tools.py/pipeline.py. Als
  Kurzbeschreibung dient `POI.kategorie` (bereits vorhandene Daten) statt einer zusätzlichen,
  kostenpflichtigen Place-Details-Anfrage für einen redaktionellen Text.
  Fotos werden ERST NACH Abschluss der Planung serverseitig heruntergeladen (neues Modul
  `src/ausgabe/fotos.py::lade_fotos_fuer_plan`, neue Methode `MapsClient.lade_foto`) in
  `ergebnisse/fotos/<sitzung_id>/` und von FastAPI als statische Dateien ausgeliefert – der
  Google-Maps-API-Key bleibt dadurch ausschließlich serverseitig, der Browser bekommt ihn nie zu
  sehen (siehe Rückfrage unten). `chat.py`/`pruefe_planung.py` lösen KEINEN Foto-Download aus, nur
  webapp.py – keine zusätzlichen API-Kosten im normalen Konsolen-Betrieb.
  `reiseplan.py::_maps_link` in das öffentliche `maps_link` umbenannt (wird jetzt auch von
  `als_kartendaten`/webapp.py gebraucht, nicht mehr nur modulintern).
  Frontend: eine einzelne, abhängigkeitsfreie `static/index.html` (Chat-Verlauf + WebSocket-Klasse
  + Ergebnis-Kartenraster, kein Build-Schritt/Framework).
- **Warum:** Nutzerwunsch: "ich hab keinen Bock mehr, über die Konsole das anzusteuern [...] hätte
  gerne immer noch diesen normalen Chat halt offen, um das zu testen [...] wenn ich Vorschläge
  bekomme [...] dass ich nicht nur da stehen hab, hier ist ein Link zu dem und dem Hotel, sondern
  direkt so einen kleinen Overview, [...] Foto drin, kurz beschrieben, was das ist, [...] Genau das
  Gleiche bei den POIs. Am wichtigsten ist mir das für Hotel und POIs." Vier Rahmenentscheidungen
  vor der Umsetzung per Rückfrage geklärt: FastAPI (async-nativ, passt zum bestehenden
  `ClaudeSDKClient`/asyncio-Code, kein zusätzliches Setup), WebSocket-Transport (statt Polling/SSE),
  Karten NUR im fertigen Reiseplan (nicht live während des Gesprächs, einfacherer Einstieg), Fotos
  serverseitig "bei API-Abruf" statt über einen client-seitigen Key-Proxy (der Google-Maps-Key darf
  laut ausdrücklicher Nutzervorgabe nie im Browser sichtbar werden).
- Prozess-Hinweis: betroffene Dateien VOR der Änderung nach `doku/15_stage15_web_ui/code_stand/`
  gesichert (siehe `doku/15_.../README.md`) – diesmal ohne den in Phase 32 passierten Fehler
  (Snapshot fehlte dort für zwei gelöschte Dateien).
- Tests: 12 neue Tests (`test_fotos.py` neu: 4 Tests für `lade_fotos_fuer_plan` mit Fake-Client;
  `test_google_maps.py`: 4 Tests für `foto_referenz`-Übernahme + `lade_foto`; `test_reiseplan.py`:
  3 Tests für `als_kartendaten`) plus ein Smoke-Test von `webapp.py` über `TestClient` (Index-Route,
  Static-Mount) außerhalb der pytest-Suite. Keine WebSocket-/LLM-Ende-zu-Ende-Tests in pytest (wie
  bei chat.py auch: Gesprächsverhalten wird manuell verifiziert, nicht automatisiert gegen echte
  LLM-Kosten). Komplette Suite: 203/203 grün (191 + 12 neue).

## Phase 35 — Erstes Nutzertest-Feedback: Kostenschätzung, Hotel-Karte im Chat, echte Websuche, Zielregionen-Klarstellung (13.08.2026)

Fünf Rückmeldungen nach dem ersten echten Testlauf von webapp.py, vier davon per Rückfrage (siehe
unten) bewusst entschieden statt einfach umgesetzt – zwei widersprachen bestehenden, bewussten
Entscheidungen (Grundprinzip 1-3 bei der Websuche, "Karten nur am Ende" bei der Hotel-Karte).

- **Was (Kostenschätzung):** Neues Modul `src/optimierung/kostenschaetzung.py` schätzt die
  Gesamtkosten PRO PERSON (An-/Abreise, Unterkunft, eingeplante Aktivitäten, jeweils aus Googles
  `price_level` 0–4 grob in Euro umgerechnet + eine dokumentierte Tagespauschale für Verpflegung,
  35 €/Tag) und zeigt sie im fertigen Reiseplan im Vergleich zu `budget_gesamt` (F-Budget-Frage).
  Neue Felder `POI.preisniveau`/`ReiseAnfrage.unterkunft_preisniveau`/
  `Reiseplan.geschaetzte_kosten_euro`/`kosten_unvollstaendig`/`budget_gesamt`. POIs OHNE
  Preisniveau (meist Parks/Plätze/Aussichtspunkte) zählen als kostenlos statt die Schätzung als
  unvollständig zu markieren; fehlt es bei der UNTERKUNFT, wird das dagegen sichtbar
  gekennzeichnet. **Bewusst NUR Anzeige** – beeinflusst NICHT die POI-Auswahl in Optimierung 1
  (Rückfrage-Ergebnis: "nur informativ anzeigen").
- **Was (Hotel-Karte live im Chat):** `IOKanal` (kanal.py) bekommt eine neue Methode
  `zeige_karte(unterkunft)` (No-Op bei TextKanal/AudioKanal – Konsole kann keine Bilder zeigen,
  siehe Moduldoku). `chat.py::hauptablauf` ruft sie NACH jedem Turn auf, sobald
  `hole_api_daten(unterkunft_anforderungen)` einen neuen Kandidaten gefunden hat
  (`state.zuletzt_gefundene_unterkunft`, per Objekt-Identität gegen erneutes Senden dedupliziert).
  `WebIOKanal.zeige_karte` (webapp.py) lädt das Foto SOFORT herunter (eigener `MapsClient`, eigener
  Sitzungsordner – unabhängig vom Batch-Download am Ende, da der Reiseplan zu diesem Zeitpunkt noch
  nicht existiert) und schickt Name/Foto/geschätzten Preis pro Nacht/Maps-Link als eigene
  `hotel_karte`-WebSocket-Nachricht; das Frontend (static/index.html) rendert sie als eigene
  Karten-Bubble im Chat-Verlauf. **Bewusst NUR bei der Unterkunft (F15)** – alle anderen Karten
  (Aktivitäten/POIs) bleiben wie in Phase 34 entschieden nur im fertigen Reiseplan.
- **Was (echte Websuche für den Agenten):** `chat.py` erlaubt jetzt zusätzlich zu den 5 MCP-Tools
  das eingebaute `WebSearch`-Werkzeug (`tools=["WebSearch"]`, `allowed_tools`
  entsprechend erweitert). `regelwerk.py` bekommt einen neuen WEBSEARCH-Abschnitt: die Websuche
  ersetzt NICHT die deterministischen API-Werkzeuge für POIs/Unterkünfte/Preise/Reisezeiten (die
  bleiben die EINZIGE Quelle für Optimierung 1+2), sondern deckt reine Kontext-/
  Hintergrundrecherche ab, die sonst gar nicht möglich wäre. **Bewusste, dokumentierte Ausnahme von
  Grundprinzip 2** (CLAUDE.md entsprechend ergänzt) – analog zum Präzedenzfall beim Architekturwechsel
  in Phase 2: der Nutzer wurde auf den Konflikt hingewiesen und hat sich informiert dagegen
  entschieden ("wirklich freien Web-Zugriff zulassen").
- **Was (Zielregionen-Klarstellung):** Root-Cause-Fund: die Vorschau UND die finale Planung
  verwenden BEIDE ausschließlich `ReiseAnfrage.primaeres_reiseziel()` (die erste genannte Region) –
  bei mehreren genannten Städten (im Test: Magdeburg/Potsdam/Berlin) wird de facto NUR die erste
  geplant. Der Bot hatte im Live-Test dem Nutzer fälschlich erklärt, die finale Planung würde
  "später noch alle drei Städte einzeln durchsuchen" – eine unbelegte Behauptung über die eigene
  Architektur, die so nicht stimmt. Fix bewusst MINIMAL gehalten (Rückfrage-Ergebnis: "einfach immer
  nur darauf verweisen, dass nur eine Stadt pro Trip geplant werden kann", keine echte Multi-Stadt-
  Unterstützung): F07-`kontext_hinweis` (katalog.py) weist das LLM an, bei mehreren genannten
  Regionen aktiv auf die Ein-Ziel-Grenze hinzuweisen; zusätzlich eine Verteidigungslinie in
  `vorschlaege.py` (`_mehrere_zielregionen_hinweis`, an allen drei Such-Einstiegspunkten
  `suche_unterkunft`/`aktivitaeten_interessen`/`verkehrsmittel_praeferenz`), die dem LLM bei JEDEM
  betroffenen Tool-Aufruf erneut verbietet, eine spätere Mehrstädte-Suche zu behaupten – auch wenn
  der F07-Hinweis übersprungen/ignoriert wurde.
- **Was (Mikrofon + Vorlesefunktion im Browser-Chat):** `static/index.html` bekommt einen
  Mikrofon-Knopf (🎤, Web Speech API `SpeechRecognition`) und einen Vorlesen-Knopf (🔊,
  `speechSynthesis`) – bewusst REIN CLIENTSEITIG über den Browser, KEINE Serverbeteiligung wie beim
  bestehenden `AUDIO_MODUS`/`AudioKanal` (das bräuchte Mikrofon/Lautsprecher am SERVER, nutzlos für
  einen entfernten Browser-Nutzer – Nutzervorgabe: "Standardausgabe und Standardeingabe des
  Nutzergeräts"). Eine erkannte Spracheingabe durchläuft denselben `sendeNachricht`-Pfad wie
  getippter Text (der Dialog läuft laut Nutzerwunsch "genauso ab, wie er abläuft"); die erste
  Spracheingabe schaltet automatisch auch das Vorlesen ein (jederzeit einzeln abschaltbar). Kein
  Backend-Code nötig – `chat.py`/`webapp.py`/`agent_tools.py` bleiben unverändert. Bekannte
  Einschränkung: `SpeechRecognition` wird von Firefox nicht unterstützt (Chrome/Edge/Safari schon)
  – der Mikrofon-Knopf erkennt das und deaktiviert sich mit erklärendem Tooltip, Text/Vorlesen
  bleiben nutzbar.
- **Nachtrag (13.08.2026, direkt nach dem ersten echten Ausprobieren):** zwei Korrekturen am
  Mikrofon/Vorlesen aus demselben Testlauf. (1) BEHOBENER BUG: der Mikrofon-Knopf leuchtete
  optimistisch SOFORT beim Klick rot (noch bevor die Erkennung tatsächlich lief) und ein zweiter
  Klick während einer laufenden Erkennung rief `start()` erneut auf – das wirft einen synchronen
  `InvalidStateError`, den `error`/`end` kommentarlos abräumten ("leuchtet rot, hört sofort wieder
  auf, funktioniert nicht"). Jetzt schaltet sich Rot erst nach dem echten `start`-Ereignis, ein
  zweiter Klick während des Zuhörens beendet die laufende Erkennung sauber statt sie neu zu
  starten, und jeder Fehler (`not-allowed`, `audio-capture`, `no-speech`, `network`, …) bekommt eine
  sichtbare, erklärende Meldung im Chat statt nur unsichtbar zu verschwinden. (2) Vorlesefunktion
  wählt jetzt aktiv eine natürlicher klingende deutsche Stimme (`speechSynthesis.getVoices()`,
  bevorzugt Netzwerk-/Cloud-Stimmen wie "Google Deutsch" statt der robotischen lokalen
  System-Stimme) statt der Browser-Voreinstellung – Nutzerwunsch: "kann man da eine nettere Stimme
  nehmen?".
- **Zweiter Nachtrag (13.08.2026):** Nutzer meldete beim Ausprobieren durchgehend einen
  `network`-Fehler der Spracherkennung – KEIN Bug im eigenen Code, sondern eine strukturelle
  Eigenschaft der Web Speech API: Chrome schickt die Audiodaten an Googles Spracherkennungsdienst,
  und Chromium-Browser ohne Googles privaten API-Schlüssel (Brave, Opera, ...) oder blockierende
  Adblocker/Firewalls bekommen dafür IMMER diesen Fehler, unabhängig von der echten
  Internetverbindung. Nutzer besitzt zusätzlich Whisper Flow (externes System-Diktier-Tool, tippt
  direkt ins fokussierte Feld) – funktioniert schon OHNE Codeänderung mit dem bestehenden
  Eingabefeld. Per Rückfrage entschieden: eingebauter Mikrofon-Knopf bleibt als Fallback im Code
  (für Nutzer/Browser ohne Whisper Flow), NICHT entfernt. Die `network`-Fehlermeldung in
  `static/index.html` wurde präzisiert (nennt die wahrscheinlichen echten Ursachen statt nur
  "Internetverbindung nötig") und weist auf Chrome/Edge bzw. normales Tippen/externe
  Diktier-Tools wie Whisper Flow als Alternativen hin.
- Tests: 21 neue Tests (`test_kostenschaetzung.py` neu: 5; `test_google_maps.py`: 2 für
  `price_level`-Übernahme; `test_reiseplan.py`: 6 für die Kosten-Textausgabe; `test_vorschlaege.py`:
  3 für den Zielregionen-Hinweis; `test_kanal.py` neu: 1 für `zeige_karte`-No-Op; `test_webapp.py`
  neu: 4 für `WebIOKanal.zeige_karte`; plus 1 erweiterte Assertion in test_agent_tools.py für
  `unterkunft_preisniveau`). Mikrofon/Vorlesen sind reines Browser-JS ohne Python-Gegenstück –
  manuell verifiziert (Seite lädt, Elemente vorhanden), wie der Rest der Chat-UI. Komplette Suite:
  224/224 grün (203 + 21 neue).
- Prozess-Hinweis: betroffene Dateien VOR der Änderung nach
  `doku/16_stage16_testfeedback_kosten_karten_suche/code_stand/` gesichert.

## Phase 36 — Verkehrsmittel je Etappe im Reiseplan, Planungs-Debug-Ausgabe (13.08.2026)

Drei Rückmeldungen nach dem Ausprobieren der Kostenschätzung/Hotel-Karte (Phase 35), zwei davon vor
der Umsetzung per Rückfrage geklärt (Recherche-Ergebnis vorab mitgeteilt, siehe unten).

- **Was (Verkehrsmittel je Etappe):** Recherche ergab: die reine Fahrzeit zwischen POIs kam schon
  vorher real von Google (`aufbereitung.py::hole_reisezeitmatrix`, VOR dem Optimierungslauf
  abgerufen) – der Algorithmus selbst berechnet nichts. Es fehlte nur die ANZEIGE, welches
  Verkehrsmittel gemeint war, UND die ganze Reise nutzte immer nur EIN global festgelegtes
  Verkehrsmittel. Nach Rückfrage ("Variante B: erst optimieren, dann nur die gewählten Etappen
  erneut abfragen" statt vorab alle Kandidaten-Paare multimodal durchzufragen – weniger API-
  Aufrufe, Zeiten bleiben konsistent) umgesetzt:
  - `aufbereitung.py::modi_fuer_lokalen_transport` (ersetzt `modus_fuer_lokalen_transport`) erkennt
    jetzt ALLE in F14 genannten Verkehrsmittel statt nur das erste Dict-Match, sortiert nach der
    Position des jeweils frühesten Treffers IM TEXT (nicht nach `_TRANSPORT_PARAMETER`s zufälliger
    Definitionsreihenfolge – sonst hätte z.B. "zu Fuß, aber auch mit dem Auto" fälschlich Auto als
    zuerst genannt behandelt). `hole_reisezeitmatrix` fragt bei mehreren genannten Verkehrsmitteln
    die Distance Matrix je Modus ab (weiterhin EIN NxN-Aufruf pro Modus) und nimmt je Paar die
    schnellere Zeit – bestimmt damit direkt das Tempo, mit dem Optimierung 1 tatsächlich rechnet.
  - Neue Funktion `ergaenze_anfahrt_modus_je_etappe` (Variante B): läuft NACH Optimierung 1, NUR
    für die tatsächlich besuchten Etappen (nicht alle 30 Kandidaten) – bei nur einem genannten
    Verkehrsmittel (Regelfall) ohne zusätzlichen API-Aufruf, bei mehreren mit einem gezielten
    `anfahrtszeiten_minuten`-Aufruf je Etappe/Modus. Setzt neues Feld `Besuch.anfahrt_modus`
    (toptw.py) – rein für die Anzeige, verändert `ankunft`/`abfahrt` NICHT.
  - Anzeige in `reiseplan.py::als_text`/`als_html`/`als_kartendaten` sowie `static/index.html`:
    "→ 15 Min. (mit dem Fahrrad) von Unterkunft".
  - Live gegen die echte Google API smoke-getestet (siehe unten) – dabei einen unabhängigen,
    vorbestehenden Bug gefunden und behoben: `monte_carlo.py::_instanz_mit_gestoerten_fahrzeiten`
    stürzte mit `math domain error` ab, wenn zwei POIs so nah beieinander liegen, dass Google 0
    Minuten Reisezeit meldet (`math.log(0)`) – jetzt wie beim bestehenden Luftlinien-Fallback
    mindestens 1 Minute vor der Logarithmus-Bildung.
- **Was (Planungs-Debug-Ausgabe):** Neues Modul `src/ausgabe/debug.py`
  (`PlanungsDebugSammlung`/`schreibe_debug_datei`) – `pipeline.py::plane_reise` bekommt einen neuen,
  optionalen Parameter `debug_sammlung`, der (nur wenn übergeben) an jedem relevanten Schritt
  befüllt wird: rohe Google/Overpass-Treffer, nach harten Einschränkungen, an Optimierung 1
  weitergegebene Kandidaten (nach Scoring+Kappung), Optimierung-1-Eingabe/-Ergebnis,
  Härtetest-Eingabe/-Ergebnis. `pruefe_planung.py` übergibt eine Sammlung und schreibt sie als
  `<name>_debug.txt` neben die bestehenden Ausgaben – EIN lesbarer Textstapel mit klar markierten
  Abschnitten (Nutzerwunsch: "sodass ich einfach erkenne, welche Daten da behandelt werden, ohne
  dass ich das noch raussuchen muss"), keine Auswirkung auf chat.py/webapp.py (dort bleibt der
  Parameter `None`, kein Mehraufwand).
- **Nutzerentscheidungen aus der Rückfrage:** Variante B (nicht vorab alle Kandidaten-Paare
  multimodal abfragen); pro Etappe wird NUR EIN Verkehrsmittel genannt (kein Alternativen-Vergleich
  wie bei der F16-Anfahrtsempfehlung – "wir geben nichts anderes raus, [...] das ist die Option, die
  er vorgibt"); Debug-Ausgabe NUR aus `pruefe_planung.py` (nicht aus chat.py/webapp.py); Format:
  strukturierte, vorsortierte Textdatei statt JSON.
- **Entdeckte, noch nicht behobene Lücke:** `planungs_testfaelle/` (in README.md/pruefe_planung.py
  dokumentiert, u.a. als Default `klettern_essen`) existierte beim Smoke-Test NICHT mehr – nur die
  ALTEN Ausgaben (`ergebnisse/planung_Annegret/Jakob/Thomas.*`) belegen, dass es sie früher gab.
  Für den Smoke-Test wurde `planungs_testfaelle/smoketest_etappen.json` neu angelegt (Hannover,
  Fahrrad+Bahn), die ursprünglichen Testfälle wurden NICHT rekonstruiert (Inhalt unbekannt, keine
  Rekonstruktion ohne echte Grundlage, siehe Grundprinzip 1) – dem Product Owner mitgeteilt, siehe
  "Offene Punkte".
- Tests: 9 neue Tests (`test_aufbereitung.py`: 6 für `modi_fuer_lokalen_transport`/
  `parameter_fuer_lokalen_transport`/`hole_reisezeitmatrix`/`ergaenze_anfahrt_modus_je_etappe`;
  `test_reiseplan.py`: 4 für die Verkehrsmittel-Anzeige; `test_debug.py` neu: 3 für
  `schreibe_debug_datei`) – macht 13 neu, 6 alte Tests umbenannt/angepasst (kein Netto-Verlust).
  Zusätzlich EIN echter Live-Lauf gegen die Google API (`pruefe_planung.py`, siehe oben) zur
  Verifikation, da `plane_reise` selbst keine pytest-Integration hat (wie schon vorher, siehe
  ENTSCHEIDUNGSLOG.md frühere Phasen – nur die einzelnen reinen Funktionen sind unit-getestet).
  Komplette Suite: 239/239 grün (224 + ~15 netto).

## Phase 37 — Google-Maps-Routen-Links für jede Etappe und die An-/Abreise (13.08.2026)

- **Was:** Jede bereits bestehende Streckenzeile im Reiseplan bekommt zusätzlich einen
  Google-Maps-DIRECTIONS-Link (nicht nur einen Orts-Link wie `maps_link`) angehängt – öffnet
  Google Maps direkt mit Start-/Zielpunkt UND dem tatsächlich geplanten Verkehrsmittel
  vorausgewählt. Neue Funktion `reiseplan.py::routen_link(ursprung, ziel, travelmode)` nutzt
  Googles dokumentiertes Directions-URL-Schema
  (`https://www.google.com/maps/dir/?api=1&origin=...&destination=...&travelmode=...`) – KEIN
  zusätzlicher API-Aufruf, reine Link-Konstruktion aus bereits vorhandenen Koordinaten/Orten.
  Betrifft zwei Stellen, beide rein additiv (bestehender Text/bestehende Struktur unverändert):
  - Vor-Ort-Etappen (Unterkunft→POI, POI→POI): Koordinaten beider Punkte + `Besuch.anfahrt_modus`
    (siehe Phase 36) als `travelmode` – Googles Modus-Strings (walking/bicycling/transit/driving)
    sind intern bereits identisch zu den erwarteten `travelmode`-Werten, keine Übersetzung nötig.
  - Hinreise/Rückreise: `anfrage.wohnort`/Zielort als Ortsnamen (keine Koordinaten nötig, Google
    löst Namen selbst auf) + eine neue Zuordnung `_TRAVELMODE_JE_VERKEHRSMITTEL` ("Bahn"/"Fernbus"
    → transit, "Auto" → driving).
  Neue Felder `Reiseplan.unterkunft_koordinaten`/`wohnort`/`zielort` (nur für diese Links, die
  eigentliche Optimierung nutzt weiterhin `anfrage.*` direkt) – von `pipeline.py::plane_reise` aus
  bereits vorhandenen lokalen Variablen befüllt. Eingebaut in `als_text`/`als_html`/
  `als_kartendaten` + `static/index.html` ("Route ansehen"-Link je Karte). Fehlt ein Punkt (z.B.
  Unterkunft-Koordinaten unbekannt), bleibt der Link für genau diese eine Zeile schlicht weg statt
  einen geratenen Startpunkt zu erfinden (Grundprinzip 1).
- **Warum:** Nutzer-Feedback nach dem ersten erfolgreichen Test der Etappen-Zeiten (Phase 36): "Das
  find ich auch ganz total gut [...] mich würde nur noch freuen, wenn [...] die Route mitgegeben
  wird, wo Du direkt auf Google Maps kommst [...] und direkt Start-/Endpunkt hast [...] das soll
  alles so bleiben, wie's ist, nur dass hinten dran halt noch ein Link gehangen wird." Vor der
  Umsetzung per Rückfrage als eigene Aufgabe formuliert und vom Nutzer bestätigt ("ja genau so").
- Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) – Links
  für Etappen (Koordinaten) UND Hin-/Rückreise (Ortsnamen) korrekt gebildet und verifiziert.
- Tests: 10 neue Tests in `test_reiseplan.py` (4 für `routen_link` direkt, 6 für die Einbindung in
  als_text/als_html/als_kartendaten). Komplette Suite: 249/249 grün (239 + 10 neue).

## Phase 38 — Präzisere Hin-/Rückreise-Routen-Links, Bahnhöfe nicht mehr als POI-Kandidaten (13.08.2026)

Zwei Nachbesserungen direkt nach dem Ausprobieren der Routen-Links (Phase 37), beide vor der
Umsetzung per Rückfrage geklärt (Analyse zuerst vorgelegt, Nutzer hat bestätigt/präzisiert).

- **Was (präzise Hin-/Rückreise-Links):** Der Hinreise-/Rückreise-Link (Phase 37) zeigte bisher nur
  grob zwischen Wohnort und der Zielstadt (z.B. "Hildesheim" → "Hannover"), NICHT zur tatsächlich
  bestätigten Unterkunft. Neue Funktion `reiseplan.py::_hinreise_ziel_fuer_link` bevorzugt jetzt die
  GENAUEN Unterkunft-Koordinaten (`Reiseplan.unterkunft_koordinaten`, seit Phase 37 vorhanden) und
  fällt nur auf den groben Zielort-Namen zurück, wenn noch keine Unterkunft bestätigt ist – der
  Hinreise-Link geht damit Wohnort → genaue Unterkunft, der Rückreise-Link genaue Unterkunft →
  Wohnort ("der Heimreisepunkt wird bei uns immer als Abfahrtspunkt [genutzt]" – bereits
  `anfrage.wohnort`, keine neue Datenquelle nötig). Die Vor-Ort-Etappen-Links (POI-zu-POI) waren
  bereits präzise und blieben unverändert.
- ~~**Was (Bahnhöfe raus aus den POI-Kandidaten):** Nutzer meldete, dass am An-/Abreisetag Bahnhöfe
  als eigene POI-Karten (Foto+Link) in der Web-UI auftauchten, gelabelt im Bereich "An- und
  Abreise" – NICHT gewünscht, dort sollen ausschließlich echte Sehenswürdigkeiten stehen. Ursache:
  Googles Places-Text-Search kann einen Hauptbahnhof bei thematisch nahen Interessen (z.B.
  "Architektur"/"Sehenswürdigkeiten") legitim als Treffer liefern – ein Hauptbahnhof ist aber
  Verkehrsinfrastruktur, kein Ausflugsziel (die eigentliche An-/Abreise deckt bereits Optimierung 2
  separat ab). Neue Konstante `google_maps.py::_AUSGESCHLOSSENE_PLACE_TYPES`
  (`train_station`/`transit_station`/`bus_station`/`subway_station`/`light_rail_station`/`airport`)
  – `suche_pois` verwirft jeden Treffer, dessen Google-`types` einen dieser Werte enthält, VOR der
  Übernahme in die Kandidatenliste. Keine Stelle im Code hatte zuvor tatsächlich "An- und Abreise"
  als POI-Label erzeugt – die Bahnhöfe kamen als ganz normale (fälschlich passende) Sucht-Treffer
  rein, nicht durch einen eigenen Sondermechanismus.~~
- **Nachtrag (13.08.2026, direkt danach wieder zurückgenommen):** Nutzer wollte KEINE pauschale
  Ausschlussliste – Bahnhöfe sollen als POI-Kandidat weiterhin grundsätzlich möglich bleiben ("ich
  möchte mir die Bahnhöfe angucken [können], das ist ja nicht zielführend [sie pauschal
  auszuschließen]"), das eigentliche Problem war unklar genug, um es NICHT jetzt zu "fixen"
  ("lass es einfach so, wie's vorher war"). `_AUSGESCHLOSSENE_PLACE_TYPES` und die zugehörige
  Filterung in `suche_pois` daher wieder vollständig entfernt, der zugehörige Test ebenfalls
  gelöscht. Bleibt als offener Punkt (siehe unten) – das ursprünglich gemeldete Symptom ("An- und
  Abreise"-Karten am ersten/letzten Tag) ist damit NICHT behoben, nur die zu pauschale Lösung dafür
  wieder zurückgenommen.
- Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) – Hinreise-
  /Rückreise-Link zeigt jetzt korrekt auf die Unterkunft-Koordinaten statt nur die Stadt.
- Tests: 1 neuer Test (`test_reiseplan.py`: präzise Hin-/Rückreise-Link-Bevorzugung) + 1 bestehender
  Test an das neue, präzisere Verhalten angepasst (der Bahnhof-Ausschluss-Test aus
  `test_google_maps.py` wurde mit dem Nachtrag oben wieder entfernt). Komplette Suite: 250/250 grün
  (249 + 1 neuer).

## Phase 39 — Debug-Ausgabe bei JEDER echten Planung, Ablage in protokolle/ statt nur pruefe_planung.py (13.08.2026)

- **Was:** Die Planungs-Debug-Ausgabe (Phase 36: rohe/gefilterte/an Optimierung 1 weitergegebene
  POIs, Optimierung-1- und Monte-Carlo-Härtetest-Eingabe/-Ergebnis) lief bisher NUR über
  `pruefe_planung.py`, mit optionalem `debug_sammlung`-Parameter an `plane_reise`. Jetzt: `plane_
  reise` erzeugt IMMER eine `PlanungsDebugSammlung` (kein optionaler Parameter mehr, dritter
  Rückgabewert: `plan, nudge, debug_sammlung = plane_reise(...)`) – die Sammlung kostet praktisch
  nichts (nur Referenzen auf ohnehin berechnete Daten). `agent_tools.py::plane_reise_und_
  abschliessen` (der TATSÄCHLICHE Pfad für chat.py/webapp.py) schreibt sie jetzt bei JEDEM
  Planungsversuch (auch einem an der Barrierefreiheit gescheiterten ersten Versuch, zur
  Fehlersuche) als `<protokoll_stem>_debug.txt` NEBEN das Sitzungsprotokoll – in `protokolle/`, NUR
  wenn ein `Protokollierer` gesetzt ist (in Tests ohne Protokollierer: kein Absturz, kein Schreiben).
  `pruefe_planung.py` schreibt seine Debug-Datei jetzt ebenfalls nach `protokolle/planung_
  <testfall>_debug.txt` statt nach `ergebnisse/` – EIN einheitlicher Ort unabhängig vom
  Einstiegspunkt.
- **Warum:** Nutzerfrage: "wo kann ich sehen, welche Ein-/Ausgaben an Optimierung 1/Monte-Carlo
  gingen?" – Antwort war bisher "nur über pruefe_planung.py". Nutzerwunsch danach: das soll auch
  beim Testen über den echten Dialog (Chat/Web) automatisch entstehen, UND in `protokolle/` liegen,
  NICHT in `ergebnisse/`/einem reinen Test-Ordner – Begründung: `pruefe_planung.py` selbst gilt als
  Test-Werkzeug, das beim finalen Code-Extrakt für die Abgabe eher rausfliegt ("diese ganzen
  Testdinger, die nehmen wir am Ende alle raus"), die Debug-Ausgabe UND das Sitzungsprotokoll
  (`protokolle/`) sollen dagegen als nachvollziehbarer, bleibender Bestandteil der echten
  Anwendung erhalten bleiben.
- Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`) – Debug-
  Datei landet jetzt korrekt in `protokolle/`.
- Tests: 2 neue Tests in `test_agent_tools.py` (Debug-Datei entsteht neben dem Protokoll, wenn ein
  Protokollierer gesetzt ist; kein Absturz/keine Datei ohne Protokollierer), 3 bestehende Mocks auf
  das neue 3-Tupel angepasst. Komplette Suite: 252/252 grün (250 + 2 neue).

## Phase 40 — Monte-Carlo-Härtetest komplett umgestellt: nicht mehr POI-Vor-Ort-Route, sondern An-/Abreise-Umstiege (16.08.2026)

Ausgelöst durch eine genaue Prüfung der Beispiel-Ausgabe (siehe Phase-40-Vorlauf: `pruefe_algorithmus.py`
wurde auf Nutzerwunsch gebaut, um Ein-/Ausgabe von Optimierung 1 UND Härtetest an einem
handverlesenen, von Hand nachrechenbaren Beispiel jedes einzelne Datenfeld zu zeigen). Beim
Durchsehen der Reisezeiten-Matrix fiel dem Nutzer auf: der Härtetest lief bisher auf den POI-zu-POI-
Bewegungen VOR ORT (Tagesroute) – dort ist die Verpassgefahr durch ein paar Minuten Fußweg/Fahrrad
zwischen zwei Sehenswürdigkeiten praktisch irrelevant ("das bringt ja eigentlich gar nix"). Der
eigentlich riskante Teil einer Reise sind reale Bus-/Bahn-UMSTIEGE bei der An-/Abreise: "Was ist,
wenn dieser Bus fünf Minuten Verspätung hat, bekomme ich dann noch die Bahn?"

- **Was:** Der komplette bisherige POI-basierte Härtetest (`monte_carlo.py::haertetest`,
  `_instanz_mit_gestoerten_fahrzeiten`) wurde entfernt, NICHT parallel weitergeführt ("für die POIs
  wird dieser Test abgeschafft, den machen wir da nicht mehr"). Neue Funktion `monte_carlo.py::
  haertetest_teilstrecken(teilstrecken, ...)` simuliert stattdessen die `Teilstrecke`-Kette (siehe
  `typen.py`, von `google_maps.py::_teilstrecken_aus_steps` aus echten Google-Directions-Schritten
  befüllt – dieselben Daten, die für die Umstiegsanzeige ohnehin schon abgerufen werden, kein neuer
  API-Aufruf): jede Teilstrecken-Dauer wird log-normal gestreut (unverändertes Verfahren/Parameter
  aus dem alten Härtetest übernommen), und bei jedem TRANSIT-Umstieg MIT bekanntem
  `wartezeit_minuten`-Puffer wird geprüft, ob die bis dahin aufgelaufene Verspätung noch hineinpasst.
  Reicht der Puffer nicht, gilt der Lauf als Verletzung (einfaches binäres Modell: verpasster
  Anschluss = gescheiterter Lauf, KEINE Prüfung auf eine mögliche spätere Ersatzverbindung, siehe
  Warum unten). `pipeline.py::plane_reise` ruft den Härtetest jetzt NUR für Hinreise/Rückreise auf
  (`bewertete[0].alternative.teilstrecken`) und NUR, wenn `teilstrecken` nicht leer ist – bei Auto
  oder falls Google keine Schritt-Details lieferte bleibt es bei `None` statt eines erfundenen
  Ergebnisses (Grundprinzip 1). `Reiseplan.robustheit` wurde durch zwei getrennte Felder
  `hinreise_robustheit`/`rueckreise_robustheit` ersetzt (beide aktuell aus derselben Alternative
  berechnet, da Hin-/Rückreise in diesem Prototyp bereits an anderer Stelle dieselbe
  `BewerteteAlternative` teilen – keine unabhängige Rückreise-Suche). `als_text`/`als_html` zeigen
  beide Ergebnisse als "Verbindungssicherheit Hinreise/Rückreise: X% ... (robust/NICHT robust)".
  `src/ausgabe/debug.py` (`PlanungsDebugSammlung`, Abschnitt 5 der Debug-Datei) zeigt jetzt für beide
  Richtungen die vollständige Teilstrecken-Kette (Linie, von/nach, Dauer, Umstiegspuffer) statt der
  alten TOPTW-Instanz/Tagesroute. `pruefe_algorithmus.py` demonstriert den neuen Härtetest an einem
  eigenständigen, handverlesenen Beispiel (Bus → Regionalbahn → ICE über einen fiktiven
  "Nordhafen") – bewusst getrennt vom Optimierung-1-POI-Beispiel, weil beide Algorithmen in der
  echten Pipeline ebenfalls unterschiedliche Daten bekommen.
- **Warum (drei Rückfrage-Runden, siehe Gesprächsverlauf):** (1) Erster eigener Vorschlag (Härtetest
  zusätzlich zum bestehenden, mit "trotz verpasstem Anschluss doch noch ankommen"-Logik) war falsch
  verstanden – Nutzer stellte klar: der POI-Test wird ERSETZT, nicht ergänzt, und läuft nur bei
  Bahn/Fernbus (bei Auto irrelevant). (2) Die Idee, bei einem verpassten Anschluss zu prüfen, ob eine
  SPÄTERE Verbindung noch rechtzeitig käme, wurde vom Nutzer selbst wieder verworfen, nachdem klar
  wurde, dass dafür Daten fehlen, die der Härtetest gar nicht bekommt (er sieht nur die bereits vom
  Bot abgerufenen Teilstrecken, keine Fahrplan-Alternativen) – "sonst müssten wir wieder Daten
  abprüfen, und das will ich nicht". Ergebnis: einfaches binäres Modell, kein zusätzlicher
  API-Aufruf, keine Rückfrage-Logik im Härtetest selbst.
- **Nebenbefund (dokumentiert, NICHT behoben):** Beim manuellen Nachrechnen des
  `pruefe_algorithmus.py`-Optimierung-1-Beispiels wurde eine strukturelle Schwäche der ILS-
  Reparaturschritt-Logik in `toptw.py::iterated_local_search` gefunden – nach einem `_shake()`
  werden reparierte POIs IMMER hinter den unveränderten Präfix angehängt
  (`kombinierte_reihenfolge = reduzierte_reihenfolge + [...repariert...]`), nie an einer Position
  davor/dazwischen versucht. Für das 4-POI-Beispiel (Museum/Aussichtspunkt/Park/Café, 240-Min.-
  Budget) findet der Algorithmus dadurch Café→Park→Aussichtspunkt (Score 13), obwohl
  Café→Museum→Aussichtspunkt (Score 15, 235/240 Min., per `simuliere_route()` verifiziert) ebenfalls
  gültig und besser wäre. Nicht Teil dieser Phase (Nutzer hat die Aufmerksamkeit bewusst auf die
  Monte-Carlo-Umstellung gelenkt statt auf einen ILS-Fix) – bleibt offener Punkt.
- Live gegen die echte Google API smoke-getestet (`pruefe_planung.py smoketest_etappen`): Hinreise
  und Rückreise (jeweils EIN direkter S4-Umstieg ohne Zwischenhalt) laufen beide zu 100 % robust
  durch den neuen Härtetest, Debug-Datei zeigt Abschnitt 5 korrekt in zwei Teilen (Hinreise/
  Rückreise, jeweils Teilstrecken-Liste + Ergebnis).
- Tests: `test_monte_carlo.py` komplett neu (5 Tests: Quote in [0,1], großzügiger Puffer robust,
  Puffer 0 erkennt tatsächlich Verletzungen – Fortsetzung des früheren Beweises, dass der
  Mechanismus nicht immer "robust" meldet –, Teilstrecke ohne Wartezeit ist kein Prüfpunkt, leere
  Liste ist robust). `test_debug.py`, `test_reiseplan.py`, `test_agent_tools.py`, `test_fotos.py` an
  die neuen `Reiseplan`-/`PlanungsDebugSammlung`-Felder angepasst. Komplette Suite: 254/254 grün.

## Phase 41 — Barrierefreiheit LLM-beurteilt statt Schlüsselwort-Suche, geführte Touren, Restaurants raus aus Optimierung 1 (17.08.2026)

Drei Rückmeldungen aus einem echten Live-Test (Berlin, Familie mit zwei Kindern, F04
`reiseleitung_gewuenscht=true` beantwortet, `aktivitaeten_interessen=["Sehenswürdigkeiten",
"Restaurants"]`): Tag 3 blieb komplett leer, obwohl eine Führung gewünscht war; ein gewünschtes
Abendessen mit der Familie wurde als normaler POI behandelt und von Optimierung 1 komplett
aussortiert; zusätzlich beim Nachdenken über die Reisetempo-Frage (F10) aufgefallen: das LLM bekam
nie mitgeteilt, welche Wörter die bisherige Barrierefreiheits-Keyword-Suche überhaupt auslösen.

- **Was (Barrierefreiheit/Reisetempo, F09/F10/F15):** `schema.py::barrierefreiheit_oder_
  eingeschraenkt()` durchsuchte bisher drei Freitextfelder nach ~13 festen Wörtern
  ("barrierefrei"/"rollstuhl"/... ) – dem LLM war diese Liste nirgends bekannt, eine sinngemäße,
  aber nicht wörtliche Antwort ("wegen der Kinder lieber gemütlich") lief unbemerkt ins Leere.
  Analog zu F11 (`sicherheit_bedenklich`) ERSETZT: neues Feld `ReiseAnfrage.barrierefreiheit_
  bedenklich: bool`, vom LLM per Tool-Argument bei `speichere_feld` gesetzt, wenn es aus dem
  GESAMTEN Gesprächskontext eine Mobilitätseinschränkung erkennt – NICHT auf ein Feld beschränkt
  (kann bei jedem `speichere_feld`-Aufruf gesetzt werden, bleibt einmal gesetzt bestehen).
  `barrierefreiheit_oder_eingeschraenkt()` liefert jetzt nur noch dieses Flag; alle downstream
  Effekte (Geschwindigkeit/Pausen/Nähe-Gewichtung, harter POI-/Unterkunft-Ausschluss) bleiben
  UNVERÄNDERT deterministisch (Grundprinzip 3) – nur die Erkennung selbst liegt jetzt beim LLM.
  `katalog.py` (F09/F10/F15) weist das LLM in den `kontext_hinweis`-Texten explizit darauf hin.
- **Was (geführte Touren):** Erster eigener Vorschlag (F04 deterministisch verdrahten, löst
  automatisch eine Tour-Suche aus) wurde vom Nutzer ausdrücklich abgelehnt: *"Ich möchte nicht,
  dass es deterministisch verdrahtet ist. Ich möchte, dass an die LLM mit übergeben wird: Wenn
  eine spezifische Tour... gewünscht ist, dann soll eine Tourensuche über die Google API
  angestoßen werden."* Umgesetzt als reine `kontext_hinweis`-Ergänzung in `katalog.py` (F04 UND
  F16): das LLM wird angewiesen, bei erkanntem Reiseleitungs-/Tour-Wunsch SELBST einen konkreten
  Suchbegriff (z. B. "geführte Tour") in `aktivitaeten_interessen` aufzunehmen – dieselbe
  bestehende, unveränderte `suche_pois`-Freitextsuche wie für jedes andere Interesse, KEIN neuer
  Mechanismus in `pipeline.py`. Zusätzlich (unabhängig von der Trigger-Frage, betrifft JEDEN nicht
  eingeplanten Kandidaten generisch): ein Tag ohne eingeplantes Programm zeigt jetzt 2–3 der
  gefundenen, aber von Optimierung 1 nicht platzierten Kandidaten aus `weitere_aktivitaeten_
  empfehlungen` statt nur "kein Programm eingeplant" (`reiseplan.py::_verteile_beispiele_auf_
  leere_tage`, verteilt ohne Wiederholung über mehrere leere Tage, entfernt gezeigte POIs aus der
  allgemeinen "Weitere Empfehlungen"-Liste, damit nichts doppelt auftaucht).
- **Was (Restaurants raus aus Optimierung 1):** Ursprünglicher Vorschlag (Restaurant fest an
  Tagesende anhängen) wurde vom Nutzer noch im selben Gespräch revidiert: *"Ich möchte nicht, dass
  das als gesondertes POI gesehen wird... es soll gar nicht in diesen Tagesplan integriert sein...
  einfach Beispielrestaurants in der Nähe von der Unterkunft."* Neue Funktion `pipeline.py::
  _trenne_beispielrestaurants_ab`: essensbezogene Treffer (`POI.besuchsklasse == "mahlzeit"`)
  werden VOR Optimierung 1 aus der Kandidatenliste entfernt (konkurrieren nicht mehr um Zeitfenster/
  Score, können also nicht mehr komplett verlieren), stattdessen nach Entfernung zur bestätigten
  Unterkunft sortiert und als neues Feld `Reiseplan.beispielrestaurants` zurückgegeben. Cafés/Bars
  (besuchsklasse "kaffee"/"bar") sind NICHT betroffen, bleiben normale Kandidaten. Anzeige je Tag
  (`reiseplan.py::_restaurants_fuer_tag`, rotierender 3er-Ausschnitt aus dem gemeinsamen Pool, damit
  nicht überall dieselben Namen stehen) – unabhängig davon, ob der Tag sonst ein Programm hat.
- Live gegen die echte Google API smoke-getestet (eigener Testfall mit den Interessen
  `["Museum", "Restaurants", "geführte Tour"]`): die Tour-Suche fand reale Anbieter (u. a.
  "Stattreisen Hannover e.V.", "Stadttouren Hannover"), die sogar direkt in Tag 1 eingeplant
  wurden; beide Tage zeigten unterschiedliche, echte "Beispielrestaurants in der Nähe der
  Unterkunft"; kein Restaurant tauchte in der normalen Tagesroute oder doppelt in "Weitere
  Empfehlungen" auf.
- Tests: neue Tests in `test_fragekatalog.py`/`test_agent_tools.py` (Flag-Default, LLM-Tool-
  Argument wirkt bei beliebigem Feld), bestehende Barrierefreiheit-Tests in `test_aufbereitung.py`/
  `test_vertraeglichkeit.py`/`test_vorschlaege.py` auf das neue Flag umgestellt, neue Tests in
  `test_pipeline.py` (`_trenne_beispielrestaurants_ab`: entfernt Mahlzeiten, lässt Café/Bar
  unangetastet, sortiert nach Entfernung) und `test_reiseplan.py` (leere Tage zeigen Beispiele ohne
  Duplikat, Beispielrestaurants werden angezeigt). Komplette Suite: 264/264 grün.
- Nebenfrage beantwortet, NICHT umgesetzt: echte Hotelpreise (statt Preisniveau-Schätzung)
  bräuchten eine GESONDERTE Hotel-/OTA-Preis-API (z. B. wieder Hotelbeds) – die auf Google Maps
  sichtbaren Booking/Hostelworld-Preise stammen aus Google Hotel Ads, einem getrennten
  Partnerprodukt, das über den normalen `GOOGLE_MAPS_API_KEY` nicht erreichbar ist. Offener Punkt,
  Anbieter-Entscheidung steht noch aus.

## Phase 42 — Barrierefreiheit in drei Stufen statt einem Bool (17.08.2026)

Direkte Rückfrage nach Phase 41: *"Bei Barrierefreiheit sollte es aber verschiedene Stufen geben...
jemand, der einfach nur ein bisschen langsamer geht als jemand, der im Rollstuhl ist, das sind
Unterschiede."* Auf Bitte des Nutzers zuerst eine Recherche, WELCHE Stufen sich anhand ECHTER
verfügbarer Daten überhaupt sinnvoll unterscheiden lassen (keine erfundene Steigungs-/
Stufen-Erkennung, Grundprinzip 1) – Ergebnis: die einzige strukturierte Barrierefreiheits-Quelle
ist weiterhin `wheelchair_accessible_entrance` (Google Places), es gibt KEINE Steigungs-/
Terrain-Daten für einzelne Orte oder Fußwege (weder Places noch Directions noch eine angebundene
Elevation-API). Drei mit dieser einen Datenquelle ehrlich unterscheidbare Stufen wurden dem Nutzer
vorgeschlagen und bestätigt ("sehr gut"):

- **Was:** `ReiseAnfrage.barrierefreiheit_bedenklich: bool` (Phase 41) ERSETZT durch `mobilitaets
  einschraenkung_stufe: str | None` mit drei Werten, vom LLM per Tool-Argument bei `speichere_feld`
  gesetzt (überschreibbar, nicht mehr nur einmal-True-setzbar – die Stufe kann im Gespräch
  verfeinert werden, z.B. "leicht" -> "stark", wenn sich ein Rollstuhlbedarf erst später
  herausstellt):
  - `"leicht"` (z.B. altersbedingt langsameres Tempo): JEDER Ort bleibt nutzbar, KEIN POI-/
    Unterkunft-Ausschluss – nur die bestehenden Tempo-/Pausen-/Nähe-Anpassungen (aufbereitung.py,
    unverändert).
  - `"mittel"` (z.B. Krücken/Gehhilfe): zusätzlich werden Orte ausgeschlossen, die EXPLIZIT als
    nicht barrierefrei bestätigt sind – unbekannte bleiben (bisheriges Standardverhalten aus
    Phase 18/32/41, jetzt nur noch für diese Stufe).
  - `"stark"` (z.B. Rollstuhl): nur EINDEUTIG bestätigt barrierefreie Orte/Unterkünfte gelten als
    unbedenklich – ein unbekannter Status zählt hier ZUSÄTZLICH als Ausschlussgrund (neu).
  Umgesetzt in `vertraeglichkeit.py::_barrierefreiheits_kriterium` (gemeinsame Konflikt-Logik für
  `filtere_pois_hart`/`filtere_unterkuenfte_barrierefrei`/`pruefe_barrierefreiheit_des_plans` –
  Letztere bekommt dafür einen neuen Parameter `mobilitaetseinschraenkung_stufe`). `katalog.py`
  (F09/F10/F15) weist das LLM in den `kontext_hinweis`-Texten auf die drei Stufen hin.
- Live gegen die echte Google API smoke-getestet (Testfall mit `gesundheitliche_einschraenkungen:
  "Rollstuhlfahrer"`, `mobilitaetseinschraenkung_stufe: "stark"`): ein Museum mit unbekanntem
  Barrierefreiheits-Status ("KUNSTHAUS HANNOVER") wurde korrekt als NICHT eindeutig bestätigt
  erkannt (Warnhinweis, da einziger Treffer der Kategorie); Tempo/Pausen griffen wie erwartet
  (20-Minuten-Pausen im Plan sichtbar).
- Tests: bestehende Barrierefreiheit-Tests in `test_vertraeglichkeit.py`/`test_aufbereitung.py`/
  `test_vorschlaege.py`/`test_fragekatalog.py`/`test_agent_tools.py` auf die drei Stufen umgestellt,
  neue Tests je Stufe (leicht = keine Filterung, mittel = nur explizit bestätigt ausgeschlossen,
  stark = auch unbekannter Status ausgeschlossen) inkl. `pruefe_barrierefreiheit_des_plans` mit
  neuem Parameter. Komplette Suite: 271/271 grün.

## Phase 43 — Flexibilitätspräferenz als LLM-beurteilte 1-5-Skala statt Schlüsselwort-Zählung (17.08.2026)

Direkte Anschlussfrage nach Phase 42 (Barrierefreiheits-Stufen): F05 (`flexibilitaet_praeferenz`)
wurde zwar abgefragt, aber der bisherige `max_pois_pro_tag_fuer_flexibilitaet` zählte nur
Schlüsselwörter ("flexibel"/"spontan" vs. "fest"/"durchgeplant") und wirkte sich AUSSCHLIESSLICH
auf die reine Anzahl POIs pro Tag aus – keine Wirkung auf die zeitliche Verteilung INNERHALB des
Tages. Nutzerwunsch: ein "flexibler" Tag soll nicht nur weniger Stopps haben, sondern auch
zwischendrin echten Freiraum bieten (z.B. für spontanen Kaffee/Kuchen), nicht nur unstrukturierte
Restzeit am Tagesende.

- **Was:** `ReiseAnfrage.flexibilitaet_praeferenz` (Freitext, bleibt als reiner Gesprächskontext
  bestehen) bekommt ein neues Geschwister-Feld `flexibilitaet_stufe: int | None` (1-5), vom LLM per
  Tool-Argument bei `speichere_feld` gesetzt – ausdrücklicher Nutzerwunsch: *"Der soll jetzt nicht
  genau fragen, wie flexibel wollen Sie von eins bis fünf sein, sondern er soll die Konversation
  führen und dann aus dieser Konversation schließen, was für ein Rating das sein sollte."*
  Überschreibbar (kann im Gesprächsverlauf verfeinert werden), analog zu `mobilitaetseinschraenkung_
  stufe` (Phase 42). ERSETZT die frühere Schlüsselwort-Zählung vollständig.
  Zwei Hebel je Stufe (`aufbereitung.py`, Tabelle mit dem Nutzer abgestimmt und bestätigt):
  | Stufe | max_pois_pro_tag | Pufferpause |
  |---|---|---|
  | 1 (ganz durchgeplant) | kein Deckel | keine |
  | 2 | 6 | keine |
  | 3 | 5 | alle 3h, 15 Min. |
  | 4 | 3 | alle 2,5h, 20 Min. |
  | 5 (extrem flexibel) | 2 | alle 1,5h, 30 Min. |
  Die Pufferpause nutzt denselben Mechanismus wie die Barrierefreiheits-Pause
  (`TOPTWInstanz.pause_intervall_minuten`/`pause_dauer_minuten`, siehe Phase 18/32) – treffen beide
  gleichzeitig zu, gewinnt das KÜRZERE Intervall (`erstelle_toptw_instanz`), eine nötige
  Barrierefreiheits-Pause wird nie durch eine niedrige Flexibilitätsstufe verdrängt.
  `katalog.py` (F05) weist das LLM in `kontext_hinweis` explizit an, NICHT direkt nach einer Zahl zu
  fragen, sondern aus dem gesamten Gesprächsverlauf zu schließen.
- **Prozess-Hinweis:** Für diese eine Änderung wurde KEIN `doku/`-Code-Stand-Snapshot vor der
  Umsetzung angelegt (Implementierung begann direkt nach der Bestätigung der Tabelle) – analog zur
  bereits in Phase 32 dokumentierten Ausnahme. Nachträglich transparent vermerkt statt verschwiegen.
- Live gegen die echte Google API smoke-getestet (`flexibilitaet_stufe: 5`): Optimierung 1 plante
  korrekt genau 2 POIs pro Tag (Deckel greift).
- Tests: `test_aufbereitung.py` – alte Schlüsselwort-Tests durch stufenweise Tests ersetzt (Deckel
  je Stufe 1-5, Pufferpause je Stufe, Kombination mit Barrierefreiheits-Pause nimmt das kürzere
  Intervall). Komplette Suite: 273/273 grün.

## Phase 44 — Geführte Touren: eigener reservierter Tag statt Optimierung 1, Performance-Fix (17.08.2026)

Live-Vorfall in der Web-Oberfläche: der Chat blieb bei einer echten Anfrage (Rollstuhl,
"geführte Tour" + "Restaurants" + "Sehenswürdigkeiten" als Interessen) sichtbar hängen. Diagnose
über das echte Sitzungsprotokoll (`protokolle/web_2026-08-17_131043.jsonl`): der letzte Eintrag war
`hole_api_daten(aktivitaeten_interessen)` mit drei Interessen, danach kein Ergebnis mehr. Ursache:
`mobilitaetseinschraenkung_stufe="stark"` (Phase 42) löst in `filtere_pois_hart` für JEDEN
Roh-Treffer einen eigenen, echten Google-Places-Details-Aufruf aus – durch die neue dritte Suche
("geführte Tour", erst seit Phase 41 wirksam) stieg die Roh-Trefferzahl auf ~60, macht ~60
sequenzielle API-Aufrufe.

- **Was:** Nutzerwunsch (direkt im Anschluss an die Diagnose): geführte Touren laufen NIE durch
  Optimierung 1 (analog zu Restaurants, Phase 41) UND werden VOR jeder teuren Prüfung auf einen
  kleinen Pool begrenzt. Konkret:
  - Neue Erkennung `google_maps.py::ist_tour_bezogenes_interesse` (Schlüsselwörter "tour"/
    "führung"/"guide"/"sightseeing" im `POI.nutzerinteresse`, analog zu `_ist_essen_bezogenes_
    interesse`) – Google liefert dafür keinen eigenen Place-Type.
  - Neue Funktion `pipeline.py::_trenne_tour_beispiele_ab`: trennt Tour-Treffer VOR `filtere_pois_
    hart` ab (Performance – die teure Barrierefreiheits-Prüfung läuft dadurch NIE auf allen
    Roh-Treffern), begrenzt auf `_TOUR_KANDIDATEN_POOL = 8` nächstgelegene zur Unterkunft (statt
    alle Roh-Treffer einzeln zu prüfen), wählt daraus `_TOUR_BEISPIELE_ANZAHL = 3` aus – OHNE
    Score/Ranking ("da wird auch nicht mal eine Auswahl getroffen").
  - Barrierefreiheits-Anforderung an die 3 gezeigten Touren, gestaffelt nach
    `mobilitaetseinschraenkung_stufe` (Rückfrage-Ergebnis, dieselbe Stufe wie überall sonst –
    *"das muss an beide Algorithmen gehen, das muss die KI wissen und das muss genauso auch der
    Optimierungsalgorithmus wissen"*): "leicht"/None keine Prüfung; "mittel" mindestens die Hälfte
    (aufgerundet) eindeutig bestätigt barrierefrei; "stark" ALLE eindeutig bestätigt barrierefrei –
    reicht der Pool nicht aus, werden ehrlich weniger als 3 gezeigt statt eine unbestätigte Tour zu
    erfinden (Grundprinzip 1).
  - Werden Touren gefunden, wird EIN kompletter Tag (bewusst der LETZTE, einfachste
    vorhersehbare Regel) komplett aus Optimierung 1 herausgenommen (`erstelle_toptw_instanz` bekommt
    dafür einen neuen Parameter `anzahl_tage_override`, `pipeline.py` reduziert `tagesbudget_je_tag`
    entsprechend) – dieser Tag bekommt KEIN optimiertes Programm, sondern die 3 Touren werden direkt
    eingetragen (`Reiseplan.tour_tag_beispiele`, neues Feld, in `reiseplan.py` für den letzten Tag
    bevorzugt vor dem generischen "leerer Tag zeigt Beispiele"-Fallback aus Phase 41 gerendert).
- **Prozess-Hinweis:** Auch für diese Änderung wurde KEIN `doku/`-Code-Stand-Snapshot vor der
  Umsetzung angelegt (direkte Weiterarbeit während der laufenden Diagnose) – wie bei Phase 32/43
  transparent vermerkt statt verschwiegen.
- Live gegen die echte Google API smoke-getestet (dieselbe Kombination wie beim Live-Vorfall,
  `mobilitaetseinschraenkung_stufe: "stark"`, 3 Interessen inkl. "geführte Tour"): Laufzeit sank von
  "hängt sich sichtbar auf" auf ca. 37 Sekunden – Tag 3 zeigt korrekt 2 gefundene, eindeutig
  bestätigt barrierefreie Touren (ehrlich weniger als 3, da der Pool nicht mehr hergab), keine
  Tour taucht in Tag 1/2 oder doppelt in "Weitere Empfehlungen" auf. Die verbleibende Laufzeit
  stammt von der UNVERÄNDERTEN Barrierefreiheits-Prüfung der normalen Sehenswürdigkeiten-Kandidaten
  (kein Bestandteil dieser Phase, siehe Offene Punkte).
- Tests: neue Tests in `test_pipeline.py` (`_trenne_tour_beispiele_ab`: Abtrennung, Pool-Begrenzung,
  alle drei Barrierefreiheits-Stufen), `test_aufbereitung.py` (`anzahl_tage_override`),
  `test_reiseplan.py` (reservierter Tag zeigt Touren statt "kein Programm eingeplant", keine
  Dopplung mit "Weitere Empfehlungen"). Komplette Suite: 284/284 grün.

## Phase 45 — Monte-Carlo-Härtetest-Schwelle von 95% auf 80% gesenkt (17.08.2026)

Direkte Anweisung des Product Owners: die bisherige `schwelle=0.95` in `monte_carlo.py::
haertetest_teilstrecken` (dokumentiert als "begründeter erster Vorschlag, vor der finalen
Auswertung zu bestätigen", siehe Phase 40) war zu streng – ein Lauf gilt jetzt bereits ab
`quote_ohne_verletzung > 0.80` als robust, nicht erst ab > 0.95.

- **Was:** Default-Parameter `schwelle: float = 0.95` -> `0.80` in `monte_carlo.py::
  haertetest_teilstrecken` (Zeile 39, einzige Stelle, die den Wert tatsächlich bestimmt –
  `pipeline.py::plane_reise` ruft die Funktion ohne expliziten `schwelle`-Wert auf, übernimmt also
  automatisch den neuen Default). `pruefe_algorithmus.py`s `SCHWELLE`-Konstante ebenfalls auf `0.80`
  angepasst, damit das Demo-Skript weiterhin denselben Wert wie die echte Pipeline zeigt.
- Bestehende Tests waren davon nicht betroffen (`test_debug.py` konstruiert `RobustheitsErgebnis`
  direkt mit einem literalen `schwelle=0.95`, unabhängig vom Funktions-Default). Komplette Suite
  weiterhin grün (287/287, siehe Phase 46 unten für den finalen Stand).

## Phase 46 — Lernaktivitäten (F17): konkrete Kurse wie geführte Touren behandelt, unkonkrete Antworten bekommen eine Empfehlung (17.08.2026)

Nutzerfrage: "Was macht der Code, wenn ich angebe, ich möchte auf der Reise etwas lernen?" – Antwort
nach Recherche: `lernaktivitaeten_interesse` (F17) war ein TOTES Feld, exakt derselbe Zustand wie
`reiseleitung_gewuenscht` vor dessen Verdrahtung (Phase 41) – wird abgefragt, gespeichert, aber
nirgends ausgewertet. Auf Bitte des Product Owners erst ein Konzept für mögliche Antwortkategorien
erarbeitet, dann per Rückfragen (`AskUserQuestion`) bestätigt, dann umgesetzt.

- **Was (Bucket A – konkrete, ortsgebundene Aktivität, z.B. "Kochkurs"):** Genau wie geführte Touren
  behandelt (Rückfrage-Ergebnis, ausdrücklich bestätigt: *"das möchte ich auf jeden Fall lernen"*
  darf NIE vom Optimierungsalgorithmus aussortiert werden können – dasselbe Argument wie bei
  Touren). Die bisherige `pipeline.py::_trenne_tour_beispiele_ab` wurde dafür zu `_trenne_
  sonderkategorie_ab` verallgemeinert (nimmt jetzt ein `gehoert_zur_kategorie`-Prädikat als
  Parameter statt fest auf Touren zu prüfen) – dieselbe Pool-Begrenzung (8 nächstgelegene),
  Beispielanzahl (3, ohne Score/Auswahl) und Barrierefreiheits-Staffelung (leicht: keine Prüfung;
  mittel: mind. Hälfte bestätigt barrierefrei; stark: alle bestätigt) gilt jetzt für BEIDE
  Kategorien. Neue Erkennung `google_maps.py::ist_lernaktivitaet_bezogenes_interesse`
  (Schlüsselwörter "kurs"/"workshop"/"seminar"/"unterricht"). `katalog.py` F16/F17 weisen das LLM
  an, bei einer konkreten Aktivität selbst einen Suchbegriff in `aktivitaeten_interessen`
  aufzunehmen (dasselbe Muster wie bei F04/F16 für Touren).
  Werden BEIDE Kategorien gefunden (Tour UND Lernaktivität), werden ZWEI GETRENNTE Tage reserviert
  (Rückfrage bestätigt, nicht ein gemeinsamer Tag) – `reiseplan.py::_reservierte_sondertage` ordnet
  die reservierten Tage den letzten Tagen der Reise zu (Tour zuerst, dann Lernaktivität, muss zur
  Reihenfolge in `pipeline.py` passen). Neues Feld `Reiseplan.lernaktivitaet_tag_beispiele`.
- **Was (Bucket B – unkonkrete Aussage, z.B. "ich möchte offen sein und dazulernen"):** Keine echten
  Daten zu suchen (Grundprinzip 1) – aber das LLM soll NICHT einfach stumm weitergehen. `katalog.py`
  F17 weist das LLM an, eine kurze, allgemeine Empfehlung zu geben (Rückfrage bestätigt: bekannte,
  real existierende Angebote wie "Duolingo" dürfen beim Namen genannt werden, KEINE erfundenen oder
  unsicheren Fakten über den konkreten Zielort selbst) – reine Gesprächsebene, kein Tool-Aufruf,
  keine Pipeline-Änderung.
- **Prozess-Hinweis (Doku-Format, eigene Rückfrage):** Product Owner wollte KEIN neues, separates
  Dokument für "Konzepte je Frage" (Sorge: "ich möchte nicht hundert Dokudateien haben"). Auflösung:
  CLAUDE.md ist bereits das lebende, stets aktuelle Dokument für den JETZT-Zustand (wird diese
  Sitzung laufend mitgepflegt), ENTSCHEIDUNGSLOG.md bleibt bewusst das unveränderliche,
  chronologische WARUM – kein drittes Dokument nötig.
- Live gegen die echte Google API smoke-getestet (Interessen `["Museum", "geführte Tour",
  "Kochkurs"]`, 4-Tage-Reise): Tag 1+2 normal optimiert, Tag 3 zeigt 3 echte Tour-Anbieter, Tag 4
  zeigt 3 echte Kochschulen – keine Überschneidung zwischen den beiden reservierten Tagen.
- Tests: `_trenne_tour_beispiele_ab`-Tests in `test_pipeline.py` auf die generalisierte `_trenne_
  sonderkategorie_ab` umgestellt, neuer Test für die Lernaktivitäts-Erkennung getrennt von Touren;
  neue Tests in `test_reiseplan.py` (Lernaktivitäts-Tag statt "kein Programm eingeplant", Tour UND
  Lernaktivität bekommen getrennte Tage). Komplette Suite: 287/287 grün.

## Phase 47 — Lokaler Kontakt (F19): Mittags-Zeitblock für Markt/Café statt totem Feld (17.08.2026)

`lokaler_kontakt_wichtig` (F19) war ein VIERTES totes Feld (nach `reiseleitung_gewuenscht`,
`lernaktivitaeten_interesse`, siehe Phasen 41/46) – abgefragt, gespeichert, nirgends ausgewertet.
Auf Bitte des Product Owners erst konkrete Beispiele erarbeitet ("kannst Du mir Beispiele geben,
was ich für ihn raussuchen kann"), dann ein eigenständiges, nicht 1:1 von Touren/Lernaktivitäten
kopiertes Konzept entwickelt (ausdrücklicher Wunsch: *"wir teilen jetzt nicht alles nach dem
gleichen Konzept, es wirkt sehr unprofessionell"*), dann per Rückfragen bestätigt.

- **Was:** DRITtes, neues Strukturmuster (weder "raus aus Optimierung + eigener Tag" wie bei
  Touren/Lernaktivitäten noch "raus aus Optimierung, keine Tagesbindung" wie bei Restaurants):
  - An "vollen" Tagen (NICHT Anreise-, NICHT Abreisetag – Rückfrage bestätigt) bekommt Optimierung 1
    120 Min. WENIGER Tagesbudget (`pipeline.py::plane_reise`, direkt an `tagesbudget_je_tag`) – der
    Algorithmus lässt den Mittagsblock dadurch von selbst frei, statt ihn mit Sehenswürdigkeiten
    vollzustopfen. Ist der Abreisetag NICHT innerhalb der von Optimierung 1 geplanten Tage (weil ein
    Tour-/Lernaktivitäts-Tag dahinter angehängt wird), zählt JEDER Tag außer Tag 1 als "voll".
  - WELCHER Markt/welches Café konkret reinpasst, entscheidet NICHT der Algorithmus: neue Funktion
    `pipeline.py::_trenne_markt_beispiele_ab` (POIs mit `besuchsklasse == "kaffee"` ODER
    `nutzerinteresse` passend zu neuer Erkennung `google_maps.py::ist_markt_bezogenes_interesse`)
    – 3 echte, nächstgelegene Beispiele je vollem Tag, rotierend (`reiseplan.py::_markt_beispiele_
    fuer_tag`), NICHT an einen bestimmten Tag gebunden.
  - Der bestehende Beispielrestaurants-Mechanismus (Phase 41) wurde ERGÄNZT statt verdoppelt
    (Rückfrage-Ergebnis: *"der Block kann in gewisser Weise mit übernommen werden"*) – `besuchsklasse
    == "bar"` wird jetzt ZUSÄTZLICH zu "mahlzeit" erfasst (eine "urige Kneipe" landet bei Google
    häufig unter "bar", nicht "restaurant"), und `katalog.py` F19 weist das LLM an, bei gewünschtem
    lokalem Kontakt zusätzlich einen Kneipen-Suchbegriff in `aktivitaeten_interessen` aufzunehmen –
    auch ohne separat geäußerten Wunsch nach "abends essen gehen".
  - `pipeline.py::_trenne_sonderkategorie_ab` (Touren/Lernaktivitäten, Phase 44/46) wurde dafür
    generalisiert: das Prädikat prüft jetzt den GANZEN POI (`gehoert_zur_kategorie(poi)`) statt nur
    `poi.nutzerinteresse`, da Café-Erkennung über `besuchsklasse` läuft, nicht über das Interesse.
  - Erkennung bleibt bewusst NUR die Antwort auf F19 selbst (Rückfrage-Ergebnis: "nicht aus dem
    gesamten Gesprächsablauf") – technisch unverändert (die generische `speichere_feld`-Speicherung
    funktionierte bereits, es fehlte nur die Auswertung danach).
  - Geführte Touren/Kochkurse MIT Einheimischen bewusst NICHT hier mit reingenommen – laufen
    weiterhin über die bestehenden F04/F17-Mechanismen (Rückfrage-Ergebnis: *"das lassen wir einfach
    weg"*). Vereine/Community-Zentren ebenfalls bewusst nicht umgesetzt (Rückfrage-Ergebnis: "können
    wir mal rausnehmen").
- **Prozess-Hinweis:** KEIN `doku/`-Code-Stand-Snapshot vor der Umsetzung (wie bei Phase 43/44/46).
- Live gegen die echte Google API smoke-getestet (4-Tage-Reise, `lokaler_kontakt_wichtig: true`):
  Tag 1 (Ankunft) und Tag 4 (Abreise) zeigen korrekt KEINE Markt-Beispiele; Tag 2+3 zeigen je 3
  echte, unterschiedliche Wochenmärkte; die Beispielrestaurants enthalten jetzt echte Kneipen
  ("MacGowan's The Irish Pub" u.a.); Tag 2/3 (reduziertes Budget) planten sichtbar weniger Programm
  (3 Besuche, bis ca. 4h50min) als Tag 1/4 (volles Budget, 5 Besuche, bis 6-7h).
- Tests: `test_pipeline.py` – `_trenne_beispielrestaurants_ab` um Bar-Erfassung erweitert/getestet,
  neue Tests für `_trenne_markt_beispiele_ab` (Markt+Café-Erfassung, Entfernungssortierung) und
  `ist_markt_bezogenes_interesse`, bestehende Sonderkategorie-Tests auf die generalisierte
  POI-Prädikat-Signatur umgestellt. Komplette Suite: 291/291 grün.

## Phase 48 — Fehlerkorrekturen aus einer echten 15-Tage-Testreise: Tagesanzahl, Rückreise, Mehrtages-Touren (17.08.2026)

Nutzer plante eine echte 15-tägige Reise (01.–15. eines Monats, per Datumsbereich statt "X Tage"
angegeben) und meldete mehrere Ungereimtheiten aus dem fertigen Reiseplan. Jeder Punkt einzeln
analysiert/mit Codefundstelle belegt und vor der Umsetzung mit dem Product Owner bestätigt
(wiederholte explizite Rückfrage-Aufforderung: "analysiere den Prompt... frag mich ab").

- **Was (Tagesanzahl-Bug):** `schaetze_reisedauer_tage()` (aufbereitung.py) erkannte nur explizite
  "X Tage"-Formulierungen (`_TAGE_MUSTER`) – ein per Datumsbereich angegebener Zeitraum ("vom 1.
  bis 15.") fiel auf den hartcodierten `standard_tage=5`-Rückfall zurück. Neue Funktion
  `_tage_aus_datumsbereich` erkennt zusätzlich Datumsbereiche (`_DATUM_BEREICH_MUSTER`, z.B.
  "21.8. bis 1.9.") OHNE Jahresangabe (Rückfrage-Ergebnis: "ohne dass man noch 2026 dahinter
  schreiben muss") – fehlt das Jahr, wird ein neutrales Ankerjahr angenommen, ein Enddatum vor dem
  Startdatum gilt als Jahreswechsel-Reise. `max_pois_fuer_reise()` nutzt dieselbe Funktion und war
  damit vom selben Bug betroffen (zu wenige POI-Kandidaten bei falsch erkannter Kurzreise) – mit dem
  Fix automatisch mitbehoben, kein separater Fix nötig.
- **Was (Rückreise-Bug):** `pipeline.py::plane_reise` setzte `rueckreise=bewertete[0]` – buchstäblich
  DASSELBE Objekt wie `hinreise` (eine bewusste, aber laut Nutzer nicht mehr tragbare frühere
  Vereinfachung, siehe Code-Kommentar "keine unabhängige Rückreise-Suche in diesem Prototyp"). Jetzt
  ein ECHTER zweiter `client.reisealternativen(ziel, wohnort)`-Aufruf in umgekehrter Richtung, mit
  eigener Bewertung/Verkehrsmittel-Filterung UND eigenem Monte-Carlo-Härtetest (`rueckreise_
  robustheit`, vorher ebenfalls dupliziert). `kostenschaetzung.py`-Aufruf entsprechend korrigiert
  (nutzte für Rückreise-Kosten ebenfalls die Hinreise-Kosten).
- **Was (Route endet an der Stadt statt am Hotel):** Konkretes Nutzerbeispiel: die angezeigte
  Verbindung endete an "Berlin-Spandau" (grober Zielort-Name), obwohl der separat gebaute
  Google-Maps-Link (`reiseplan.py::_hinreise_ziel_fuer_link`, bereits aus einer früheren Phase) die
  echte Unterkunfts-Adresse zeigte – nur die tatsächliche Routenberechnung (Dauer/Kosten/
  Teilstrecken) war nie bis zur Unterkunft nachgezogen worden. Neue Variable `ziel_fuer_route`
  (`anfrage.unterkunft_koordinaten` als "lat,lng"-String, sobald F15 bestätigt ist, sonst Rückfall
  auf den groben Zielort) wird jetzt für BEIDE Richtungen als Google-Directions-Ziel/-Start
  verwendet.
- **Was (Web-Visualisierung, Nutzerwunsch "alle Reiseelemente sollen hier aufgeführt werden"):**
  `reiseplan.py::als_kartendaten` liefert jetzt zusätzlich `hinreise`/`rueckreise`-Karten (Route-Link,
  Verkehrsmittel, Verbindungssicherheit) sowie ein `vorschlaege`-Feld je Tag (Sondertag-Beispiele,
  Markt-/Café-/Restaurant-Vorschläge, generische Beispiele an leeren Tagen), jeweils mit `label` zur
  klaren Markierung als "nur Vorschlag, nicht Teil der optimierten Route" statt wie eine normale
  Tages-Karte auszusehen. `static/index.html` zeigt Hinreise ganz oben, Unterkunft, dann die
  Tages-Karten (Vorschläge in einem sichtbar umrahmten Block DIREKT NACH den POI-Karten desselben
  Tages), dann Weitere Empfehlungen, Rückreise ganz unten (exakte Reihenfolge vom Product Owner
  bestätigt).
- **Was (Kulinarik-Anzeige-Bug, zweiter Live-Testfund):** Beispielrestaurants/Markt-Café-Vorschläge
  liefen in `als_text`/`als_html` UNCONDITIONAL für JEDEN Tag, auch für reservierte Tour-/
  Lernaktivitäts-Tage ("da ist nur Tour"). Jetzt an einen `if tag_nr not in sondertage:`-Zweig
  gebunden (in beiden Ausgabeformen sowie bereits von Anfang an korrekt in `als_kartendaten`).
- **Was (Mehrtages-Touren, neue Anforderung):** Bisher reservierte eine gefundene Tour-Kategorie
  IMMER genau einen Tag. Neues Feld `ReiseAnfrage.tour_tage_anzahl: int | None` (Tool-Argument bei
  `speichere_feld`, analog `flexibilitaet_stufe`/`mobilitaetseinschraenkung_stufe`) – NUR bei
  EXPLIZITER Mehrtages-Aussage des Nutzers gesetzt (katalog.py F04-Hinweis erweitert), bewusst NICHT
  proaktiv erfragt (Rückfrage-Ergebnis: "ganz einfach halten"). `pipeline.py::plane_reise` reserviert
  entsprechend viele Tage (gedeckelt auf mindestens 1, höchstens `tage` minus Lernaktivitäts-Tag),
  ALLE mit derselben Beispiel-Auswahl (keine künstlich vervielfältigte, echte-Daten-arme Auswahl nur
  um Tage zu füllen). `reiseplan.py::_reservierte_sondertage` ordnet jetzt N aufeinanderfolgende
  Tage der Tour zu statt fest einem – Reihenfolge bestätigt unverändert: Lernaktivität bleibt der
  ALLERLETZTE Tag, die Tour-Tage liegen davor (`Reiseplan.tour_tage_anzahl` neu, damit die Anzahl
  nicht mehr nur implizit aus einer 1-Tag-Annahme folgt).
- Live gegen echte Google-API-Daten smoke-getestet (drei neue `planungs_testfaelle/*.json`, bleiben
  als Regressions-Fixtures im Repo): 15-Tage-Datumsbereich → korrekt 15 Tage statt 5; Hinreise/
  Rückreise mit unterschiedlichen Fahrzeiten/Teilstrecken UND Ziel bis zur echten Unterkunft; 6-Tage-
  Reise mit `tour_tage_anzahl=2` → Tag 5 UND Tag 6 beide "geführte Tour", KEINE Beispielrestaurants
  auf diesen Tagen, während Tag 2–4 sie weiterhin zeigen.
- Tests: neue Tests in `test_aufbereitung.py` (Datumsbereich-Erkennung, inkl. Jahreswechsel/
  ungültigem Datum/Vorrang expliziter Tagesangabe) und `test_reiseplan.py` (Hinreise/Rückreise-
  Karten getrennt, Vorschläge an leeren/vollen/Sonder-Tagen, Kulinarik-Ausschluss an Sondertagen,
  mehrtägige Tour-Reservierung). Komplette Suite: 306/306 grün.

## Phase 49 — Datumsbereich-Bug Teil 2: fehlendes Jahr auf einer Seite ergab ~700-Tage-Phantomreise (17.08.2026)

Erster Live-Test der Phase-48-Datumsbereich-Erkennung (Web-Oberfläche, echte Google API) direkt im
Anschluss: `reisezeitraum_rohtext = "15.09. - 18.09.2026"` (Protokoll `web_2026-08-24_163339.jsonl`)
ergab eine ~700 Tage lange Reise statt der erwarteten 4 Tage. Ursache mit dem exakten protokollierten
Wert nachvollzogen, dann gefixt.

- **Was:** `_tage_aus_datumsbereich` (aufbereitung.py) gab einem Datum OHNE Jahresangabe bisher
  IMMER das neutrale Ankerjahr (2024), unabhängig davon, ob die ANDERE Seite des Bereichs bereits
  ein echtes Jahr nannte. Aus "15.09. - 18.09.2026" wurde so faktisch "15.09.2024 - 18.09.2026" –
  eine Differenz von ca. 733 Tagen statt der gemeinten 4. Fix: EIN gemeinsames Jahr wird ermittelt
  (das erste genannte, Start vor Ende; erst wenn KEINE Seite ein Jahr nennt, das Ankerjahr) und auf
  BEIDE Seiten angewendet, sofern die jeweils andere Seite kein eigenes, abweichendes Jahr nennt –
  ein echter Jahreswechsel-Bereich ("28.12.2026 bis 3.1.2027", beide Jahre explizit genannt) bleibt
  davon unberührt.
- Verifiziert direkt gegen den exakten gemeldeten Text: `schaetze_reisedauer_tage("15.09. -
  18.09.2026")` liefert jetzt `4`.
- Zweiter, vom Nutzer selbst als "kann auch mein Fehler sein" eingeordneter Punkt (ein explizit
  gewünschter Fischmarkt wurde nicht eingeplant) bewusst NICHT untersucht/verändert – vermutlich
  reine Öffnungszeiten-Kollision mit der gewählten Tagesstart-Präferenz (19 Uhr), vom Nutzer selbst
  als nachrangig markiert ("das können wir außen vor lassen").
- Tests: zwei neue Regressionstests in `test_aufbereitung.py` (Jahr nur am Ende/nur am Anfang des
  Bereichs). Komplette Suite: 308/308 grün.

## Phase 50 — Reisedauer: LLM interpretiert das Datum, Code rechnet deterministisch (24.08.2026)

Nach ZWEI Live-Bugs im selben Tag im reinen Freitext-Regex-Parser (Phasen 48/49) Rückfrage beim
Product Owner: "auf welcher Seite wird das gefixt?" – Ergebnis: der Freitext-Parser bleibt
grundsätzlich fehleranfällig für die Vielfalt echter Nutzerformulierungen; besser die LLM
Mehrdeutigkeiten im Dialog klären lassen (fehlendes Jahr, "nächsten Monat" o.Ä.), die eigentliche
Tagesberechnung aber weiterhin GARANTIERT deterministisch halten (Grundprinzip 3 – Rückfrage-
Ergebnis: *"die LLM bringt es zu einem Wert, und ich in meinem Algorithmus gucke, wie weit diese
Daten auseinanderliegen"*). Zusätzlich bestätigt: die POI-Anzahl-Kopplung an die Reisedauer
(`max_pois_fuer_reise`) ist bereits die EINE gemeinsame Quelle für Chat-Vorschau UND finale
Optimierung – keine separate Anbindung nötig, profitiert automatisch mit.

- **Was:** Neue Felder `ReiseAnfrage.reise_start_datum`/`reise_end_datum` (schema.py, ISO-Format
  "YYYY-MM-DD"). Neue Tool-Argumente bei `speichere_feld` (agent_tools.py, analog
  `tagesstart_minuten`/`tagesende_minuten`) – NUR bei `feld=reisezeitraum_rohtext`, nur gültige
  ISO-Strings werden übernommen (`datetime.date.fromisoformat`-Validierung), ein ungültiger Wert
  bleibt kommentarlos leer statt einen Fehler zu werfen (die LLM bekommt trotzdem den validierten
  `speichere_feld`-Erfolg zurück, versucht es im Gespräch ggf. erneut). katalog.py F06 weist die LLM
  aktiv an, bei Unsicherheit (fehlendes Jahr, vage Angabe) nachzufragen statt zu raten.
- Neue Funktion `aufbereitung.py::_tage_aus_iso_daten` – reine Datumsarithmetik aus den zwei
  ISO-Strings, None bei fehlenden/ungültigen Werten oder Ende-vor-Start (dann Fallback statt
  negativer/geratener Dauer, Grundprinzip 1). `schaetze_reisedauer_tage` bekommt zwei neue optionale
  Parameter (`start_datum`/`end_datum`) und prüft sie ZUERST, bevor der alte Freitext-Parser
  (explizite "X Tage" / Datumsbereich-Regex / Standard-Rückfall) überhaupt zum Zug kommt. Der alte
  Parser bleibt vollständig bestehen – als Fallback für dialogfreie Testfälle
  (`pruefe_planung.py`) und für den seltenen Fall, dass die LLM aus dem Gespräch kein eindeutiges
  Datum ableiten konnte.
- Alle drei bestehenden Aufrufer (`pipeline.py::plane_reise`, `aufbereitung.py::max_pois_fuer_reise`,
  `aufbereitung.py::erstelle_toptw_instanz`-Fallback) reichen jetzt `anfrage.reise_start_datum`/
  `reise_end_datum` mit durch.
- **Zusätzlich final entschieden (Product Owner, 24.08.2026, siehe "Offene Punkte" oben für die
  einzelnen Einträge):** echte Hotelpreise, weitere CO2-/Preistabellen-Verifizierung, eine echte
  Café-Zeitfenster-Obergrenze und mehrere Unterkünfte je Reise werden NICHT umgesetzt – bleibt beim
  aktuellen Stand. Die Idee "explizit genannte Orte erzwungen einplanen" (Fischmarkt-Beispiel aus
  Phase 49) wurde diskutiert (Pflicht-POI-Flag in Optimierung 1 vs. zweiter Startpunkt/Depot,
  Letzteres verworfen wegen Überschneidung mit "mehrere Unterkünfte") und bewusst zurückgestellt,
  nicht beauftragt.
- Verifiziert: `schaetze_reisedauer_tage("15.09. - 18.09.2026", start_datum="2026-09-15",
  end_datum="2026-09-18")` liefert `4`, `max_pois_fuer_reise` entsprechend `16` – direkt am
  Original-Fall aus Phase 49 durchgerechnet.
- Tests: neue Tests in `test_aufbereitung.py` (ISO-Daten haben Vorrang vor Freitext, funktionieren
  auch ohne Freitext, ungültige/verdrehte Daten fallen sauber auf den Freitext-Fallback zurück) und
  `test_agent_tools.py` (`speichere_feld` persistiert gültige ISO-Daten, verwirft ungültige,
  bleibt ohne Angabe `None` – analog zu den bestehenden `mobilitaetseinschraenkung_stufe`-Tests).
  Komplette Suite: 315/315 grün.

## Phase 51 — Prozessmodell komplett neu gezeichnet: Grundkonzept + Datenfluss je Fragekatalog-Feld (24.08.2026)

`Modell_1_Reisebot_Prototyp.drawio` (siehe CLAUDE.md, "Referenzdateien") bildete noch den ALTEN,
festen b2..b6/gw1..gw4-Swimlane-Ablauf ab – seit der werkzeugbasierten Dialogsteuerung (Phase 10)
technisch überholt, seit Langem als offener Punkt vermerkt. Nutzerwunsch: "jede kleine Veränderung
der Datei mit drin sehen, was macht die LLM wirklich, was macht der deterministische Bereich" – EIN
großes Grundkonzept plus für JEDE Frage eine eigene Seite mit dem konkreten Datenfluss.

- **Was:** Die Datei liegt in `Fortschritte/` (nicht im Code-Repo `reisebot_prototyp/`), alte Version
  vorher als `Modell_1_Reisebot_Prototyp.alt-vor-2026-08-24.drawio` gesichert statt überschrieben.
  Neu: 21 Seiten in EINER `.drawio`-Datei – Seite 1 "00 Grundkonzept" (Nutzer → LLM-Agent mit den 5
  Werkzeugen → ReiseAnfrage → harte Grenze zum deterministischen Layer → POI-Suche/Hartfilter/
  Sondermechanismen → Optimierung 1 (TOPTW/ILS) + Optimierung 2 (Verkehrsmittelwahl) + Monte-Carlo-
  Härtetest → Reiseplan → Ausgabe), danach EINE Seite je Fragekatalog-Feld (F01–F20, 20 Seiten).
- Jede Feld-Seite zeigt denselben Aufbau: Nutzer-Antwort → `ReiseAnfrage.<feld>` → ggf. LLM-Tool-
  Argumente (Seitenkanäle wie `mobilitaetseinschraenkung_stufe`/`flexibilitaet_stufe`/
  `tour_tage_anzahl`/`reise_start_datum`) → tatsächliche(s) Zielmodul(e) mit Wirkungs-Beschriftung
  auf dem Pfeil, ODER (bei Feldern ohne Code-Verwendung, z.B. F01 name/F02 email/F03 reisebegleitung/
  F17 lernaktivitaeten_interesse) ein rot gestricheltes Kästchen "keine deterministische Verwendung".
  Farblegende auf der Grundkonzept-Seite (Blau=LLM, Grau=rohes Feld, Grün=deterministischer Filter/
  Sondermechanismus, Orange=Kern-Optimierung, Lila=externe API, Gelb=nur Anzeige).
- **Methodik:** JEDER Datenfluss wurde vor dem Zeichnen per gezielter `grep`-Suche nach jedem
  `anfrage.<feld>`-Zugriff in `src/` verifiziert (nicht aus dem Gedächtnis/den Kommentaren
  übernommen) – z.B. bestätigt, dass `name`/`reisebegleitung`/das ROHE `flexibilitaet_praeferenz`-
  Freitextfeld tatsächlich NIRGENDS im deterministischen Layer gelesen werden (nur die davon
  abgeleiteten LLM-Tool-Argumente zählen).
- Erzeugt über ein kleines Python-Generator-Skript (mxGraph-XML-Bausteine: `box()`/`pfeil()`, EIN
  Eintrag pro Feld als strukturierte Daten) statt handgeschriebenem XML – bei 21 Seiten deutlich
  weniger fehleranfällig, und bei künftigen Code-Änderungen leicht wiederholbar/anpassbar. Das
  Generator-Skript selbst liegt nicht im Projekt (Einwegwerkzeug), nur das Ergebnis.
- Verifiziert: erzeugte Datei per `xml.etree.ElementTree` geparst (wohlgeformt), auf doppelte
  Cell-IDs und auf Kanten mit fehlendem Quell-/Ziel-Knoten geprüft (0 Fehler je Seite), Umlaute
  byte-genau als UTF-8 bestätigt. KEIN visueller Test in einem echten diagrams.net-Client (dafür
  bräuchte es die Desktop-App oder app.diagrams.net im Browser) – Layout-Feinschliff (z.B. exakte
  Positionen) ggf. dort noch von Hand nachzuziehen.

## Phase 52 — POI-Obergrenze nach echtem Kosten-Vorfall von 30 auf 15 gesenkt (24.08.2026)

Nutzer erhielt eine echte Google-Cloud-Rechnung über ca. 100€ (davon 40€ an einem einzigen Tag) und
fragte nach der Ursache. Analyse ergab: `aufbereitung.py::hole_reisezeitmatrix` holt für JEDEN
Planungslauf eine VOLLSTÄNDIGE (Depot+POIs)²-Distanzmatrix von Google, EINMAL PRO im Dialog genanntem
Verkehrsmittel (`modi_fuer_lokalen_transport` gibt bei mehreren genannten Verkehrsmitteln, z.B.
"Fahrrad und Bahn", ALLE zurück – bewusst so seit einer früheren Rückfrage, siehe dortiger
Kommentar). Bei der bisherigen Obergrenze von 30 POIs + 1 Unterkunft (=31 Orte) und zwei genannten
Verkehrsmitteln ergibt das ~1.900 abgerechnete Distance-Matrix-Elemente FÜR EINEN EINZIGEN
Reiseplan – da die Kosten quadratisch mit der POI-Zahl skalieren, ist das der dominante Kostentreiber
(nicht z.B. die Places-Suche oder die An-/Abreise-Berechnung).

- **Transparenz-Nachtrag:** Ein Teil der Kosten dieser Session selbst stammt von vier echten
  Live-Planungsläufen für die Bugfixes der Phasen 48–51, davon zwei mit dem teuren 15-Tage-
  Szenario + zwei Verkehrsmitteln (`smoketest_datumsbereich`, einmal über `pruefe_planung.py`,
  einmal über ein Ad-hoc-Skript für den `als_kartendaten`-Test) – für reine Struktur-Verifikation
  (Tage-Anzahl, Sonder-Tage) hätte MOCK_MODE ausgereicht, echte API-Calls waren nur für die
  "Route bis zum Hotel statt nur bis zur Stadt"-Prüfung nötig. Künftig: MOCK_MODE bevorzugen, wo es
  für die konkrete Verifikation ausreicht.
- **Was:** `aufbereitung.py::_MAX_POIS_FUER_OPTIMIERUNG` von 30 auf 15 gesenkt (Product-Owner-
  Entscheidung: "dass so was auf keinen Fall noch mal passieren kann") – senkt das Worst-Case-
  Element-Volumen auf rund ein Viertel. Bewusst in Kauf genommener Trade-off: weniger POI-
  Kandidaten für sehr lange Reisen, potenziell etwas weniger Auswahl für Optimierung 1.
  `_MIN_POIS_FUER_OPTIMIERUNG`/`_POIS_JE_TAG` unverändert.
- Empfehlung an den Product Owner (noch nicht umgesetzt, nicht beauftragt): zusätzlich ein
  Budget-Alert in der Google Cloud Console einrichten (unabhängig vom Code der einzige Schutz auch
  gegen künftige, noch unbekannte Kostentreiber) sowie perspektivisch ein Distanzmatrix-Cache für
  wiederholte Entwicklungs-Testläufe gegen dieselben Koordinaten.
- Tests: zwei bestehende Tests mit hartkodiertem alten Grenzwert (`test_aufbereitung.py`,
  `test_vorschlaege.py`) auf 15 aktualisiert. Komplette Suite: 315/315 grün.

## Phase 53 — POI-Obergrenze weiter auf 10 gesenkt, Flexibilitätsskala von 1-5 auf 1-3 verkleinert (24.08.2026)

Direkte Fortsetzung von Phase 52: 15 war dem Product Owner "auch noch zu hoch" ("dass so was auf
keinen Fall noch mal passieren kann"). Auf Nachfrage nach einer belastbaren Herleitung stellte sich
heraus, dass die Flexibilitätsstufe 1 ("ganz durchgeplant") bisher GAR KEINEN Deckel hatte (Tag
wurde voll ausgereizt) – die vom Nutzer erinnerte Zahl "3 POIs bei strikter Planung" existierte im
Code schlicht nicht. Der Product Owner entschied daraufhin, die Skala selbst neu zu ziehen, statt
eine nicht vorhandene Zahl zu erfinden.

- **Was (Flexibilitätsskala):** Skala von 1-5 auf 1-3 verkleinert. NEU: JEDE Stufe hat jetzt einen
  festen POI-pro-Tag-Deckel, auch Stufe 1 ("ganz durchgeplant" = 3 POIs/Tag, vorher unbegrenzt) –
  Stufe 2 = 2, Stufe 3 ("extrem flexibel") = 1. `_MAX_POIS_PRO_TAG_JE_FLEXIBILITAETSSTUFE` (vorher
  `{2:6,3:5,4:3,5:2}`) ist jetzt `{1:3,2:2,3:1}`. Pufferpausen (`_PAUSE_JE_FLEXIBILITAETSSTUFE`)
  entsprechend auf die neue Skala gemappt (Stufe 2→150/20 Min., Stufe 3→90/30 Min., Stufe 1 weiter
  ohne Puffer) – NICHT explizit vom Nutzer vorgegeben, eigene, klar dokumentierte Interpretation
  beim Verkleinern der Skala (Werte der bisherigen Stufen 4/5 übernommen). Nur `None` (kein Signal)
  bleibt weiterhin unbegrenzt. Änderung durchgezogen durch `agent_tools.py` (Tool-Argument-Schema
  `maximum` 5→3, Handler-Validierung), `katalog.py` (F05-Kontexthinweis), `schema.py`
  (Feld-Dokumentation), CLAUDE.md.
- **Was (POI-Obergrenze):** `_MAX_POIS_FUER_OPTIMIERUNG` von 15 auf 10 gesenkt – hergeleitet aus der
  neuen, strengsten Flexibilitätsstufe (3 POIs/Tag) über einen Referenzzeitraum von 3 Tagen (3×3=9)
  plus EINEM zusätzlichen Kandidaten als Reserve für "weitere Empfehlungen" (Product-Owner-Vorgabe:
  "drei Tage, drei POIs, plus ein gesonderter Vorschlag außerhalb"). `_MIN_POIS_FUER_OPTIMIERUNG=8`
  bleibt unverändert – der wirksame Bereich ist damit nur noch 8–10, die tage-abhängige Skalierung
  (`_POIS_JE_TAG=4`) wirkt sich dadurch faktisch kaum noch aus (ab 3 Tagen wird ohnehin die
  Obergrenze erreicht) – bewusst so belassen, da die Obergrenze jetzt die dominante Schutzgrenze
  gegen Kosten-Ausreißer ist, nicht mehr die Tage-Skalierung selbst.
- Klarstellung im Gespräch, die zur Neuherleitung führte: `_MAX_POIS_FUER_OPTIMIERUNG` (Kandidaten-
  POOL für die GESAMTE Reise) und der Flexibilitäts-Deckel (POIs, die pro TAG tatsächlich eingeplant
  werden) sind zwei unterschiedliche Mechanismen – die Pool-Obergrenze muss größer als das absehbare
  Scheduling-Maximum bleiben, sonst hat Optimierung 1 keine echte Auswahl mehr zum Verwerfen.
- Tests: `test_max_pois_pro_tag_fuer_flexibilitaet_je_stufe`/`test_pause_parameter_fuer_flexibilitaet_
  je_stufe` auf die neue 1-3-Skala umgeschrieben (Stufe 1 hat jetzt einen Wert statt `None`),
  `test_erstelle_toptw_instanz_barrierefreiheit_und_flexibilitaet_kombiniert_nimmt_kuerzeres_
  intervall` von Stufe 5 auf Stufe 3 umgestellt, mehrere hartkodierte Obergrenzen-Werte (12/15) auf
  10 aktualisiert. Bewusst KEIN Live-Test gegen die echte API (Lehre aus Phase 52: für reine
  Grenzwert-Verifikation reicht die deterministische Testsuite, kein weiterer Kostenanfall nötig).
  Komplette Suite: 315/315 grün.

## Phase 54 — Flexibilitäts-Einstufung: LLM ordnete einfaches "flexibel" fälschlich der Mitte statt Stufe 3 zu (26.08.2026)

Erster echter Live-Test der Phase-53-Skala (Web-Oberfläche): Nutzer sagte laut eigener Aussage
"gerne flexibel", die LLM speicherte daraufhin `flexibilitaet_stufe=2` (Mitte) statt der erwarteten
Stufe 3 (siehe Protokoll `web_2026-08-26_145355.jsonl`: `flexibilitaet_praeferenz='flexibel, kein
straffes Programm'`, `flexibilitaet_stufe=2`) – sichtbar an nur 2 statt der erwarteten 1 vorgeschlagenen
POI/Tag. Ursachenanalyse: die alte 1-5-Skala-Formulierung im Systemprompt verlangte implizit eine
GESTEIGERTE Aussage ("extrem flexibel") für die oberste Stufe; bei nur noch 3 Stufen ist aber schon
ein einfaches "flexibel" OHNE Steigerung der korrekte obere Wert – das war der LLM nicht explizit
gesagt worden.

- **Was:** `katalog.py` F05 `kontext_hinweis` und `agent_tools.py`
  `flexibilitaet_stufe`-Tool-Argument-Beschreibung ergänzt: ein einfaches "flexibel"/"spontan" OHNE
  Steigerungswort reicht für Stufe 3, ein einfaches "durchgeplant"/"fest"/"strukturiert" reicht für
  Stufe 1 – Stufe 2 ist AUSDRÜCKLICH nur für erkennbar gemischte/neutrale Aussagen reserviert
  (z.B. "teils, teils"), nicht der Standardfall für jede nicht eindeutig extreme Antwort. Live-
  Vorfall ("gerne flexibel" → fälschlich Stufe 2) wörtlich als Negativbeispiel im Prompt hinterlegt.
- Reine Prompt-Änderung, keine Code-Logik betroffen – keine neuen Tests nötig, komplette Suite
  weiterhin 315/315 grün. Verifikation der Wirkung erst durch einen erneuten Live-Test möglich (vom
  Nutzer explizit abgelehnt, die rohe Chat-Nachricht zusätzlich zu protokollieren, um das künftig
  einfacher nachvollziehen zu können).

## Phase 55 — Fragekatalog-Feinschliff: F18 (Unverträglichkeiten) in F09 integriert, F04 (Reiseleitung) nach hinten verschoben (07.09.2026)

Reine Reihenfolge-/Zuschnittsänderung am Fragekatalog auf ausdrücklichen Nutzerwunsch, kein neues
Feld, keine neue Fachlogik:

- **Was (1):** Die eigene Katalogfrage F18 ("Haben Sie spezielle Ernährungsbedürfnisse oder
  Allergien...", `ernaehrung_einschraenkungen`) wurde aus `katalog.py` entfernt. Stattdessen fragt
  F09 (`gesundheitliche_einschraenkungen`, "medizinische Bedürfnisse/Einschränkungen") jetzt explizit
  auch nach Unverträglichkeiten/Allergien mit; das LLM soll NUR nachhaken, welche Unverträglichkeit
  konkret gemeint ist, wenn der Nutzer bei F09 tatsächlich eine erwähnt – sonst bleibt das Thema
  unbehandelt, kein separates Nachfragen ins Blaue. Technisch über ein neues Tool-Argument
  `ernaehrung_einschraenkungen` bei `speichere_feld(feld="gesundheitliche_einschraenkungen")`
  gelöst (`agent_tools.py`), exakt nach demselben Muster wie das bereits bestehende
  `mobilitaetseinschraenkung_stufe`-Argument. Das Schema-Feld `ernaehrung_einschraenkungen` selbst
  bleibt unverändert bestehen (wird weiterhin für die Restaurant-Suche in `google_maps.py` und die
  harte Verträglichkeitsprüfung in `vertraeglichkeit.py` gebraucht) – nur der Weg, wie es befüllt
  wird, ändert sich.
- **Warum (1):** Nutzereinschätzung: beide Fragen erheben inhaltlich dasselbe Thema
  ("gesundheitsbezogene Einschränkung") und sollten daher zu einer Frage zusammengefasst werden,
  statt den Nutzer zweimal nacheinander nach verwandten Dingen zu fragen.
- **Was (2):** F04 ("Möchten Sie einen Reiseleiter oder eine Reiseleitung vor Ort haben?",
  `reiseleitung_gewuenscht`) wurde von seiner ursprünglichen Position direkt nach F03
  (Reisebegleitung) an das Ende des Katalogs verschoben, direkt VOR F17 (Lernaktivität). `id`,
  `stufe` und `cluster` bleiben unverändert (Rückführbarkeit auf das Original-Dokument, exakt wie
  beim bereits bestehenden Präzedenzfall F17/F19 vor F16, siehe Phase-Kommentar in `katalog.py`) –
  nur die tatsächliche Position in der Python-Liste (und damit die Gesprächs-Reihenfolge, die das
  LLM aus `regelwerk.py::_fragekatalog_uebersicht` abliest) ändert sich.
- **Warum (2):** Nutzereinschätzung: Reiseleitung/geführte Tour und Lernaktivität (Kurs/Workshop)
  fragen im Kern dasselbe ("möchten Sie sich vor Ort etwas zeigen/vermitteln lassen") und gehören
  daher thematisch zusammen, statt wie zuvor weit auseinanderzuliegen.
- Reine Prompt-/Katalog-Änderung, keine neue Fachlogik. Komplette Suite weiterhin grün (315/315).
  Betroffene Doku-Kommentare (Modul-Docstrings in `katalog.py`/`schema.py`/`agent_tools.py`/
  `vertraeglichkeit.py`/`poi_sammlung.py`, veraltete F18-Referenzen in Testkommentaren) mit
  aktualisiert; der historische Changelog-Eintrag in `tests/conftest.py` (der die frühere F18-
  Bezeichnung noch nennt) bewusst NICHT rückwirkend umgeschrieben, da er den damaligen Stand
  dokumentiert.
- Offen: die beiden Prozessmodell-Dateien (`Modell_1_Reisebot_Prototyp_Gesamtbild.drawio`,
  `Modell_1_Reisebot_Prototyp_Datenfluss.drawio`, siehe Phase 51, liegen in Fortschritte/, nicht im
  Code-Repo) bilden F04/F18 noch an der ALTEN Position/als eigene Frage ab – hier NICHT automatisch
  nachgezogen (Diagrammdatei außerhalb des Code-Repos), muss bei Bedarf von Hand nachgezogen
  werden.
- Zusätzlich vom Nutzer zur Diskussion gestellt, aber NICHT umgesetzt (nur Feedback erbeten): ob
  F20 (`tagesstart_praeferenz`, "ab wann/bis wann POIs am Tag") noch gebraucht wird. Einschätzung:
  ja, weiterhin relevant – bestimmt nicht nur die angezeigten Uhrzeiten im fertigen Plan, sondern
  laut `schema.py`-Kommentar direkt das TATSÄCHLICHE Tagesbudget für Optimierung 1 (ersetzt sonst
  einen festen Konfigurations-Default) und ist bereits `pflichtfeld=False` mit sinnvollem Fallback-
  Verhalten bei vager/fehlender Antwort – also geringe Gesprächslast bei echtem Planungsnutzen.

## Offene Punkte

- Die `ist_barrierefrei()`-Einzelabfragen für die NORMALEN POI-Kandidaten (Sehenswürdigkeiten etc.,
  außerhalb von Touren/Restaurants) laufen weiterhin sequenziell in `filtere_pois_hart` – bei vielen
  Roh-Treffern UND `mobilitaetseinschraenkung_stufe` in ("mittel", "stark") bleibt das langsam
  (siehe Phase 44, ca. 37 Sek. im Live-Test). Vorschlag (noch nicht umgesetzt, nicht beauftragt):
  diese Aufrufe parallelisieren (z.B. Thread-Pool statt sequenziell).

- ~~Echte Hotelpreise statt Preisniveau-Schätzung~~ — Product-Owner-Entscheidung (24.08.2026):
  bleibt bei der Preisniveau-Schätzung (`price_level` 0-4), keine gesonderte Hotel-/OTA-Preis-API.

- Ursprünglich gemeldetes Symptom aus Phase 38 ("Bahnhöfe tauchen am An-/Abreisetag als eigene
  POI-Karten auf, gelabelt 'An- und Abreise'") ist NICHT behoben – die dafür gebaute pauschale
  Ausschlussliste wurde auf Nutzerwunsch wieder entfernt (siehe Nachtrag), weil Bahnhöfe als
  POI-Kandidat grundsätzlich weiter möglich bleiben sollen. Nächster Schritt: mit dem Nutzer klären,
  was am beobachteten Zustand ("An- und Abreise" als Kartenlabel) konkret stört – ob es z.B. NUR um
  die konkrete Beschriftung ging, um eine Häufung an genau diesen beiden Tagen, oder um etwas
  anderes, das sich nicht pauschal an einem Google-Place-Type festmachen lässt.

- `planungs_testfaelle/` fehlt komplett (siehe Phase 36) – README.md und `pruefe_planung.py`
  dokumentieren einen Default-Testfall `klettern_essen` sowie weitere (laut `ergebnisse/`-Resten:
  Annegret/Jakob/Thomas), die Original-JSONs sind aber nicht mehr vorhanden. Nur
  `smoketest_etappen.json` (für den Phase-36-Live-Test neu angelegt) liegt aktuell dort. Beim
  Product Owner erfragen, ob/wie die ursprünglichen Testfälle rekonstruiert werden sollen.

- ~~`Modell_1_Reisebot_Prototyp.drawio` bildet noch den ALTEN, festen b2..b6/gw1..gw4-Ablauf ab~~ —
  erledigt in Phase 51: komplett neu gezeichnet (Grundkonzept + eine Seite je Fragekatalog-Feld).
  Offen bleibt nur noch: kein visueller Test in einem echten diagrams.net-Client, Layout-Feinschliff
  ggf. dort von Hand nachzuziehen.
- Warnhinweis-Text in `vorschlaege.py::hole_echte_daten_fuer_vorschlag` bei zu vielen Rohtreffern
  kann unsinnige Zahlen zeigen ("Vorschau, 30 von 15") wenn `ziel_max` größer als die tatsächliche
  Trefferzahl ist — reine Formulierungssache, keine Datenauswirkung (siehe Phase 10, Nebenbefund).
- ~~Mailjet-Account noch nicht eingerichtet~~ — erledigt: Key/Secret/Absenderadresse seit 12.08.2026
  hinterlegt, `sende_mail` live gegen die echte Mailjet Send API v3.1 getestet (Testmail erfolgreich
  zugestellt).
- ~~FlightAPI.io- und Hotelbeds-Anbindung noch nie live getestet~~ — gegenstandslos: beide
  Anbindungen wurden in Phase 32 komplett entfernt (All-Inclusive/Flug raus, siehe dort).
- Geografische Vor-Clusterung von POIs vor dem Tag-für-Tag-ILS-Lauf (Nutzeridee, 12.08.2026:
  "erst grob gucken, was nah beieinander liegt, dann in Tage aufteilen") – bewusst NICHT mit dem
  Mahlzeiten-Mindestabstand (Phase 16) umgesetzt, eigener, größerer Eingriff in den ILS-Kern,
  separat zu bewerten.
- ~~Café-Tageszeitregel (Phase 16) ist nur eine MINDESTZEIT, kein echtes Zeitfenster mit
  Obergrenze~~ — Product-Owner-Entscheidung (24.08.2026): bleibt wie es ist, keine Obergrenze
  geplant.
- ~~Mehrere Unterkünfte je Reise (Rundreise mit Etappen-/Hotelwechsel)~~ — Product-Owner-
  Entscheidung endgültig bestätigt (24.08.2026, nach vorherigem Zurückstellen 12.08.2026): kommt
  nicht, es soll EIN Trip mit EINER Unterkunft geplant werden. Optimierung 1 plant weiterhin die
  GESAMTE Reise gegen EIN Depot.
- ~~CO2-Emissionsfaktoren sind Platzhalter und müssen vor Verwendung in der Arbeit gegen eine
  offizielle Quelle verifiziert werden~~ — Product-Owner-Entscheidung (24.08.2026): bleibt bei den
  aktuellen Werten, keine weitere Verifizierung vorgesehen.
- Monte-Carlo-Parameter (Verteilung, Läufe, Schwelle) sind ein begründeter
  Vorschlag, aber laut CLAUDE.md eigentlich mit dem Product Owner
  abzustimmen.
- TOPTW/ILS-Implementierung ist eine eigenständige Python-3-Umsetzung, noch
  nicht gegen die genannte Referenzimplementierung (Constantino/TOPTW)
  abgeglichen. (Eine ANDERE, unabhängige Prüfung – gegen Google OR-Tools + Brute-Force statt gegen
  diese spezifische Referenzimplementierung – wurde in Phase 21 durchgeführt, siehe
  `evaluierung/README.md`; ersetzt den Abgleich mit Constantino/TOPTW nicht, ergänzt ihn.)
- ~~Kein Cache der POI-zu-POI-Distance-Matrix über mehrere Unterkunfts-Kandidaten hinweg~~ —
  gegenstandslos: seit Phase 32 gibt es nur noch EINE Unterkunft (kein Kandidatenvergleich mehr,
  `_plane_bestes_depot` entfernt), die Distanzmatrix wird ohnehin nur noch einmal pro Planung
  berechnet.
- POI-Öffnungszeiten werden pauschal als ganztägig angenommen (Places
  Nearby Search liefert keine vollständigen Öffnungszeiten ohne
  zusätzliche Place-Details-Anfrage pro Ort).
- `GoogleMapsClient.ist_barrierefrei()` (Phase 5) noch nie live gegen die echte Places-API
  getestet (kein Key mit Details-Zugriff verifiziert).
- Monte-Carlo-"Robustheits-Gateway" (CLAUDE.md: "nicht robust → mit Sicherheitspuffern erneut
  optimieren") ist bisher NUR eine Anzeige ("robust"/"NICHT robust" im Reiseplan), KEIN
  automatischer Rückkopplungs-Loop, der bei "nicht robust" tatsächlich mit Puffern neu plant –
  Lücke zwischen CLAUDE.md-Beschreibung und Implementierung, aufgefallen bei einer Nutzerfrage
  nach nicht-offensichtlichen Implementierungsdetails (12.08.2026). Gilt seit Phase 40 unverändert
  für den neuen Teilstrecken-Härtetest (Hinreise/Rückreise) statt für den früheren POI-Test.
- ILS-Reparaturschritt (`toptw.py::iterated_local_search`) hängt nach `_shake()` reparierte POIs
  IMMER hinter den unveränderten Präfix an, versucht nie eine Einfügeposition davor/dazwischen –
  am `pruefe_algorithmus.py`-Beispiel konkret nachgewiesen (Score 13 statt möglicher 15, per
  `simuliere_route()` verifiziert, siehe Phase 40 Nebenbefund). Noch nicht behoben, vom Nutzer noch
  nicht beauftragt.
- ~~Tagesablauf-Parameter (F20) sollte der KI zur Interpretation übergeben werden~~ — erledigt in
  Phase 33.
- ~~Web-Oberfläche für den Chat (HTML-Seite statt Konsole) mit Bild-/Kurzinfo-Vorschau für Hotels
  und POIs~~ — erledigt in Phase 34 (webapp.py).
- ~~Browser-Ende-zu-Ende-Test von `webapp.py` steht noch aus~~ — größtenteils erledigt: echter
  Chat-Durchlauf im Browser mit echtem Google-Maps-Key mehrfach durchgeführt (u.a. die 15-Tage-
  Testreise, die zu Phase 48/49 führte, siehe `protokolle/web_2026-08-24_163339.jsonl`). Mikrofon/
  Vorlesen (Phase 35) weiterhin nicht selbst in einem echten Browser ausprobiert.
- ~~Preistabellen in `kostenschaetzung.py` sind Platzhalter-Annahmen~~ — Product-Owner-Entscheidung
  (24.08.2026): bleibt bei den aktuellen Werten, wie bei den CO2-Emissionsfaktoren.
- Explizit genannte Orte (z.B. "ich möchte den Fischmarkt sehen") werden aktuell wie jeder andere
  POI nur über den Score priorisiert, nicht garantiert eingeplant – Nutzeridee (24.08.2026): ein
  "Pflicht-POI"-Flag in Optimierung 1 (ILS fügt ihn zuerst ein, wie den Depot-Punkt), Alternative
  "zweiter Startpunkt/Depot" wurde verworfen (liefe auf dasselbe Mehr-Depot-Problem hinaus wie
  "mehrere Unterkünfte", das gerade endgültig zurückgestellt wurde). Bewusst zurückgestellt, noch
  nicht beauftragt – offen bleibt zusätzlich, WIE "explizit gewünscht" erkannt wird (vermutlich
  LLM-Tool-Argument analog `tour_tage_anzahl`).

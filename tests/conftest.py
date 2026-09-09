"""
Testübersicht des Reisebot-Prototyps.

Diese Datei enthält aktuell keine gemeinsamen Fixtures, sondern dient als
Nachschlagewerk: welches Modul wird durch welche Tests wie abgedeckt (siehe
CLAUDE.md: "Tests je Modul"). Ausführung: `pytest` aus diesem Verzeichnis
(siehe pytest.ini). Stand: 2026-08-10.

tests/test_aufbereitung.py — Scoring & Auswahl vor Optimierung 1 (Ergänzung)
--------------------------------------------------------------------------------
Zusätzlich zu max_pois_fuer_reise:
- test_berechne_poi_score_matcht_echte_google_place_types /
  ..._matcht_overpass_kategorien / ..._matcht_deutsche_mock_kategorien_weiterhin:
    Regression für einen behobenen Bug (siehe Projektkonversation) – vorher
    matchte `berechne_poi_score` deutsche Präferenzen ("Kultur") nur per
    rohem Substring-Vergleich gegen `poi.kategorie`, was bei ECHTEN Google-
    Places-Ergebnissen (englischer Place Type wie "museum") praktisch nie
    traf. Nutzt jetzt dieselben Alias-Tabellen wie die POI-Suche.
- test_berechne_poi_score_gewichtung_erhoeht_treffer_staerker: optionale
  relative Gewichtung (aus einer vergleichenden Rückfrage bei zu vielen
  Treffern, siehe llm_interpreter.py `kategorie_gewichtung`) erhöht den
  Score stärker als ein neutraler Treffer.
- test_waehle_top_pois_*: Auswahl der besten (nicht der ERSTEN) POIs nach
  Score – behobener Bug: pipeline.py kappte vorher VOR dem Scoring.
- test_waehle_top_pois_fuellt_nicht_mit_unpassenden_treffern_auf (siehe
  Projektkonversation: "er sucht einfach irgendwelche Aktivitäten raus, auch
  Gym oder Spa, obwohl ich das nicht will"): behobener Bug – ein POI ohne
  Treffer zu irgendeiner genannten Präferenz bekam vorher trotzdem den
  neutralen Basis-Score 1.0 (`berechne_poi_score`) und konnte so bis zum
  Maximum auffüllen (auch branchenfremde Google-Places-Zufallstreffer wie
  einen Physiotherapeuten). Jetzt: Score 0.0 bei keinem Treffer, wird
  ausgefiltert – die Auswahl darf kleiner als `max_anzahl` sein. Zusätzlich
  wurde `google_maps.py::_waehle_place_types` von "sucht IMMER auch
  Restaurant/Bar/Spa" auf "sucht NUR, was genannt wurde" umgestellt (siehe
  test_google_maps.py, dort ebenfalls angepasst).
- test_parameter_fuer_lokalen_transport_* / test_erstelle_toptw_instanz_
  setzt_geschwindigkeit_aus_lokalem_transport (siehe Projektkonversation:
  "wenn ich Fahrrad angebe, sollte das die Planung beeinflussen"): F14-
  Freitext -> (Geschwindigkeit km/h, Suchradius Meter), fließt in
  TOPTWInstanz.geschwindigkeit_kmh UND (siehe pipeline.py/google_maps.py)
  den Places-Suchradius ein.

tests/test_overpass.py — Spezialrecherche für Aktivitäten (src/api/overpass.py)
---------------------------------------------------------------------------------
Prüft die Aktivität->Overpass-Tag-Zuordnung und den Mock-Client:
- test_waehle_alias_erkennt_bekannte_aktivitaeten /
  ..._liefert_none_fuer_unbekannte_aktivitaet: Teilstring-Matching analog zu
  google_maps.py::_KATEGORIE_ALIASE.
- test_mock_overpass_client_*: liefert Beispiel-POIs mit Schwierigkeitsgrad
  bzw. leere Liste ohne Alias-Treffer.
- test_erster_vorhandener_tag_*: Priorisierung mehrerer OSM-Tag-Kandidaten
  für uneinheitlich getaggte Schwierigkeitsgrade (siehe Moduldoku dort).
STATUS: `OverpassClient` (der echte HTTP-Client) ist manuell live gegen die
echte Overpass-API verifiziert (siehe Moduldoku in overpass.py – dabei drei
Stolpersteine gefunden und behoben: fehlender User-Agent führte zu "406 Not
Acceptable", uneinheitliche Grade-Tags brauchten mehrere Kandidaten, und der
öffentliche Server antwortet unter Last live reproduzierbar mit "504 Gateway
Timeout" – Regression: test_overpass_client_fehlerhafte_antwort_wird_
abgefangen_statt_absturz/..._timeout_..., HTTP-Fehler werden jetzt
abgefangen statt die gesamte Planung crashen zu lassen), aber ansonsten
NICHT in der automatisierten Suite (Netzwerkabhängigkeit/Rate-Limit, gleiche
Begründung wie bei GoogleMapsClient).

tests/test_poi_sammlung.py — geteilter POI-Sammel-Helper (src/datenaufbereitung/poi_sammlung.py)
----------------------------------------------------------------------------------------------------
Prüft, dass Places-POIs und (nur bei gesetzter `aktivitaeten_mit_spezialrecherche`)
Overpass-POIs korrekt zusammengeführt und nach Name dedupliziert werden;
`overpass_client` ist injizierbar, damit der Test unabhängig vom lokalen
`MOCK_MODE` deterministisch bleibt (siehe Moduldoku dort).

tests/test_fragekatalog.py — AP1 (Datenmodell) + AP2 (Dialogschicht)
----------------------------------------------------------------------
Prüft Fragekatalog (katalog.py), Datenmodell (schema.py) und die
Zustandsmaschine (zustandsmaschine.py) im Zusammenspiel:
- test_katalog_und_schema_felder_stimmen_ueberein:
    jedes `feld` aus FRAGEKATALOG existiert als Attribut in ReiseAnfrage
    (verhindert, dass Katalog und Schema auseinanderlaufen).
- test_rueckfrage_bei_leerer_pflichtantwort:
    leere Antwort auf eine Pflichtfrage löst eine Rückfrage aus, der Wert
    wird NICHT gesetzt (Prozessschritt "Antwort vollständig & plausibel?").
- test_vollstaendiger_durchlauf_schliesst_dialog_ohne_rueckfrage_ab:
    alle 19 Fragen lassen sich mit typkonformen Beispielwerten beantworten,
    ohne dass eine gültige Eingabe fälschlich zurückgewiesen wird.
- test_abbruch_wunsch_beendet_dialog_sofort:
    das Schlüsselwort "abbrechen" löst das Abbruch-Gateway aus und beendet
    den Dialog, unabhängig davon, welche Frage gerade aktiv ist.
- test_optionale_frage_akzeptiert_leere_antwort:
    bei optionalen Fragen (pflichtfeld=False) wird eine leere Antwort
    akzeptiert statt eine Rückfrage-Schleife auszulösen.
- test_bestaetige_und_speichere_setzt_zusatzfelder:
    der optionale `zusatz`-Parameter (chat.py, F16 `aktivitaeten_mit_
    spezialrecherche`) setzt zusätzliche ReiseAnfrage-Felder neben dem
    Hauptwert, ohne die Signatur für Typ A/B zu verändern.
- test_betroffene_korrektur_fragen_*, test_frage_zur_korrektur_zuruecksetzen_*,
  test_springe_zu_frage_*: Primitive für die nachträgliche Korrektur bereits
  bestätigter Antworten (siehe Projektkonversation: "was ist, wenn ich nach
  5 Minuten merke, dass ich doch nicht in die Türkei will?") – nur bereits
  BESTÄTIGTE, abhängige Folge-Fragen (`_ABHAENGIGE_FELDER`) gelten als
  betroffen; die eigentliche Korrekturschleife (erneut durch b2..b6 schicken,
  danach zurück zur unterbrochenen Frage) liegt in chat.py und ist NUR
  manuell/per Live-Smoke-Test verifiziert (siehe unten, gleiche Begründung
  wie bei der übrigen LLM-Anbindung).

tests/test_toptw.py — AP5 (Optimierung 1: Greedy + ILS)
-----------------------------------------------------------
Prüft, dass die harten Constraints aus CLAUDE.md ("Optimierung 1")
eingehalten werden:
- test_ils_ergebnis_ist_eine_gueltige_route:
    die von iterated_local_search zurückgegebene Route lässt sich erneut
    simulieren, ohne ein Zeitfenster oder das Tagesbudget zu verletzen.
- test_ils_liefert_score_groesser_gleich_null:
    der Gesamtscore einer geplanten Route ist nie negativ (Regressionsschutz
    für die Insertions-/Shake-Logik).
- test_zeitfenster_wird_nicht_verletzt:
    simuliere_route gibt None zurück, wenn allein die Anreise zu einem POI
    dessen Schließzeit überschreitet.
- test_tagesbudget_wird_nicht_verletzt:
    simuliere_route gibt None zurück, wenn die Rückkehr zum Depot das
    Tagesbudget überschreitet.
- test_geschwindigkeit_kmh_beeinflusst_reisezeit / test_plane_gesamte_reise_
  ohne_tagesbudget_je_tag_nutzt_instanz_budget / ..._mit_verkuerztem_tag1_
  budget_plant_dort_weniger_ein (siehe Projektkonversation: "Anreisezeit
  frisst Tag 1 nicht auf" + "Fahrrad soll Sachen in Fahrradnähe raussuchen"):
  `TOPTWInstanz.geschwindigkeit_kmh` ist jetzt konfigurierbar (statt
  hartcodiertem Fußweg-Tempo) und `plane_gesamte_reise` akzeptiert ein
  individuelles `tagesbudget_je_tag` – Tag 1 bekommt in pipeline.py die um
  die Hinreisedauer verkürzte Zeit, live über main.py verifiziert (19h-
  Bahnfahrt -> Tag 1 korrekt leer statt unrealistisch voll durchgeplant).

tests/test_verkehrsmittelwahl.py — AP6 (Optimierung 2: Verkehrsmittelwahl)
--------------------------------------------------------------------------
Prüft die gewichtete Bewertung (Zeit/Kosten/CO2) und den
Nachhaltigkeits-Nudge:
- test_bahn_wird_bei_gleicher_zeit_und_kosten_wegen_co2_bevorzugt:
    sind Zeit und Kosten zweier Alternativen identisch, entscheidet allein
    der (niedrigere) CO2-Wert über den Sieger.
- test_nudge_wird_erzeugt_wenn_bahn_langsamer_aber_sauberer_ist:
    die Nudge-Botschaft wird erzeugt und enthält "Bahn", wenn die Bahn zwar
    langsamer, aber die schnellste Alternative nicht die Bahn ist.
- test_kein_nudge_wenn_bahn_bereits_die_beste_option_ist:
    kein Nudge, wenn die Bahn ohnehin schon die insgesamt beste Alternative
    ist (kein Anreiz zum Umsteigen nötig).

tests/test_monte_carlo.py — AP7 (Monte-Carlo-Härtetest, NUR An-/Abreise-Umstiege)
----------------------------------------------------------------------------------
Prüft `haertetest_teilstrecken` (ARCHITEKTURWECHSEL, siehe monte_carlo.py: der
frühere POI-vor-Ort-Härtetest wurde abgeschafft, geprüft werden jetzt reale
Bus-/Bahn-Umstiege der Hin-/Rückreise):
- test_haertetest_liefert_quote_zwischen_0_und_1:
    die Robustheitsquote liegt für jede Eingabe im gültigen Bereich [0, 1]
    und die Anzahl der Läufe wird korrekt weitergereicht.
- test_grosszuegiger_umstiegspuffer_ist_robust:
    ein Umstieg mit viel Puffer übersteht die Störung der Fahrzeiten in
    (nahezu) allen Läufen und gilt daher als robust.
- test_umstiegspuffer_null_erkennt_verpassten_anschluss:
    ein Umstieg ohne jeden Puffer erzeugt tatsächlich Verletzungen – beweist,
    dass der Mechanismus verpasste Anschlüsse erkennt statt immer "robust" zu
    melden.
- test_teilstrecke_ohne_wartezeit_ist_kein_pruefpunkt:
    eine TRANSIT-Teilstrecke ohne wartezeit_minuten (z.B. die erste, ohne
    vorherigen Anschluss) wird selbst nicht als Umstieg geprüft.
- test_leere_teilstreckenliste_ist_robust:
    keine Teilstrecken (z.B. Auto) -> kein Härtetest-Risiko, immer robust.

tests/test_google_maps.py — AP3 (echter API-Layer, GoogleMapsClient)
--------------------------------------------------------------------
Prüft die NICHT-netzwerkabhängigen Teile der echten Google-Maps-Anbindung
(requests.get wird per unittest.mock simuliert, da kein echter Key vorliegt
— siehe "Bewusste Lücken" unten):
- test_client_ohne_key_wirft_fehler: leerer API-Key wird sofort abgelehnt.
- test_waehle_place_type_bekannte_kategorie /
  ..._unbekannte_kategorie_faellt_auf_standard_zurueck:
    Mapping deutscher Präferenz-Labels auf Google-Place-Types.
- test_geocode_parst_koordinaten_aus_antwort: korrektes Parsen einer
  Beispiel-Geocoding-Antwort, inkl. korrekt übergebenem API-Key im Request.
- test_geocode_ohne_treffer_wirft_fehler / test_get_wirft_bei_fehlerstatus_laufzeitfehler:
    Fehlerbehandlung bei ZERO_RESULTS/REQUEST_DENIED.
- test_suche_pois_nutzt_uebergebenen_radius: Suchradius kommt jetzt vom
  Aufrufer statt hartcodiert (siehe aufbereitung.py `parameter_fuer_
  lokalen_transport`).
- test_reisealternativen_ueberspringt_route_ohne_verbindung:
    fehlende Bahn-/Fernbusverbindung wird übersprungen statt einen Fehler
    zu werfen; nur tatsächlich gefundene Routen werden zurückgegeben.
- test_suche_unterkuenfte_gibt_praeferenz_text_als_keyword_weiter /
  ..._ohne_praeferenz_text_setzt_kein_keyword: die F15-Freitextantwort
  ("Vorstellungen") geht als echter Places-`keyword`-Parameter in die
  Nearby-Search ein (siehe Projektkonversation: "Top 5 nach Budget/
  Vorstellungen/Lage") – Google sortiert dann selbst nach Relevanz, statt
  dass ein eigenes Text-Matching erfunden wird.

tests/test_flightapi.py + tests/test_hotelbeds.py — Flug-/Hotelsuche (Ersatz für Amadeus)
-------------------------------------------------------------------------------------------
HINTERGRUND (siehe Projektkonversation): Amadeus for Developers hat seinen
kostenlosen Self-Service-Test-Tarif am 17.07.2026 eingestellt – die frühere
tests/test_amadeus.py wurde ersetzt. FlightAPI.io (Flüge) und Hotelbeds
(All-Inclusive-Hotels, `boardCode="AI"`) wurden gegen die jeweils echte
API-Dokumentation/OpenAPI-Spec verifiziert (nicht geraten), NICHT gegen die
echte API selbst (kein Key verfügbar) – wie zuvor bei Amadeus per
unittest.mock auf `requests`:
- test_flightapi.py: IATA-Auflösung + Onewaytrip-Antwortparsing (Dauer aus
  `legs[].duration`, Preis aus `itineraries[].pricing_options[].price.amount`),
  leere Liste ohne gefundenen Flughafen, RuntimeError bei Fehlerstatus.
- test_hotelbeds.py: `boardCode`-Filterung auf "AI" (Hotels ohne All-
  Inclusive-Rate werden übersprungen), Api-key/X-Signature-Auth-Header,
  `amenity_fuer_aktivitaet`-Zuordnung. `hotel_hat_amenity` liefert bei der
  echten Anbindung bewusst IMMER `False` (siehe Moduldoku hotelbeds.py: der
  numerische Facility-Katalog ist nicht verifiziert – lieber ehrlich
  einschränken als einen Facility-Code zu raten, Grundprinzip 1).

Bewusste Lücken (noch nicht automatisiert getestet)
-----------------------------------------------------
- src/api/google_maps.py::GoogleMapsClient: die HTTP-Interaktion selbst ist
  NICHT live gegen die echte Google-Maps-API getestet (kein Key verfügbar).
  Die Endpunkt-Implementierung (Places/Distance-Matrix/Directions/Geocoding)
  ist fertig, aber ungetestet – siehe Moduldoku dort für bekannte,
  bewusste Vereinfachungen (Öffnungszeiten, Nachhaltigkeitszertifikat,
  Kostenschätzung). Bitte nach Eintragen eines echten Keys einmal live
  verifizieren.
- src/ausgabe/reiseplan.py: speichere_datei/speichere_json/sende_mail sind
  bisher nur manuell über den main.py-Lauf verifiziert (siehe Terminal-
  Output), nicht als automatisierte Tests. als_text/als_html haben seit der
  Ergänzung um `alle_unterkunft_kandidaten`/`sicherheitshinweis` (siehe
  Projektkonversation: "alle Empfehlungen in die Mail", F11 muss die Planung
  beeinflussen) jetzt eigene Tests: tests/test_reiseplan.py – inkl. Maps-
  Link-Fallback über Koordinaten für Unterkünfte ohne Google-`place_id`
  (z.B. Hotelbeds-Hotels).
- src/pipeline.py: nur indirekt über main.py verifiziert (kein eigener
  Test) – gilt auch für die neue Weitergabe von `alle_unterkunft_kandidaten`
  (aus `_plane_bestes_depot` bzw. einer erneuten Hotelbeds-Hotelsuche bei
  All-Inclusive) und `sicherheitshinweis` (aus `ReiseAnfrage.sicherheit_
  ist_wichtig()`) an `Reiseplan`.
- main.py: der Ende-zu-Ende-Durchlauf (AP9) ist bislang nur manuell
  verifiziert, nicht als eigener pytest-Test formalisiert.
- src/fragekatalog/llm_interpreter.py + chat.py + vorschlaege.py: die echte
  LLM-Anbindung (Claude Agent SDK) ist bewusst NICHT in der automatisierten
  Suite, da jeder Aufruf reale Kosten/Zeit gegen das Claude-Abo verursacht.
  Verifiziert wurde sie stattdessen zweimal manuell:
    1) `interpretiere` (b3): vier Szenarien (klare Antwort, Array in
       Alltagssprache, vage Antwort -> Rückfrage, Abbruchwunsch ohne exaktes
       Schlüsselwort) – alle vier liefen wie erwartet.
    2) Typ-C-Schleife (c1 -> b5 -> gw3): Datenabruf, Vorschlag NUR mit echten
       Mock-Daten, Ablehnung mit Verfeinerungswunsch, anschließende
       Zustimmung – lief End-to-End wie im Prozessmodell vorgesehen.
    3) Korrekturschleife (siehe gwAenderung/bKorrektur im drawio): mitten in
       einer späteren Typ-C-Frage einen Änderungswunsch zu einer FRÜHER
       bestätigten Antwort geäußert (Zielregion) – korrekt erkannt, die
       Zielregion UND die davon abhängige, bereits bestätigte Frage
       (Verkehrsmittel) automatisch neu durchlaufen (inkl. frischem
       c1-Datenabruf zum neuen Ziel), danach korrekt zur ursprünglich
       unterbrochenen Frage zurückgekehrt und zur nächsten Katalogfrage
       weitergerückt.
    4) All-Inclusive-Pfad (F15 unterkunft_anforderungen -> F13 verkehrsmittel_
       praeferenz erneut -> F16 aktivitaeten_interessen): All-Inclusive-Wunsch
       bei F15 korrekt erkannt, echtes (Fake-)Hotelbeds-Hotel vorgeschlagen und
       bestätigt; F13 (bereits VOR F15 im Katalog beantwortet, siehe katalog.py)
       automatisch neu durchlaufen und bot dabei einen Flug DIREKT an, ohne
       erst eine Alternativregion vorzuschlagen; F16 hat "Wellness" korrekt
       als bereits im Paket enthalten erkannt (nur "Kultur"/"Museen" landeten
       in `aktivitaeten_noch_per_poi_zu_planen`).
  Bekannter Fallstrick, gegen den `_normalisiere_wert` absichert: das Modell
  gab ein Array im ersten Smoke-Test einmal als JSON-String statt als echtes
  Array zurück, obwohl das JSON-Schema `type: array` vorgab.
    5) `formuliere_frage`/`ueberspringbar` (siehe katalog.py, nur F11
       sicherheitsbeduerfnis): Zielregion "Mexiko" (breites Land) -> Frage
       wurde gestellt (sogar kontextualisiert: "Verhältnisse unterscheiden
       sich je nach Region"); Zielregion "Innsbruck" (konkreter, bekannter
       Ort) -> Frage korrekt übersprungen (`formuliere_frage` gab `None`
       zurück, kein Prompt an den Nutzer).
- src/fragekatalog/regelwerk.py: nur indirekt über den chat.py-Smoke-Test
  verifiziert (kein eigener Test für den generierten Text).
- src/audio/ (Sprachausgabe, Spracheingabe, kanal.py): NICHT in der
  automatisierten Suite (braucht echte Audio-Hardware + die optionalen
  Pakete aus requirements-audio.txt). Manuell verifiziert: TTS spricht
  hörbar über die echten Lautsprecher, STT nimmt vom echten Mikrofon auf und
  transkribiert fehlerfrei (Whisper-Modell 'base', deutsche Windows-Stimme
  "Hedda" gefunden und ausgewählt). Ein TTS->STT-Rundlauf-Test (Testsatz
  synthetisiert, zurücktranskribiert) ergab eine nahezu perfekte Übereinstimmung.
  Ausschließlich mechanisch getestet, nicht inhaltlich mit echten Nutzer-
  Gesprächen über den vollen 18-Fragen-Katalog.

tests/test_vertraeglichkeit.py (neu), tests/test_reiseplan.py (Ergänzung),
tests/test_vorschlaege.py (Ergänzung), tests/test_fragekatalog.py (Ergänzung),
tests/test_google_maps.py (Ergänzung) — "grobe Struktur statt fertiger Plan" + harte
Einschränkungs-Prüfung (2026-08-10). KEIN eigener test_pipeline.py: pipeline.py wird weiterhin
nur indirekt über main.py (Smoke-Test) und die Unit-Tests seiner Bausteine abgedeckt.
--------------------------------------------------------------------------------
Zwei zusammenhängende, in derselben Sitzung entstandene Änderungen (siehe Projektkonversation):

1) "Ich möchte nicht, dass am Ende eine vollkommen fertig geplante Reise entsteht ... eine grobe
   Struktur liefern, er trifft dann Entscheidungen": Optimierung 1 (TOPTW/ILS) bleibt UNVERÄNDERT
   (liefert weiterhin genau EINE realisierbare, zeitfenstergeprüfte Tagesroute je Tag – bewusste
   Entscheidung, siehe Nutzerantwort auf die Rückfrage: "Algorithmus bleibt gleich, nur Ausgabe wird
   ergänzt"). Neu ist NUR die Ausgabe (src/ausgabe/reiseplan.py):
   - `Reiseplan.weitere_aktivitaeten_empfehlungen`: POIs aus dem Kandidaten-Pool (`pois` in
     pipeline.py), die NICHT in die gewählte Tagesroute übernommen wurden (Zeitfenster/Budget hat
     nicht für alle gereicht) – werden NICHT verworfen, sondern als frei kombinierbare Zusatz-
     Empfehlungen mitgegeben (einfache Mengendifferenz `pois` minus tatsächlich besuchte POI-IDs
     über alle Tage, siehe pipeline.py `plane_reise`).
   - Einleitungstext (`_EINLEITUNG` in reiseplan.py) + "Tag X – unser Vorschlag" statt "Tag X:" +
     "unsere Empfehlung unter mehreren geprüften Kandidaten" statt "von Optimierung 1 gewählt":
     reine Framing-/Textänderung, keine Datenänderung – macht deutlich, dass es sich um EINEN
     plausiblen Vorschlag handelt, nicht um eine feste Buchung.
   - Unterkunft war bereits vorher so gelöst (alle Kandidaten in der Mail, siehe ältere Sitzung) –
     laut Nutzerantwort bewusst unverändert gelassen ("Bleibt wie jetzt").
   test_reiseplan.py: neue Tests für Einleitungstext, "unser Vorschlag"-Überschrift, Rendering von
   `weitere_aktivitaeten_empfehlungen` (Text + HTML, inkl. Maps-Link) und `einschraenkungshinweise`.

2) "Wenn ich Fischallergie angebe, soll kein Fischrestaurant vorgeschlagen werden ... das soll für
   den barrierefreien Prozess genauso gelten": neues Modul src/datenaufbereitung/
   vertraeglichkeit.py – harte Ausschlusskriterien, bewusst GETRENNT von aufbereitung.py::
   waehle_top_pois (dort geht es um weiche Präferenz-GEWICHTUNG, hier um harte Ausschlüsse). Läuft
   NACH der POI-/Unterkunft-Suche (c1), VOR dem Präferenz-Scoring, sowohl in der Chat-Vorschau
   (vorschlaege.py `hole_echte_daten_fuer_vorschlag`) als auch in der finalen Planung
   (pipeline.py `plane_reise` und `_plane_bestes_depot`), damit beide dieselben Kandidaten sehen.
   - Ernährung (F18 `ernaehrung_einschraenkungen`): NAMENSBASIERTE Schlüsselwort-Heuristik (z.B.
     "Fischallergie" im Nutzertext + "fisch"/"sushi"/"seafood" im POI-Namen) – bewusst konservativ,
     da keine der angebundenen APIs Zutaten-/Allergendaten liefert (Grundprinzip 1). KEIN Ersatz
     für eine Rückfrage vor Ort.
   - Barrierefreiheit (F09/F10/F15, siehe schema.py `barrierefreiheit_oder_eingeschraenkt` –
     ursprünglich hier per Schlüsselwortliste erkannt, seit Phase 41 liefert stattdessen
     `mobilitaetseinschraenkung_stufe` ("leicht"/"mittel"/"stark", seit Phase 42 gestuft statt nur
     ein Bool), ein vom LLM aus dem Gesprächskontext gesetztes Tool-Argument, siehe
     tests/test_agent_tools.py/test_fragekatalog.py/test_vertraeglichkeit.py): ECHTES,
     strukturiertes Feld statt Heuristik – `GoogleMapsClient.ist_barrierefrei` fragt
     `wheelchair_accessible_entrance` per Place Details (Legacy) ab (Feld verifiziert gegen die
     offizielle Doku: Basic-Feldkategorie, NICHT in Nearby Search enthalten, daher ein separater
     Aufruf NUR bei genanntem Bedarf, nicht automatisch für jeden Treffer – Kostengründe). Fehlt
     das Feld in der Antwort, wird `None` ("keine Angabe") zurückgegeben statt eine Aussage zu
     erfinden. `MockGoogleMapsClient.ist_barrierefrei` nutzt eine feste Demo-Zuordnung
     (mock_data.py `BEISPIEL_BARRIEREFREIHEIT`) mit allen drei Zuständen (True/False/None).
   - Ausschluss NUR, wenn danach noch mind. ein unbedenklicher Kandidat DERSELBEN Kategorie übrig
     bleibt (POIs: `kategorie`; Unterkünfte: alle in einer Gruppe) – sonst wird der einzige Treffer
     behalten, aber `Reiseplan.einschraenkungshinweise` bekommt einen Warnhinweis (kein
     Verschweigen des Konflikts, aber auch kein Erfinden einer nicht existierenden Alternative,
     Grundprinzip 1). In der Chat-Vorschau laufen dieselben Hinweise als "HINWEIS AN DICH (LLM)"-
     Zeilen mit (siehe vorschlaege.py `_mit_hinweisen`), analog zum bestehenden Mechanismus für
     "bereits im All-Inclusive-Paket enthalten".
   Live verifiziert (Mock-Modus, main.py-artiger Smoke-Test): ein POI mit fest hinterlegtem
   `barrierefrei=False` (mock-poi-8 "Biergarten") wurde bei genanntem Rollstuhlbedarf korrekt aus
   den Kandidaten entfernt (Alternative derselben Kategorie "kulinarik" war vorhanden), ohne
   genannten Bedarf blieb er unverändert Teil des Vorschlags.

tests/test_aufbereitung.py, tests/test_google_maps.py, tests/test_reiseplan.py (je Ergänzung) —
Lokaler Fahrzeugwechsel + Verleih-Suche (2026-08-10, Phase 7 im ENTSCHEIDUNGSLOG)
--------------------------------------------------------------------------------
- test_erkenne_leihwunsch_*: regelbasierte Erkennung, ob die BESTÄTIGTE F14-Antwort einen Wunsch
  nach einem vor Ort geliehenen Fahrzeug ausdrückt (Schlüsselwort "ausleihen"/"leihen"/"mieten"/
  "verleih" + Fahrzeug "Fahrrad"/"Auto"). Bewusst KEIN Test dafür, dass die Frage im Dialog
  nachhakt – das ist reine LLM-Prompterei (katalog.py F14 `kontext_hinweis`, verglichen mit
  `bereits_erfasst` aus llm_interpreter.py), nicht deterministisch per pytest testbar (analog zu
  F16s Vertiefungslogik, siehe oben – auch dort nur per Live-Smoke-Test verifiziert).
- test_waehle_place_types_erkennt_fahrzeugverleih_kategorien: "Autoverleih" -> "car_rental" (echter
  Google Place Type), "Fahrradverleih" -> "bicycle_store" (kein eigener Verleih-Typ vorhanden,
  bewusste Grundprinzip-1-Einschränkung, siehe google_maps.py-Kommentar dort).
- test_als_text_zeigt_gefundenen_verleih_mit_link / ..._ohne_treffer_zeigt_ehrliche_fehlanzeige:
  `Reiseplan.lokales_leihfahrzeug_gewuenscht`/`lokaler_verleih_poi` werden zu einem fertigen Satz
  (Fund mit Maps-Link ODER ehrliche Fehlanzeige) – nie ein erfundener Verleih.

tests/test_aufbereitung.py, tests/test_google_maps.py, tests/test_toptw.py (je Ergänzung) — Gym-
Fehltreffer bei Klettern-Suche + maximale Aktivitätszeit pro Tag (2026-08-11)
--------------------------------------------------------------------------------
- BEHOBENER BUG (siehe Projektkonversation: "wieso wird mir da ein Gym rausgesucht?"): Google Places
  kennt keinen eigenen Place Type für Kletterhallen, nur "gym" – geteilt mit normalen
  Fitnessstudios. Ein POI mit `kategorie="gym"` matchte bisher JEDES Klettern-Interesse, unabhängig
  vom Namen. Fix in `aufbereitung.py::_kategorie_passt_zu_praeferenz`: für die unpräzisen
  Schlüsselwörter "klettern"/"kletterhalle"/"bouldern"/"climbing" wird zusätzlich verlangt, dass der
  POI-NAME selbst auf Klettern/Bouldern hindeutet – für andere auf "gym" zeigende Präferenzen (z.B.
  "Sport") bleibt ein normales Fitnessstudio weiterhin ein gültiger Treffer (keine pauschale
  "gym"-Sperre). Ergänzend lenkt `google_maps.py::suche_pois` die echte Places-Suche bei einer
  Klettern-bedingten "gym"-Suche zusätzlich über ein `keyword` Richtung Kletter-/Boulderhallen
  (verbessert die TREFFERQUOTE, ersetzt aber nicht die harte Namensprüfung). Neue Mock-Fixtures
  (mock_data.py, id=13/14): "Fitnessstudio PowerFit" (muss ausgefiltert werden) vs. "Boulderhalle
  Nordwand" (muss durchgehen), beide mit `kategorie="gym"`. Live per Mock-Smoke-Test verifiziert:
  das generische Fitnessstudio taucht bei einem Klettern-Interesse nirgends mehr auf (weder
  eingeplant noch als "weitere Empfehlung"), die Boulderhalle schon.
- BEHOBENER BUG (siehe Projektkonversation: "da wurden zehn Stunden Aktivitäten geplant, das macht
  ja keiner"): `TOPTWInstanz` bekommt ein neues Feld `max_aktivitaetszeit_minuten` (Default sehr
  groß = keine Einschränkung, damit bestehende Aufrufer/Tests unverändert funktionieren) – neue
  harte Nebenbedingung in `toptw.py::simuliere_route`, geprüft ZUSÄTZLICH zum bisherigen
  `tagesbudget_minuten` (das Fahrzeit einschließt). `config.py`: `STANDARD_TAGESBUDGET_MINUTEN`
  600->480 (8h inkl. Fahrzeit), neu `MAX_AKTIVITAETSZEIT_MINUTEN=360` (6h reine Besuchszeit) – auch
  in `.env`/`.env.example` aktualisiert. Live per Mock-Smoke-Test verifiziert: ein Tag, der ohne die
  Grenze >6h reine Aktivitätszeit bekommen hätte (5 POIs, insgesamt 300+ Minuten Besuchszeit an
  einem einzelnen Tag bei einer 5-Tage-Reise), blieb nach dem Fix in jedem Tag unter der 360-
  Minuten-Grenze.

tests/test_agent_tools.py (neu), tests/test_fragekatalog.py (stark gekürzt) — Architekturwechsel
LLM-autonome Dialogsteuerung (2026-08-11, Phase 10 im ENTSCHEIDUNGSLOG)
--------------------------------------------------------------------------------
`zustandsmaschine.py`/`llm_interpreter.py` (Dialogschleife, RegelbasierterInterpreter,
ClaudeAntwortInterpreter) wurden komplett entfernt und durch fünf LLM-Werkzeuge ersetzt (siehe
src/fragekatalog/agent_tools.py). test_agent_tools.py testet diese Werkzeuge DIREKT über die
rohen `SdkMcpTool.handler`-Coroutinen (kein SDK-Server/keine echte LLM-Session nötig) – deckt ab:
Typvalidierung in `speichere_feld` (inkl. Ablehnung bei Typ-Mismatch/unbekanntem Feld, inkl. der
feldspezifischen Sonderfälle All-Inclusive-Erkennung und `aktivitaeten_noch_per_poi_zu_planen`),
`hole_api_daten`s Beschränkung auf Typ-C-Felder, die deterministische `fehlende_pflichtfelder()`-
Prüfung, und vor allem `plane_reise_und_abschliessen()`s harte Sperre (schlägt fehl, solange
Pflichtfelder offen sind; ruft bei Vollständigkeit `pipeline.py::plane_reise` – dort mit
`unittest.mock.patch` ersetzt, um keine echte Optimierung/Datei-/Mail-I/O im Unit-Test
auszulösen). test_fragekatalog.py behält nur noch die von der Ablaufsteuerung unabhängigen Tests
(Katalog/Schema-Konsistenz, `sicherheit_ist_wichtig`/`barrierefreiheit_wichtig`) – Gesprächs-
verhalten (welche Frage das LLM wann stellt/überspringt) ist bewusst NICHT mehr per pytest
testbar, nur noch per echtem Live-Lauf (siehe ENTSCHEIDUNGSLOG.md, Phase 10, akzeptierter
Kompromiss).

tests/test_pipeline.py (neu), tests/test_aufbereitung.py + test_reiseplan.py + test_agent_tools.py
(je Ergänzung) — Nachbesserungen nach erstem Live-Test (2026-08-11, Phase 11 im ENTSCHEIDUNGSLOG)
--------------------------------------------------------------------------------
- test_pipeline.py::test_nur_bestaetigte_verkehrsmittel_*: Regression für den Verkehrsmittel-Bug
  (bestätigtes "Auto" muss "Bahn" mit besserem Score schlagen, unbekannter Freitext fällt auf alle
  Alternativen zurück statt abzustürzen).
- test_vorschlaege.py::test_aktivitaeten_aktuell_wird_fuer_die_suche_verwendet /
  test_agent_tools.py::test_hole_api_daten_gibt_aktivitaeten_aktuell_an_die_suche_weiter:
  Regression für den Restaurant/Café-Bug (leere `anfrage.aktivitaeten_interessen` beim ersten
  Durchlauf darf nicht mehr zu einer leeren Kategoriensuche führen).
- test_aufbereitung.py::test_wende_tageszeitfenster_an_*/test_parameter_fuer_tagesablauf_*: neue
  F20-Logik (Tageszeitfenster relativ zum Tagesbeginn, Start-/Enduhrzeit-Parser, beides mit
  dokumentierten Standardannahmen ohne Angabe).
- test_reiseplan.py::test_als_text_mit_tagesstart_minuten_*: echte Uhrzeiten NUR ab Tag 2 UND nur
  wenn `tagesstart_minuten` gesetzt ist – Tag 1 bleibt in JEDEM Fall relativ (kein HH:MM-Muster).
- test_reiseplan.py::test_speichere_poi_uebersicht_*: CSV-Export enthält sowohl eingeplante als
  auch nicht eingeplante Kandidaten mit Score/Zeitfenster/Tag-Status.

tests/test_vorschlaege.py (stark gekürzt), tests/test_agent_tools.py (Ergänzung) — Keine Hotel-/
POI-Auswahl mehr im Chat (2026-08-12, Phase 29 im ENTSCHEIDUNGSLOG)
--------------------------------------------------------------------------------
F15 (unterkunft_anforderungen) und F16 (aktivitaeten_interessen) sind keine Typ-C-Felder mehr
(siehe katalog.py) – die zugehörigen Codezweige in `vorschlaege.py::hole_echte_daten_fuer_vorschlag`
(Chat-Vorschau, Kandidaten-Kappung, Warnschwellen-Rückfrage, Anfahrtsempfehlung je POI) wurden
ersatzlos entfernt, damit auch die 17 Tests, die ausschließlich diese Zweige prüften. Verbleibt in
test_vorschlaege.py: verkehrsmittel_praeferenz (weiterhin Typ C), `ist_all_inclusive_wunsch`,
`trenne_bereits_im_paket_enthalten` (weiterhin direkt von agent_tools.py::speichere_feld gebraucht,
unabhängig von einer Chat-Vorschau). test_agent_tools.py: ein Test ersetzt (prüft jetzt, dass
`hole_api_daten` für `aktivitaeten_interessen` ablehnt, statt die entfernte Weiterleitung von
`aktivitaeten_aktuell` zu prüfen). Die tatsächliche Auswahl-Logik (`pipeline.py::
_plane_bestes_depot`, `aufbereitung.py::waehle_top_pois`) ist unverändert und bleibt indirekt über
pruefe_planung.py-artige Smoke-Tests abgedeckt, nicht über eigene Unit-Tests (wie schon vorher,
siehe oben).
"""

"""
Bereitet die im Dialog erhobenen Daten für Optimierung 1 auf (siehe
CLAUDE.md, "Optimierung 1 – Vor-Ort-Planung"): POI-Scores aus Präferenz-
Matching und Zusammenstellung des TOPTW-Eingabeformats (Depot, Zeitbudget
je Tag, Tagesanzahl).
"""
from __future__ import annotations

import math
import re
from dataclasses import replace

from src.api.google_maps import MapsClient, mindest_tageszeit_fuer_typ
from src.api.typen import POI
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.toptw import TOPTWInstanz

_TAGE_MUSTER = re.compile(r"(\d+)\s*tag", re.IGNORECASE)

# Lokaler-Transport-Freitext (F14, siehe katalog.py) -> (Geschwindigkeit
# km/h, POI-Suchradius Meter) – siehe Projektkonversation: "wenn ich angebe,
# ich möchte mich vor Ort mit dem Fahrrad fortbewegen, dann sollte auch
# Sachen in Fahrradnähe rausgesucht werden". Geschwindigkeiten grobe,
# literaturunabhängige Richtwerte (analog zu google_maps.py
# `_GESCHWINDIGKEIT_KMH_JE_MODUS`, dort für Anfahrtsempfehlungen statt für
# Optimierung 1 – bewusst zwei kleine Konstanten statt eines Cross-Layer-
# Imports, siehe vorschlaege.py-Kommentar zu `_MAX_UNTERKUNFT_KANDIDATEN`).
# Kein Eintrag -> Fußweg-Default (konservativste, bisherige Annahme). Dritter Wert = Google
# Distance-Matrix-`mode` (siehe `modus_fuer_lokalen_transport`) – dieselbe Schlüsselwort-Tabelle,
# EINE Zuordnung statt zwei potenziell abweichender (Geschwindigkeit UND Modus gehören fachlich
# zusammen, siehe Projektkonversation: "die Zeiten sind falsch" / CLAUDE.md "Zentrale Anpassung").
_TRANSPORT_PARAMETER: dict[str, tuple[float, int, str]] = {
    "fahrrad": (15.0, 8000, "bicycling"), "rad": (15.0, 8000, "bicycling"),
    "bike": (15.0, 8000, "bicycling"), "fahrradfahren": (15.0, 8000, "bicycling"),
    "auto": (40.0, 15000, "driving"), "wagen": (40.0, 15000, "driving"), "pkw": (40.0, 15000, "driving"),
    "öffentlich": (25.0, 8000, "transit"), "bus": (25.0, 8000, "transit"), "bahn": (25.0, 8000, "transit"),
    "u-bahn": (25.0, 8000, "transit"), "tram": (25.0, 8000, "transit"), "öpnv": (25.0, 8000, "transit"),
    "zu fuß": (4.5, 1500, "walking"), "fuß": (4.5, 1500, "walking"),
    "laufen": (4.5, 1500, "walking"), "fußweg": (4.5, 1500, "walking"),
}
_STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH = 4.5
_STANDARD_TRANSPORT_RADIUS_METER = 3000
_STANDARD_TRANSPORT_MODUS = "walking"


def parameter_fuer_lokalen_transport(lokaler_transport_praeferenz: str | None) -> tuple[float, int]:
    """
    Ermittelt (Geschwindigkeit km/h, POI-Suchradius Meter) aus der Freitext-
    Antwort auf F14. Regelbasiertes Schlüsselwort-Matching statt LLM-
    Erkennung (analog zu vorschlaege.py `ist_all_inclusive_wunsch`) – die
    Entscheidung bleibt damit im deterministischen Layer (CLAUDE.md,
    Grundprinzip 1/3). Ohne Angabe oder unbekannte Formulierung: konservative
    Fußweg-Annahme, wie bisher.
    """
    geschwindigkeit, radius, _ = _parameter_eintrag(lokaler_transport_praeferenz)
    return geschwindigkeit, radius


def modus_fuer_lokalen_transport(lokaler_transport_praeferenz: str | None) -> str:
    """Google-Distance-Matrix-`mode` (siehe `erstelle_toptw_instanz`) – dieselbe Erkennung wie `parameter_fuer_lokalen_transport`."""
    _, _, modus = _parameter_eintrag(lokaler_transport_praeferenz)
    return modus


def _parameter_eintrag(lokaler_transport_praeferenz: str | None) -> tuple[float, int, str]:
    if not lokaler_transport_praeferenz:
        return _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH, _STANDARD_TRANSPORT_RADIUS_METER, _STANDARD_TRANSPORT_MODUS
    text_klein = lokaler_transport_praeferenz.lower()
    for schluesselwort, parameter in _TRANSPORT_PARAMETER.items():
        if schluesselwort in text_klein:
            return parameter
    return _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH, _STANDARD_TRANSPORT_RADIUS_METER, _STANDARD_TRANSPORT_MODUS


# Uhrzeit-Muster für F20 (tagesstart_praeferenz), z.B. "ab 9 Uhr", "09:00", "bis 21 Uhr" –
# absichtlich einfach (siehe `schaetze_reisedauer_tage` für dasselbe Grundmuster: ein robuster
# Regex-Parser statt eine LLM-Extraktion, die im deterministischen Layer nichts zu suchen hat).
_UHRZEIT_MUSTER = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(?:uhr)?")
_STANDARD_TAGESSTART_MINUTEN = 9 * 60  # 09:00 – vorsichtige, dokumentierte Standardannahme
_STANDARD_TAGESENDE_MINUTEN = 21 * 60  # 21:00


def parameter_fuer_tagesablauf(tagesstart_praeferenz: str | None) -> tuple[int, int]:
    """
    Ermittelt (Start, Ende) eines normalen Reisetags in Minuten seit Mitternacht aus der
    Freitext-Antwort auf F20 (siehe katalog.py). Sucht die ERSTE genannte Uhrzeit als Start und
    die LETZTE als Ende (deckt Formulierungen wie "ab 9 bis 21 Uhr" ab); ohne mindestens zwei
    erkennbare Uhrzeiten oder ganz ohne Angabe: konservative Standardannahme (09:00–21:00, siehe
    Projektkonversation – wird NICHT als reale Uhrzeit ausgegeben, siehe reiseplan.py).
    """
    if not tagesstart_praeferenz:
        return _STANDARD_TAGESSTART_MINUTEN, _STANDARD_TAGESENDE_MINUTEN
    treffer = _UHRZEIT_MUSTER.findall(tagesstart_praeferenz)
    uhrzeiten = [
        stunde_min * 60 + minute_min
        for stunde, minute in treffer
        if 0 <= (stunde_min := int(stunde)) <= 23 and 0 <= (minute_min := int(minute or 0)) <= 59
    ]
    if len(uhrzeiten) < 2:
        return _STANDARD_TAGESSTART_MINUTEN, _STANDARD_TAGESENDE_MINUTEN
    start, ende = uhrzeiten[0], uhrzeiten[-1]
    if ende <= start:
        return _STANDARD_TAGESSTART_MINUTEN, _STANDARD_TAGESENDE_MINUTEN
    return start, ende


def wende_tageszeitfenster_an(pois: list[POI]) -> list[POI]:
    """
    Hebt `poi.opening` je nach Place Type auf eine kategoriebezogene Mindest-Tageszeit an (siehe
    google_maps.py `mindest_tageszeit_fuer_typ` – z.B. Bars/Nachtclubs erst spät am Tag, siehe
    Projektkonversation: "ich soll nicht direkt nach dem Aufstehen in die Bar gehen"). Arbeitet
    RELATIV zum jeweiligen Tagesbeginn (egal ob das die tatsächliche Ankunft an Tag 1 oder eine
    spätere, angegebene Startuhrzeit ist) – dadurch bleibt die Regel gültig, ohne eine absolute
    Uhrzeit zu kennen (Grundprinzip 1: keine erfundene Uhrzeit). Gibt NEUE POI-Objekte zurück
    (verändert `pois` nicht in-place), damit dieselbe Kandidatenliste z.B. für "weitere
    Empfehlungen" unverändert weiterverwendet werden kann.
    """
    ergebnis = []
    for poi in pois:
        mindest_tageszeit = mindest_tageszeit_fuer_typ(poi.kategorie)
        if mindest_tageszeit <= poi.opening:
            ergebnis.append(poi)
            continue
        neues_opening = min(mindest_tageszeit, max(poi.opening, poi.closing - poi.required_time))
        ergebnis.append(replace(poi, opening=neues_opening))
    return ergebnis


# Schlüsselwörter, die einen Leihwunsch ausdrücken (siehe Projektkonversation: "wenn ich mitm Auto
# hinfahre und dann sage, ich möchte vor Ort mitm Fahrrad fahren, dann musst du nachfragen ... und
# wenn er das bestätigt, [nach einem Verleih] gucken"). Der eigentliche Dialog (LLM, siehe katalog.py
# F14 `kontext_hinweis`) erkennt den ANLASS (Fahrzeugwechsel gegenüber der Anreise) und fragt nach;
# diese Funktion liest nur noch das ERGEBNIS dieser Nachfrage aus der final bestätigten F14-Antwort
# heraus – bewusst regelbasiert statt LLM-Erkennung (CLAUDE.md Grundprinzip 1/3), analog zu
# `ist_all_inclusive_wunsch` (vorschlaege.py).
_LEIHWUNSCH_SCHLUESSELWOERTER = ("ausleihen", "ausgeliehen", "leihen", "geliehen", "mieten", "gemietet", "verleih")
_FAHRZEUG_SCHLUESSELWOERTER: dict[str, tuple[str, ...]] = {
    "Fahrrad": ("fahrrad", "rad", "bike"),
    "Auto": ("auto", "pkw", "mietwagen", "wagen"),
}


def erkenne_leihwunsch(lokaler_transport_praeferenz: str | None) -> str | None:
    """
    Liefert "Fahrrad"|"Auto", wenn die (finale, bestätigte) F14-Antwort
    erkennbar einen Wunsch nach einem vor Ort GELIEHENEN Fahrzeug ausdrückt,
    sonst None. Wird von pipeline.py genutzt, um danach real nach einem
    Verleih in der Nähe zu suchen (siehe pipeline.py
    `_VERLEIH_KATEGORIE_JE_FAHRZEUG`, google_maps.py `suche_pois`).
    """
    if not lokaler_transport_praeferenz:
        return None
    text_klein = lokaler_transport_praeferenz.lower()
    if not any(schluesselwort in text_klein for schluesselwort in _LEIHWUNSCH_SCHLUESSELWOERTER):
        return None
    for fahrzeug, schluesselwoerter in _FAHRZEUG_SCHLUESSELWOERTER.items():
        if any(schluesselwort in text_klein for schluesselwort in schluesselwoerter):
            return fahrzeug
    return None


# Score eines POIs bei neutralem Gewicht (1.0) – siehe `berechne_poi_score`. Reiner Platzhalterwert
# (kein zitierfähiger Fakt), dient nur als Bezugsgröße für die multiplikative Gewichtung.
_BASIS_SCORE = 3.0


def berechne_poi_score(poi: POI, praeferenzen: list[str], gewichtung: dict[str, float] | None = None) -> float:
    """
    Bewertet einen POI danach, ob `poi.nutzerinteresse` (siehe typen.py – der
    WORTLAUT des Interesses, für das dieser POI gesucht wurde, gesetzt von
    google_maps.py::suche_pois bzw. overpass.py::suche_spezial_pois) unter
    den genannten `praeferenzen` ist. Je mehr passende (und ggf. höher
    gewichtete) Präferenzen, desto höher der Score. Eine einfache,
    transparente Regel – bewusst nicht von einem LLM erzeugt (CLAUDE.md,
    Grundprinzip 1: "Es erstellt NIE selbst die Reise und erfindet NIE
    Fakten").

    ARCHITEKTURWECHSEL (siehe Projektkonversation: "ich möchte klettern und
    nicht ins Gym – das ist auf gar keinen Fall das Gleiche"): Vorher wurde
    HIER, nachträglich, versucht zu erraten, ob `poi.kategorie` (Googles
    rohem Place Type, z.B. "gym") zu einer Freitext-Präferenz (z.B.
    "Klettern") passt – über eine feste, selbst gepflegte Alias-Tabelle plus
    einer Sonderregel für den Fall, dass "gym" sowohl Kletterhallen als auch
    normale Fitnessstudios abdeckt. Das war strukturell fehleranfällig UND
    unwartbar für alles außerhalb einer festen Kategorienliste. Jetzt sucht
    google_maps.py::suche_pois direkt PRO Interesse (Places Text Search mit
    dem Interesse als Freitext-Query) – ein zurückgegebener POI IST also per
    Konstruktion ein Treffer für sein `nutzerinteresse`, hier muss nichts
    mehr geraten werden. Diese Funktion prüft daher nur noch, ob das
    Interesse, für das der POI gefunden wurde, überhaupt noch unter den
    AKTUELL genannten `praeferenzen` ist (relevant z.B. nach einer Korrektur
    im Dialog, bei der ein Interesse wieder verworfen wurde).

    `gewichtung` (optional): relative Wichtigkeit EINZELNER Präferenzen
    (Schlüssel = exakter Präferenz-String aus `praeferenzen`), z.B. wenn der
    Nutzer im Dialog "eher Kultur als Shopping" geäußert hat (siehe
    schema.py `aktivitaeten_gewichtung`). Fehlt eine Präferenz im Dict,
    zählt sie neutral mit Gewicht 1.0.

    MULTIPLIKATIV statt additiv (siehe Projektkonversation: "dem Nutzerkontext entsprechend
    gewichtet werden" – die Gewichtung soll sich tatsächlich spürbar durchsetzen, nicht nur
    marginal): `score = _BASIS_SCORE * gewichtung`. Bei neutralem Gewicht 1.0 unverändert
    `_BASIS_SCORE` (wie bisher); doppeltes Gewicht verdoppelt den Score tatsächlich (statt nur um
    67% zu steigen wie bei der vorherigen additiven Formel `1.0 + gewichtung*2.0`) – setzt sich
    dadurch klarer sowohl bei der Kappung (`waehle_top_pois`) als auch bei der Greedy-Einfüge-
    Priorität (Score/Zusatzzeit-Verhältnis, siehe toptw.py `_greedy_einfuegen`) durch.

    Ein POI ohne passendes `nutzerinteresse` bekommt 0.0 (nicht den
    neutralen Basis-Score) und fällt damit in `waehle_top_pois` heraus,
    statt mit thematisch Unpassendem aufzufüllen (siehe Projektkonversation:
    "er sucht einfach irgendwelche Aktivitäten raus, auch Gym oder Spa,
    obwohl ich das nicht will").
    """
    if not praeferenzen:
        return 1.0  # keine Präferenz angegeben -> alle POIs gleich interessant
    if poi.nutzerinteresse is None or poi.nutzerinteresse not in praeferenzen:
        return 0.0
    return _BASIS_SCORE * (gewichtung or {}).get(poi.nutzerinteresse, 1.0)


def schaetze_reisedauer_tage(reisezeitraum_rohtext: str | None, standard_tage: int = 5) -> int:
    """
    Heuristische Schätzung der Reisedauer aus dem Freitext der Zeitraum-Frage
    (siehe katalog.py, Anmerkung zu F07: das Rohmaterial kombiniert "wie
    lange" und "welcher Zeitraum" in einer einzigen, als "Date" vermerkten
    Frage) – `reisezeitraum_rohtext` wird als reiner Freitext gespeichert
    (Rueckgabetyp.STRING), dieser einfache Regex-Parser liest daraus die
    Anzahl Tage für Optimierung 1/Tests, ohne eine LLM-Anbindung zu
    brauchen.
    """
    if not reisezeitraum_rohtext:
        return standard_tage
    treffer = _TAGE_MUSTER.search(reisezeitraum_rohtext)
    return int(treffer.group(1)) if treffer else standard_tage


# Wie viele POIs Optimierung 1 maximal als Kandidaten bekommt – skaliert mit
# der Reisedauer statt eines festen Werts (siehe Projektkonversation: eine
# 3-Tage-Reise braucht keine 30 Kandidaten, eine 10-Tage-Reise mehr als eine
# feste Kleinzahl). Wird sowohl von der Chat-Vorschau (vorschlaege.py, Knoten
# b5) als auch von der tatsächlichen Optimierung (pipeline.py) verwendet –
# EINE Quelle, damit beide immer denselben Wert nennen/verwenden: wenn der
# Bot im Chat sagt "wir können nicht mehr als X optimieren", muss das auch
# wirklich stimmen.
_POIS_JE_TAG = 4
_MIN_POIS_FUER_OPTIMIERUNG = 8
_MAX_POIS_FUER_OPTIMIERUNG = 30


def max_pois_fuer_reise(anfrage: ReiseAnfrage) -> int:
    """Wie viele POIs Optimierung 1 für diese Reise maximal als Kandidaten bekommt (siehe Kommentar oben)."""
    tage = schaetze_reisedauer_tage(anfrage.reisezeitraum_rohtext)
    return max(_MIN_POIS_FUER_OPTIMIERUNG, min(_MAX_POIS_FUER_OPTIMIERUNG, tage * _POIS_JE_TAG))


def waehle_top_pois(
    pois: list[POI], praeferenzen: list[str], max_anzahl: int, gewichtung: dict[str, float] | None = None
) -> list[POI]:
    """
    Bewertet ALLE Kandidaten (setzt `poi.score`, siehe `berechne_poi_score`)
    und behält die `max_anzahl` besten – NICHT die ersten `max_anzahl` in
    beliebiger Fund-Reihenfolge.

    BEHOBENER BUG (siehe Projektkonversation): pipeline.py kappte vorher VOR
    dem Scoring (`sammle_pois(...)[:max_pois_fuer_reise(anfrage)]`), wodurch
    Präferenzen/Gewichtung faktisch keinen Einfluss darauf hatten, WELCHE
    POIs überhaupt als Kandidaten für Optimierung 1 übrig bleiben – nur noch
    darauf, wie sie unter sich einsortiert werden. Damit eine geäußerte
    Präferenz ("eher Kultur als Shopping") tatsächlich Entscheidungen
    eingrenzt, muss die Auswahl NACH dem Scoring passieren.

    POIs mit Score 0.0 (siehe `berechne_poi_score`: passt zu KEINER genannten
    Präferenz) werden HIER herausgefiltert statt nur ans Ende sortiert – die
    Rückgabe kann also kürzer als `max_anzahl` sein, wenn nicht genug wirklich
    passende POIs gefunden wurden (siehe Projektkonversation: "wenn nicht
    genug in der Nähe da sind, dann werden halt nur die einzelnen
    vorgeschlagen, die auch da sind" statt mit branchenfremden Treffern
    aufzufüllen).
    """
    for poi in pois:
        poi.score = berechne_poi_score(poi, praeferenzen, gewichtung)
    passende_pois = [poi for poi in pois if poi.score > 0]
    return sorted(passende_pois, key=lambda poi: poi.score, reverse=True)[:max_anzahl]


# Schlüsselwörter für die Flexibilitätspräferenz (F05, katalog.py) – bisher abgefragt, aber
# NIRGENDS ausgewertet (siehe Projektkonversation: "Flexibilitätspräferenz soll auch Auswirkungen
# auf die POIs am Tag haben"). Zählt Treffer statt nur den ERSTEN Treffer zu nehmen (siehe
# `max_pois_pro_tag_fuer_flexibilitaet`): bei gemischten Aussagen ("ein fester Plan ist ganz nett,
# aber ich möchte auch spontan sein") heben sich die Signale bewusst auf, statt willkürlich eines
# zu bevorzugen – dann bleibt es bei keiner zusätzlichen Einschränkung.
_FLEXIBEL_SCHLUESSELWOERTER = ("flexibel", "spontan", "locker", "offen", "wenig geplant")
_UNFLEXIBEL_SCHLUESSELWOERTER = ("fest", "durchgeplant", "durchgetaktet", "strukturiert", "genau geplant", "unflexibel")
# Grobe, literaturunabhängige Richtwerte (analog zu den anderen Konstanten in dieser Datei): ein
# flexibler Tag lässt spürbar Luft für Spontanes, ein durchgeplanter Tag ist voller. Kein Eintrag
# in max_pois_fuer_reise() (Gesamt-Kandidatenpool über die ganze Reise) verändert – das hier
# begrenzt zusätzlich, wie viele davon an EINEM TAG landen dürfen.
_POIS_PRO_TAG_FLEXIBEL = 2
_POIS_PRO_TAG_UNFLEXIBEL = 6


def max_pois_pro_tag_fuer_flexibilitaet(flexibilitaet_praeferenz: str | None) -> int | None:
    """
    None (keine zusätzliche Tages-Obergrenze) ohne Angabe ODER bei gemischten/widersprüchlichen
    Signalen – nur bei einem klaren Überhang in eine Richtung wird `TOPTWInstanz.max_pois_pro_tag`
    tatsächlich gesetzt (siehe `erstelle_toptw_instanz`). Bewusst regelbasiertes Schlüsselwort-
    Zählen statt LLM-Einschätzung (CLAUDE.md Grundprinzip 1/3).
    """
    if not flexibilitaet_praeferenz:
        return None
    text_klein = flexibilitaet_praeferenz.lower()
    flexibel_treffer = sum(1 for wort in _FLEXIBEL_SCHLUESSELWOERTER if wort in text_klein)
    unflexibel_treffer = sum(1 for wort in _UNFLEXIBEL_SCHLUESSELWOERTER if wort in text_klein)
    if flexibel_treffer > unflexibel_treffer:
        return _POIS_PRO_TAG_FLEXIBEL
    if unflexibel_treffer > flexibel_treffer:
        return _POIS_PRO_TAG_UNFLEXIBEL
    return None


# Drei Anpassungen für Optimierung 1 bei genannter eingeschränkter Gehfähigkeit (siehe
# schema.py `eingeschraenkte_gehfaehigkeit`, Projektkonversation: "wenn ich angebe, dass ich
# Schwierigkeiten habe zu gehen, dann müssen die Gehzeiten neu berechnet werden, Pausen eingeplant
# werden, dazu sollten POIs die nah am Hotel liegen höher gewichtet werden"). Grobe,
# literaturunabhängige Richtwerte (analog zu den bereits bestehenden Konstanten in dieser Datei),
# keine erfundene Tatsache über eine konkrete Person – nur eine dokumentierte Modellannahme.
#
# 1) Gehzeiten: deutlich langsameres Tempo als der normale Fußweg-Richtwert (4.5 km/h).
_GESCHWINDIGKEIT_EINGESCHRAENKT_KMH = 2.0

# 2) Pausen: alle 2h Aktivität/Fahrzeit eine 20-Minuten-Pause (siehe toptw.py
# `pause_intervall_minuten`/`pause_dauer_minuten`, `simuliere_route`).
_PAUSE_INTERVALL_MINUTEN = 120
_PAUSE_DAUER_MINUTEN = 20

# 3) Nähe zum Depot: Referenzdistanz, bei der der Score-Bonus auf die Hälfte abgefallen ist (siehe
# `gewichte_nach_naehe_zum_depot`) – 1.5 km entspricht einem kurzen, auch mit eingeschränkter
# Gehfähigkeit noch gut machbaren Fußweg.
_REFERENZDISTANZ_NAEHE_KM = 1.5


def gewichte_nach_naehe_zum_depot(pois: list[POI], depot_koordinaten: tuple[float, float]) -> list[POI]:
    """
    Erhöht (nicht-mutierend, `dataclasses.replace`) den Score näher am Depot gelegener POIs relativ
    zu weiter entfernten – NUR aufgerufen, wenn `ReiseAnfrage.eingeschraenkte_gehfaehigkeit()`
    zutrifft (siehe `erstelle_toptw_instanz`). Reine Multiplikation mit einem Distanz-Faktor
    zwischen 0 und 1 (glatt abfallend, kein harter Cutoff): POIs direkt am Depot behalten praktisch
    ihren vollen Score, bei `_REFERENZDISTANZ_NAEHE_KM` ist er auf die Hälfte gefallen. Die
    bestehende Präferenz-Gewichtung (Kategorie-Score, `aktivitaeten_gewichtung`) bleibt dadurch
    RELATIV erhalten – ein Interesse mit doppeltem Score bleibt auch nach der Nähe-Gewichtung
    doppelt so hoch bewertet wie eines ohne, nur beide zusätzlich nach Entfernung skaliert.
    """
    depot_x, depot_y = depot_koordinaten
    gewichtet = []
    for poi in pois:
        distanz_km = math.dist((poi.x, poi.y), (depot_x, depot_y)) * 111
        faktor = _REFERENZDISTANZ_NAEHE_KM / (_REFERENZDISTANZ_NAEHE_KM + distanz_km)
        gewichtet.append(replace(poi, score=poi.score * faktor))
    return gewichtet


def hole_reisezeitmatrix(
    client: MapsClient, depot: POI, pois: list[POI], modus: str
) -> dict[tuple[int, int], int]:
    """
    Ruft EINMAL die echte Google-Distance-Matrix (`MapsClient.distanzmatrix`) für Depot + alle
    `pois` ab und baut daraus ein `(id_a, id_b) -> Minuten`-Lookup für `TOPTWInstanz.
    reisezeiten_minuten` (siehe dort und CLAUDE.md "Zentrale Anpassung": "Distanzberechnung aus
    Koordinaten (Luftlinie) durch echte Reisezeiten aus der Google Distance Matrix ersetzen").

    UMSETZUNG (siehe Projektkonversation: "die Zeiten sind falsch" – Luftlinie ignoriert
    Straßennetz/Umwege komplett, ILS wählte dadurch unrealistisch kurze Wegzeiten): EIN
    NxN-Aufruf statt vieler Einzelaufrufe (`distanzmatrix` existierte bereits, war aber nie mit
    Optimierung 1 verdrahtet). Fehlt für ein Paar eine Route (-1, siehe google_maps.py), wird
    dieses Paar NICHT in die Matrix aufgenommen – `TOPTWInstanz.reisezeit_minuten` fällt dann NUR
    für dieses eine Paar auf die Luftlinien-Schätzung zurück, statt eine erfundene Zeit einzutragen
    (Grundprinzip 1) oder die gesamte Planung abzubrechen.

    Bewusst NICHT über die Depot-Kandidaten hinweg gecacht (siehe pipeline.py
    `_plane_bestes_depot`, ruft diese Funktion einmal PRO Unterkunfts-Kandidat auf) – die
    POI-zu-POI-Distanzen wären zwar identisch, aber die Kandidatenmenge ist mit maximal
    `_MAX_UNTERKUNFT_KANDIDATEN` (5) klein genug, dass der Mehraufwand die zusätzliche
    Code-Komplexität eines Caches aktuell nicht rechtfertigt (offener Optimierungspunkt, siehe
    ENTSCHEIDUNGSLOG.md).
    """
    alle_orte = [depot] + pois
    minuten_matrix = client.distanzmatrix([(ort.x, ort.y) for ort in alle_orte], modus=modus)
    reisezeiten: dict[tuple[int, int], int] = {}
    for i, von in enumerate(alle_orte):
        for j, nach in enumerate(alle_orte):
            if i == j or i >= len(minuten_matrix) or j >= len(minuten_matrix[i]):
                continue
            minuten = minuten_matrix[i][j]
            if minuten is not None and minuten >= 0:  # -1 = keine Route gefunden (siehe google_maps.py)
                reisezeiten[(von.id, nach.id)] = minuten
    return reisezeiten


def erstelle_toptw_instanz(
    anfrage: ReiseAnfrage,
    pois: list[POI],
    standard_tagesbudget_minuten: int,
    depot_koordinaten: tuple[float, float],
    depot_name: str = "Unterkunft",
    max_aktivitaetszeit_minuten: int = 10**9,
    client: MapsClient | None = None,
) -> TOPTWInstanz:
    """
    Führt Fragekatalog-Antworten und POI-Liste zur TOPTW-Eingabe zusammen.

    `pois` müssen bereits bewertet UND ausgewählt sein (siehe
    `waehle_top_pois`) – diese Funktion scort nicht mehr selbst, damit
    Scoring+Auswahl nur EINMAL passiert, auch wenn `pipeline.py::
    _plane_bestes_depot` diese Funktion mehrfach aufruft (einmal je
    Unterkunfts-Kandidat).

    `depot_koordinaten` MUSS in der Nähe der `pois` liegen (z.B. die
    geokodierte Zielregion oder eine konkrete Unterkunft, siehe pipeline.py::
    _plane_bestes_depot) – ohne diese Angabe würde das Depot beim
    TOPTWInstanz-Default auf (0, 0) stehen, wodurch jede Anreise zu einem POI
    unrealistisch lang würde und de facto nie ein POI eingeplant werden könnte.

    `max_aktivitaetszeit_minuten` (siehe TOPTWInstanz-Doku, config.py
    `EINSTELLUNGEN.max_aktivitaetszeit_minuten`): reine Besuchszeit-Obergrenze
    OHNE Fahrzeit, härter als `standard_tagesbudget_minuten`. Default sehr
    groß (= keine Einschränkung), damit Aufrufer ohne explizite Angabe (z.B.
    ältere Tests) unverändert funktionieren.

    Bei genannter `anfrage.eingeschraenkte_gehfaehigkeit()` (siehe schema.py, Projektkonversation:
    "Gehzeiten neu berechnen, Pausen einplanen, POIs nah am Hotel höher gewichten") drei
    Anpassungen (siehe Konstanten oben `erstelle_toptw_instanz`): langsamere Geschwindigkeit NUR
    wenn ohnehin zu Fuß unterwegs (ein bestätigtes Auto/ÖPNV-Tempo wird nicht "verlangsamt" – die
    Person sitzt ja nicht zu Fuß in der Bahn), Pausen-Intervall in der `TOPTWInstanz`, und eine
    Nähe-Gewichtung der `pois` VOR dem Zeitfenster-Schritt.

    `anfrage.flexibilitaet_praeferenz` (F05, siehe `max_pois_pro_tag_fuer_flexibilitaet`) setzt bei
    klarem Signal ("eher flexibel"/"fest durchgeplant") eine zusätzliche Tages-Obergrenze für die
    reine ANZAHL POI-Besuche – unabhängig vom verbleibenden Zeitbudget.

    `client` (optional, siehe `hole_reisezeitmatrix`): mit Angabe werden ECHTE Reisezeiten (Google
    Distance Matrix) für Depot+POIs vorab abgerufen und in `TOPTWInstanz.reisezeiten_minuten`
    hinterlegt – ohne Angabe (Default `None`, z.B. ältere Tests) bleibt es bei der
    Luftlinien-Schätzung (`TOPTWInstanz.reisezeit_minuten`-Fallback).
    """
    # Der Fragekatalog enthält aktuell kein eigenes Feld für das tägliche
    # Zeitbudget (siehe katalog.py) – daher der Konfigurations-Default.
    tagesbudget = standard_tagesbudget_minuten
    tage = schaetze_reisedauer_tage(anfrage.reisezeitraum_rohtext)

    depot_x, depot_y = depot_koordinaten
    depot = POI(
        id=0, name=depot_name, kategorie="depot", x=depot_x, y=depot_y,
        score=0.0, required_time=0, opening=0, closing=24 * 60,
    )
    geschwindigkeit_kmh, _ = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    modus = modus_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    pause_intervall_minuten = None
    eingeplante_pois = pois
    if anfrage.eingeschraenkte_gehfaehigkeit():
        if geschwindigkeit_kmh == _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH:
            geschwindigkeit_kmh = _GESCHWINDIGKEIT_EINGESCHRAENKT_KMH
        pause_intervall_minuten = _PAUSE_INTERVALL_MINUTEN
        eingeplante_pois = gewichte_nach_naehe_zum_depot(pois, depot_koordinaten)
    eingeplante_pois = wende_tageszeitfenster_an(list(eingeplante_pois))
    reisezeiten_minuten = hole_reisezeitmatrix(client, depot, eingeplante_pois, modus) if client is not None else None
    max_pois_pro_tag = max_pois_pro_tag_fuer_flexibilitaet(anfrage.flexibilitaet_praeferenz)
    return TOPTWInstanz(
        pois=eingeplante_pois, tagesbudget_minuten=tagesbudget, anzahl_tage=tage,
        depot=depot, geschwindigkeit_kmh=geschwindigkeit_kmh, max_aktivitaetszeit_minuten=max_aktivitaetszeit_minuten,
        pause_intervall_minuten=pause_intervall_minuten, pause_dauer_minuten=_PAUSE_DAUER_MINUTEN,
        reisezeiten_minuten=reisezeiten_minuten, max_pois_pro_tag=max_pois_pro_tag,
    )

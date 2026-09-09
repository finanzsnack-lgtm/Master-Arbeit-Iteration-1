"""
Bereitet die im Dialog erhobenen Daten für Optimierung 1 auf (siehe
CLAUDE.md, "Optimierung 1 – Vor-Ort-Planung"): POI-Scores aus Präferenz-
Matching und Zusammenstellung des TOPTW-Eingabeformats (Depot, Zeitbudget
je Tag, Tagesanzahl).
"""
from __future__ import annotations

import datetime
import math
import re
from dataclasses import replace

from src.api.google_maps import MapsClient, mindest_tageszeit_fuer_typ
from src.api.typen import POI
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.toptw import TOPTWInstanz, Tagesroute

_TAGE_MUSTER = re.compile(r"(\d+)\s*tag", re.IGNORECASE)

# Erkennt Datumsbereiche wie "21.8. bis 1.9." oder "21.8.-1.9.2026" im F07-Freitext – das Jahr ist
# an BEIDEN Enden optional (Live-Vorfall: eine 15-tägige Reise "vom 1. bis 15." wurde auf den
# Standardwert 5 Tage zurückgestuft, weil `_TAGE_MUSTER` nur "X Tage"-Formulierungen erkennt, keine
# Datumsbereiche – Rückfrage-Ergebnis: "21.8. bis 1.9." muss erkannt werden, OHNE dass zusätzlich
# ein Jahr angegeben werden muss).
_DATUM_BEREICH_MUSTER = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})?\s*(?:bis(?:\s+zum)?|-|–)\s*(\d{1,2})\.(\d{1,2})\.(\d{4})?"
)

# Lokaler-Transport-Freitext (F14, siehe katalog.py) -> (Geschwindigkeit km/h, POI-Suchradius
# Meter, Google-Distance-Matrix-`mode`) – EINE gemeinsame Zuordnung für alle drei Werte
# (Geschwindigkeit, Radius und Modus gehören fachlich zusammen), analog zu google_maps.py
# `_GESCHWINDIGKEIT_KMH_JE_MODUS` (dort nur für Anfahrtsempfehlungen, nicht für Optimierung 1).
# Kein Eintrag -> Fußweg-Default (konservativste Annahme).
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
    Ermittelt (Geschwindigkeit km/h, POI-Suchradius Meter) aus der Freitext-Antwort auf F14.
    Regelbasiertes Schlüsselwort-Matching statt LLM-Erkennung – die Entscheidung bleibt damit im
    deterministischen Layer (CLAUDE.md, Grundprinzip 1/3). Ohne Angabe oder unbekannte
    Formulierung: konservative Fußweg-Annahme.

    Werden MEHRERE Verkehrsmittel genannt (siehe `modi_fuer_lokalen_transport`), bestimmt weiterhin
    das ZUERST erkannte die Geschwindigkeit (unverändertes Verhalten für den häufigen Ein-Modus-
    Fall), der Suchradius nimmt dagegen den GRÖSSTEN unter den genannten Optionen – ein genanntes
    Auto soll die POI-Suche nicht künstlich auf Fußweg-Reichweite einschränken, nur weil zusätzlich
    auch "zu Fuß" erwähnt wurde.
    """
    treffer = _gefundene_eintraege(lokaler_transport_praeferenz)
    geschwindigkeit = treffer[0][0]
    radius = max(eintrag[1] for eintrag in treffer)
    return geschwindigkeit, radius


def modi_fuer_lokalen_transport(lokaler_transport_praeferenz: str | None) -> list[str]:
    """
    Google-Distance-Matrix-`mode`-Werte ALLER in F14 genannten Verkehrsmittel (dedupliziert,
    Reihenfolge = zuerst erkannt zuerst) – anders als eine frühere Version, die beim ERSTEN Treffer
    abbrach (siehe ENTSCHEIDUNGSLOG.md: "wenn er sagt Fahrrad und Öffis, dann werden Öffis UND
    Fahrrad ausgegeben, und dann wird das genommen, was schneller ist"). Welches der genannten
    Verkehrsmittel für ein KONKRETES Etappenpaar tatsächlich schneller ist, entscheidet NICHT diese
    Funktion, sondern die echte Reisezeit je Modus (siehe `hole_reisezeitmatrix`/
    `ergaenze_anfahrt_modus_je_etappe`). Ohne erkennbares Verkehrsmittel: `["walking"]`.
    """
    return [eintrag[2] for eintrag in _gefundene_eintraege(lokaler_transport_praeferenz)]


def _gefundene_eintraege(lokaler_transport_praeferenz: str | None) -> list[tuple[float, int, str]]:
    """
    Alle (Geschwindigkeit, Radius, Modus)-Einträge aus `_TRANSPORT_PARAMETER`, deren Schlüsselwort
    im Text vorkommt – dedupliziert nach Modus (mehrere Schlüsselwörter können auf denselben Modus
    zeigen, z.B. "fahrrad"/"rad"/"bike"), sortiert nach der Position des jeweils FRÜHESTEN Treffers
    IM TEXT (nicht nach der zufälligen Definitionsreihenfolge in `_TRANSPORT_PARAMETER` – sonst
    würde z.B. "zu Fuß, aber auch mit dem Auto" fälschlich "Auto" als zuerst genannt behandeln, nur
    weil "auto" im Dict vor "zu fuß" steht). Ohne jeden Treffer (keine Angabe oder unbekannte
    Formulierung): EIN Eintrag mit der konservativen Fußweg-Annahme.
    """
    standard = [(_STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH, _STANDARD_TRANSPORT_RADIUS_METER, _STANDARD_TRANSPORT_MODUS)]
    if not lokaler_transport_praeferenz:
        return standard
    text_klein = lokaler_transport_praeferenz.lower()
    fruehester_treffer_je_modus: dict[str, tuple[int, tuple[float, int, str]]] = {}
    for schluesselwort, eintrag in _TRANSPORT_PARAMETER.items():
        position = text_klein.find(schluesselwort)
        if position == -1:
            continue
        modus = eintrag[2]
        bisher = fruehester_treffer_je_modus.get(modus)
        if bisher is None or position < bisher[0]:
            fruehester_treffer_je_modus[modus] = (position, eintrag)
    if not fruehester_treffer_je_modus:
        return standard
    return [eintrag for _, eintrag in sorted(fruehester_treffer_je_modus.values(), key=lambda paar: paar[0])]


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


# Schlüsselwörter, die einen Leihwunsch ausdrücken. Der eigentliche Dialog (LLM, siehe katalog.py
# F14 `kontext_hinweis`) erkennt den ANLASS (Fahrzeugwechsel gegenüber der Anreise) und fragt nach;
# diese Funktion liest nur noch das ERGEBNIS dieser Nachfrage aus der final bestätigten F14-Antwort
# heraus – bewusst regelbasiert statt LLM-Erkennung (CLAUDE.md Grundprinzip 1/3).
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


def _tage_aus_datumsbereich(text: str) -> int | None:
    """
    Berechnet die Reisedauer (inklusive beider Grenztage, wie bei "X Tage"-Angaben) aus einem im
    Text gefundenen Datumsbereich (siehe `_DATUM_BEREICH_MUSTER`) – None, wenn kein Bereich
    gefunden wird oder die gefundenen Zahlen kein gültiges Datum ergeben (z.B. Tag 32).

    Fehlt das Jahr auf EINER Seite (der Normalfall, siehe Rückfrage-Ergebnis), übernimmt sie das
    Jahr der ANDEREN Seite, falls dort eines genannt wurde – erst wenn KEINE der beiden Seiten ein
    Jahr nennt, wird ein neutrales Ankerjahr für BEIDE angenommen. BEHOBENER BUG (Live-Vorfall:
    "15.09. - 18.09.2026" ergab eine ~700 Tage lange Reise): vorher bekam eine fehlende Jahresangabe
    IMMER das Ankerjahr, unabhängig davon, ob die andere Seite bereits ein echtes Jahr nannte – aus
    "15.09. - 18.09.2026" wurde so faktisch "15.09.2024 - 18.09.2026", eine ~2 Jahre lange
    Phantom-Reise. Liegt das (jetzt korrekt gemeinsame) Enddatum dadurch VOR dem Startdatum (z.B.
    "28.12. bis 3.1." – eine echte Reise über den Jahreswechsel, kein Jahr genannt), gilt das Ende
    als im Folgejahr statt eine negative Dauer zu liefern.
    """
    treffer = _DATUM_BEREICH_MUSTER.search(text)
    if not treffer:
        return None
    start_tag, start_monat, start_jahr, ende_tag, ende_monat, ende_jahr = treffer.groups()
    anker_jahr = 2024  # Schaltjahr als neutraler Anker, falls GAR KEIN Jahr genannt wird (29.2. gültig)
    gemeinsames_jahr = int(start_jahr) if start_jahr else (int(ende_jahr) if ende_jahr else anker_jahr)
    ende_jahr_effektiv = int(ende_jahr) if ende_jahr else gemeinsames_jahr
    try:
        start = datetime.date(gemeinsames_jahr, int(start_monat), int(start_tag))
        ende = datetime.date(ende_jahr_effektiv, int(ende_monat), int(ende_tag))
    except ValueError:
        return None  # z.B. "32.1." – kein gültiges Datum, kein geratener Ersatzwert (Grundprinzip 1)
    if ende < start:
        ende = ende.replace(year=ende.year + 1)
    return (ende - start).days + 1


def _tage_aus_iso_daten(start_datum: str | None, end_datum: str | None) -> int | None:
    """
    Reisedauer (inklusive beider Grenztage) aus zwei ISO-Datumsstrings ("YYYY-MM-DD") – der
    PRIMÄRE, deterministische Pfad (siehe schema.py `ReiseAnfrage.reise_start_datum`/
    `reise_end_datum`): die LLM klärt Datumsfragen im Dialog (fehlendes Jahr, "nächsten Monat"
    o.Ä.) und liefert zwei eindeutige Werte, die REINE Arithmetik übernimmt weiterhin der Code
    (Grundprinzip 3 – kein Vertrauen auf LLM-Kopfrechnen bei Datumsdifferenzen).

    None, wenn eines der beiden Felder fehlt, kein gültiges ISO-Datum ist, oder das Enddatum vor
    dem Startdatum liegt (dann lieber der Freitext-Fallback als eine negative/geratene Dauer,
    Grundprinzip 1) – der Aufrufer fällt dann auf den Freitext-Parser zurück.
    """
    if not start_datum or not end_datum:
        return None
    try:
        start = datetime.date.fromisoformat(start_datum)
        ende = datetime.date.fromisoformat(end_datum)
    except ValueError:
        return None
    if ende < start:
        return None
    return (ende - start).days + 1


def schaetze_reisedauer_tage(
    reisezeitraum_rohtext: str | None, standard_tage: int = 5,
    start_datum: str | None = None, end_datum: str | None = None,
) -> int:
    """
    Schätzung der Reisedauer für Optimierung 1/Tests. PRIMÄR aus `start_datum`/`end_datum` (von der
    LLM interpretierte ISO-Daten, siehe `_tage_aus_iso_daten`) – FALLBACK, wenn diese fehlen (z.B.
    dialogfreie Testfälle über pruefe_planung.py ohne LLM-Session, oder falls die LLM aus dem
    Gespräch kein eindeutiges Datum ableiten konnte): der bisherige Freitext-Regex-Parser auf
    `reisezeitraum_rohtext` (Rueckgabetyp.STRING, siehe katalog.py F07), in dieser Reihenfolge (die
    explizite Tagesangabe geht vor, falls beide im selben Text vorkommen) – eine explizite "X
    Tage"-Formulierung, sonst ein Datumsbereich (siehe `_tage_aus_datumsbereich`).
    """
    tage_aus_iso = _tage_aus_iso_daten(start_datum, end_datum)
    if tage_aus_iso is not None:
        return tage_aus_iso
    if not reisezeitraum_rohtext:
        return standard_tage
    treffer = _TAGE_MUSTER.search(reisezeitraum_rohtext)
    if treffer:
        return int(treffer.group(1))
    tage_aus_datum = _tage_aus_datumsbereich(reisezeitraum_rohtext)
    return tage_aus_datum if tage_aus_datum is not None else standard_tage


# Wie viele POIs Optimierung 1 maximal als Kandidaten bekommt – skaliert mit
# der Reisedauer statt eines festen Werts (siehe Projektkonversation: eine
# 3-Tage-Reise braucht keine 30 Kandidaten, eine 10-Tage-Reise mehr als eine
# feste Kleinzahl). Wird sowohl von der Chat-Vorschau (vorschlaege.py, Knoten
# b5) als auch von der tatsächlichen Optimierung (pipeline.py) verwendet –
# EINE Quelle, damit beide immer denselben Wert nennen/verwenden: wenn der
# Bot im Chat sagt "wir können nicht mehr als X optimieren", muss das auch
# wirklich stimmen.
#
# BEHOBENER KOSTEN-VORFALL (Live-Vorfall, echte Google-Rechnung ~100€, davon 40€ an einem einzigen
# Tag): `aufbereitung.py::hole_reisezeitmatrix` holt für JEDEN Planungslauf eine VOLLSTÄNDIGE
# (Depot+POIs)²-Distanzmatrix, EINMAL PRO genanntem Verkehrsmittel – bei vielen POIs und mehreren
# genannten Verkehrsmitteln (z.B. "Fahrrad und Bahn") summiert sich das schnell auf tausende
# abgerechnete Distance-Matrix-Elemente FÜR EINEN EINZIGEN Reiseplan. Da die Kosten quadratisch mit
# dieser Zahl skalieren, wurde sie in zwei Schritten gesenkt (Product-Owner-Entscheidung,
# 24.08.2026: "dass so was auf keinen Fall noch mal passieren kann") – zuletzt auf 10, hergeleitet
# aus der striktesten Flexibilitätsstufe (siehe `_MAX_POIS_PRO_TAG_JE_FLEXIBILITAETSSTUFE`: Stufe 1
# = 3 POIs/Tag) über einen Referenzzeitraum von 3 Tagen (3 × 3 = 9) plus EINEM zusätzlichen
# Kandidaten als Reserve für "weitere Empfehlungen". Trade-off bewusst in Kauf genommen: weniger
# Kandidaten für sehr lange Reisen bedeuten potenziell etwas weniger Auswahl für Optimierung 1.
_POIS_JE_TAG = 4
_MIN_POIS_FUER_OPTIMIERUNG = 8
_MAX_POIS_FUER_OPTIMIERUNG = 10


def max_pois_fuer_reise(anfrage: ReiseAnfrage) -> int:
    """Wie viele POIs Optimierung 1 für diese Reise maximal als Kandidaten bekommt (siehe Kommentar oben)."""
    tage = schaetze_reisedauer_tage(
        anfrage.reisezeitraum_rohtext, start_datum=anfrage.reise_start_datum, end_datum=anfrage.reise_end_datum
    )
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


# Flexibilitätsstufe (F05, katalog.py `flexibilitaet_stufe`, 1-3, vom LLM aus dem GESAMTEN
# Gesprächsverlauf abgeleitet, siehe schema.py) – zwei Hebel, gemeinsam abgestimmt (Rückfrage-
# Ergebnis, siehe ENTSCHEIDUNGSLOG.md): ein Anzahl-Deckel pro Tag UND eine Pufferpause (analog zum
# Barrierefreiheits-Mechanismus, siehe unten) – ein "flexibler" Tag soll nicht nur weniger Stopps
# haben, sondern auch zwischendrin echten Freiraum für Spontanes (z.B. Kaffee/Kuchen), nicht nur
# unstrukturierte Restzeit am Tagesende.
#
# SKALA VERKLEINERT (Product-Owner-Entscheidung, 24.08.2026, im Zuge des Kosten-Vorfalls – siehe
# `_MAX_POIS_FUER_OPTIMIERUNG`): vorher 1-5 mit "Stufe 1 = kein Deckel" (Tag wurde voll ausgereizt).
# Jetzt 1-3, und JEDE Stufe (auch 1) hat einen festen Deckel – "ganz durchgeplant" bedeutet jetzt
# maximal 3 Stopps/Tag, nicht mehr unbegrenzt. NUR ohne jedes Signal (None) bleibt der Tag
# unbegrenzt (kein Deckel, keine Pufferpause).
_MAX_POIS_PRO_TAG_JE_FLEXIBILITAETSSTUFE: dict[int, int] = {1: 3, 2: 2, 3: 1}
# (pause_intervall_minuten, pause_dauer_minuten) je Stufe – Stufe 1 ("ganz durchgeplant") bewusst
# ohne Eintrag (kein Puffer), ab Stufe 2 zusätzlich echter Freiraum zwischen den Besuchen.
_PAUSE_JE_FLEXIBILITAETSSTUFE: dict[int, tuple[int, int]] = {2: (150, 20), 3: (90, 30)}


def max_pois_pro_tag_fuer_flexibilitaet(flexibilitaet_stufe: int | None) -> int | None:
    """None (keine zusätzliche Tages-Obergrenze) NUR ohne jedes Signal."""
    return _MAX_POIS_PRO_TAG_JE_FLEXIBILITAETSSTUFE.get(flexibilitaet_stufe) if flexibilitaet_stufe else None


def pause_parameter_fuer_flexibilitaet(flexibilitaet_stufe: int | None) -> tuple[int | None, int | None]:
    """(pause_intervall_minuten, pause_dauer_minuten) – (None, None) ohne Signal oder bei Stufe 1."""
    if not flexibilitaet_stufe:
        return None, None
    return _PAUSE_JE_FLEXIBILITAETSSTUFE.get(flexibilitaet_stufe, (None, None))


# Drei Anpassungen für Optimierung 1 bei genannter Barrierefreiheit/eingeschränkter
# Gehfähigkeit (siehe schema.py `barrierefreiheit_oder_eingeschraenkt`): langsamere Gehzeiten,
# eingeplante Pausen, POIs nah am Depot bevorzugt. Grobe, literaturunabhängige Richtwerte, keine
# erfundene Tatsache über eine konkrete Person – nur eine dokumentierte Modellannahme.
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
    zu weiter entfernten – NUR aufgerufen, wenn `ReiseAnfrage.barrierefreiheit_oder_eingeschraenkt()`
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
    client: MapsClient, depot: POI, pois: list[POI], modi: list[str]
) -> dict[tuple[int, int], int]:
    """
    Ruft die echte Google-Distance-Matrix (`MapsClient.distanzmatrix`) für Depot + alle `pois` ab
    und baut daraus ein `(id_a, id_b) -> Minuten`-Lookup für `TOPTWInstanz.reisezeiten_minuten`
    (siehe dort und CLAUDE.md "Zentrale Anpassung": "Distanzberechnung aus Koordinaten (Luftlinie)
    durch echte Reisezeiten aus der Google Distance Matrix ersetzen").

    `modi` (siehe `modi_fuer_lokalen_transport`): bei MEHREREN genannten Verkehrsmitteln wird die
    Matrix EINMAL PRO MODUS abgerufen (weiterhin ein NxN-Aufruf je Modus, kein Aufruf je
    Einzelpaar) und je Paar die SCHNELLSTE der genannten Optionen übernommen – siehe
    ENTSCHEIDUNGSLOG.md: "wenn er sagt Fahrrad und Öffis, dann wird das genommen, was schneller
    ist". Fehlt für ein Paar in JEDEM abgefragten Modus eine Route (-1, siehe google_maps.py), wird
    dieses Paar NICHT in die Matrix aufgenommen – `TOPTWInstanz.reisezeit_minuten` fällt dann NUR
    für dieses eine Paar auf die Luftlinien-Schätzung zurück, statt eine erfundene Zeit einzutragen
    (Grundprinzip 1) oder die gesamte Planung abzubrechen.
    """
    alle_orte = [depot] + pois
    reisezeiten: dict[tuple[int, int], int] = {}
    for modus in modi:
        minuten_matrix = client.distanzmatrix([(ort.x, ort.y) for ort in alle_orte], modus=modus)
        for i, von in enumerate(alle_orte):
            for j, nach in enumerate(alle_orte):
                if i == j or i >= len(minuten_matrix) or j >= len(minuten_matrix[i]):
                    continue
                minuten = minuten_matrix[i][j]
                if minuten is None or minuten < 0:  # -1 = keine Route gefunden (siehe google_maps.py)
                    continue
                bisher = reisezeiten.get((von.id, nach.id))
                if bisher is None or minuten < bisher:
                    reisezeiten[(von.id, nach.id)] = minuten
    return reisezeiten


def ergaenze_anfahrt_modus_je_etappe(
    client: MapsClient, depot_koordinaten: tuple[float, float], tagesrouten: list[Tagesroute], modi: list[str],
) -> None:
    """
    NACHTRÄGLICH, NUR für die tatsächlich besuchten Etappen der fertigen Route (Rückfrage-Ergebnis
    "Variante B": erst optimieren, dann nur die gewählten Etappen erneut abfragen, statt vorab alle
    Kandidaten-Paare multimodal durchzufragen – deutlich weniger API-Aufrufe, und die bereits
    feststehenden Ankunfts-/Abfahrtszeiten bleiben unverändert konsistent mit der EINEN
    Distanzmatrix, mit der Optimierung 1 tatsächlich geplant hat, siehe `hole_reisezeitmatrix`).

    Setzt `Besuch.anfahrt_modus` auf das vom Nutzer genannte Verkehrsmittel (F14), das für GENAU
    DIESE Etappe am schnellsten ist – reine Anzeige-Ergänzung, verändert `ankunft`/`abfahrt` nicht.
    Bei nur einem genannten Verkehrsmittel (Regelfall) wird direkt übernommen, OHNE zusätzlichen
    API-Aufruf – die Anzeige soll trotzdem immer ehrlich benennen, welches Verkehrsmittel gemeint
    war, statt es zu verschweigen.
    """
    if len(modi) == 1:
        for tagesroute in tagesrouten:
            for besuch in tagesroute.besuche:
                besuch.anfahrt_modus = modi[0]
        return

    for tagesroute in tagesrouten:
        vorherige_koordinaten = depot_koordinaten
        for besuch in tagesroute.besuche:
            ziel_koordinaten = (besuch.poi.x, besuch.poi.y)
            dauer_je_modus = {
                modus: client.anfahrtszeiten_minuten(vorherige_koordinaten, [ziel_koordinaten], modus=modus)[0]
                for modus in modi
            }
            gueltige_modi = {modus: dauer for modus, dauer in dauer_je_modus.items() if dauer is not None and dauer >= 0}
            besuch.anfahrt_modus = min(gueltige_modi, key=gueltige_modi.get) if gueltige_modi else modi[0]
            vorherige_koordinaten = ziel_koordinaten


def erstelle_toptw_instanz(
    anfrage: ReiseAnfrage,
    pois: list[POI],
    standard_tagesbudget_minuten: int,
    depot_koordinaten: tuple[float, float],
    depot_name: str = "Unterkunft",
    max_aktivitaetszeit_minuten: int = 10**9,
    client: MapsClient | None = None,
    anzahl_tage_override: int | None = None,
) -> TOPTWInstanz:
    """
    Führt Fragekatalog-Antworten und POI-Liste zur TOPTW-Eingabe zusammen.

    `anzahl_tage_override` (siehe pipeline.py): ersetzt die aus `anfrage.reisezeitraum_rohtext`
    geschätzte Reisedauer – NUR nötig, wenn ein Tag komplett aus der Optimierung herausgenommen
    wurde (siehe pipeline.py `_trenne_tour_beispiele_ab`, ein für geführte Touren reservierter
    Tag), sonst bleibt es bei der geschätzten Gesamtdauer.

    `pois` müssen bereits bewertet UND ausgewählt sein (siehe `waehle_top_pois`) – diese Funktion
    scort nicht mehr selbst.

    `depot_koordinaten` MUSS in der Nähe der `pois` liegen (die im Dialog bestätigte Unterkunft,
    siehe `ReiseAnfrage.unterkunft_koordinaten`, bzw. ersatzweise die geokodierte Zielregion, siehe
    pipeline.py::plane_reise) – ohne diese Angabe würde das Depot beim TOPTWInstanz-Default auf
    (0, 0) stehen, wodurch jede Anreise zu einem POI unrealistisch lang würde und de facto nie ein
    POI eingeplant werden könnte.

    `max_aktivitaetszeit_minuten` (siehe TOPTWInstanz-Doku, config.py
    `EINSTELLUNGEN.max_aktivitaetszeit_minuten`): reine Besuchszeit-Obergrenze
    OHNE Fahrzeit, härter als `standard_tagesbudget_minuten`. Default sehr
    groß (= keine Einschränkung), damit Aufrufer ohne explizite Angabe (z.B.
    ältere Tests) unverändert funktionieren.

    Bei genannter `anfrage.barrierefreiheit_oder_eingeschraenkt()` (siehe schema.py, Projektkonversation:
    "Gehzeiten neu berechnen, Pausen einplanen, POIs nah am Hotel höher gewichten") drei
    Anpassungen (siehe Konstanten oben `erstelle_toptw_instanz`): langsamere Geschwindigkeit NUR
    wenn ohnehin zu Fuß unterwegs (ein bestätigtes Auto/ÖPNV-Tempo wird nicht "verlangsamt" – die
    Person sitzt ja nicht zu Fuß in der Bahn), Pausen-Intervall in der `TOPTWInstanz`, und eine
    Nähe-Gewichtung der `pois` VOR dem Zeitfenster-Schritt.

    `anfrage.flexibilitaet_stufe` (F05, 1-5, vom LLM aus dem Gesprächsverlauf abgeleitet – siehe
    schema.py) setzt eine zusätzliche Tages-Obergrenze für die reine ANZAHL POI-Besuche (siehe
    `max_pois_pro_tag_fuer_flexibilitaet`) UND ab Stufe 3 eine Pufferpause (siehe
    `pause_parameter_fuer_flexibilitaet`) – Stufe 1/2 bzw. kein Signal: wie bisher, Tag wird voll
    ausgereizt.

    `client` (optional, siehe `hole_reisezeitmatrix`): mit Angabe werden ECHTE Reisezeiten (Google
    Distance Matrix) für Depot+POIs vorab abgerufen und in `TOPTWInstanz.reisezeiten_minuten`
    hinterlegt – ohne Angabe (Default `None`, z.B. ältere Tests) bleibt es bei der
    Luftlinien-Schätzung (`TOPTWInstanz.reisezeit_minuten`-Fallback).
    """
    # Der Fragekatalog enthält aktuell kein eigenes Feld für das tägliche
    # Zeitbudget (siehe katalog.py) – daher der Konfigurations-Default.
    tagesbudget = standard_tagesbudget_minuten
    tage = anzahl_tage_override if anzahl_tage_override is not None else schaetze_reisedauer_tage(
        anfrage.reisezeitraum_rohtext, start_datum=anfrage.reise_start_datum, end_datum=anfrage.reise_end_datum
    )

    depot_x, depot_y = depot_koordinaten
    depot = POI(
        id=0, name=depot_name, kategorie="depot", x=depot_x, y=depot_y,
        score=0.0, required_time=0, opening=0, closing=24 * 60,
    )
    geschwindigkeit_kmh, _ = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    modi = modi_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    pause_intervall_minuten = None
    pause_dauer_minuten = _PAUSE_DAUER_MINUTEN
    eingeplante_pois = pois
    if anfrage.barrierefreiheit_oder_eingeschraenkt():
        if geschwindigkeit_kmh == _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH:
            geschwindigkeit_kmh = _GESCHWINDIGKEIT_EINGESCHRAENKT_KMH
        pause_intervall_minuten = _PAUSE_INTERVALL_MINUTEN
        eingeplante_pois = gewichte_nach_naehe_zum_depot(pois, depot_koordinaten)
    # Flexibilitäts-Pufferpause (siehe `pause_parameter_fuer_flexibilitaet`) UND Barrierefreiheits-
    # Pufferpause können gleichzeitig zutreffen – dann gewinnt das KÜRZERE Intervall (öfter Pause
    # schadet nie), nie wird eine bereits nötige Barrierefreiheits-Pause durch niedrige
    # Flexibilität "wegoptimiert".
    flex_intervall, flex_dauer = pause_parameter_fuer_flexibilitaet(anfrage.flexibilitaet_stufe)
    if flex_intervall is not None and (pause_intervall_minuten is None or flex_intervall < pause_intervall_minuten):
        pause_intervall_minuten = flex_intervall
        pause_dauer_minuten = flex_dauer
    eingeplante_pois = wende_tageszeitfenster_an(list(eingeplante_pois))
    reisezeiten_minuten = hole_reisezeitmatrix(client, depot, eingeplante_pois, modi) if client is not None else None
    max_pois_pro_tag = max_pois_pro_tag_fuer_flexibilitaet(anfrage.flexibilitaet_stufe)
    return TOPTWInstanz(
        pois=eingeplante_pois, tagesbudget_minuten=tagesbudget, anzahl_tage=tage,
        depot=depot, geschwindigkeit_kmh=geschwindigkeit_kmh, max_aktivitaetszeit_minuten=max_aktivitaetszeit_minuten,
        pause_intervall_minuten=pause_intervall_minuten, pause_dauer_minuten=pause_dauer_minuten,
        reisezeiten_minuten=reisezeiten_minuten, max_pois_pro_tag=max_pois_pro_tag,
    )

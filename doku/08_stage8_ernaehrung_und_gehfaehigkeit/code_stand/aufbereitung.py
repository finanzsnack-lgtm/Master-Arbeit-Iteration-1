"""
Bereitet die im Dialog erhobenen Daten für Optimierung 1 auf (siehe
CLAUDE.md, "Optimierung 1 – Vor-Ort-Planung"): POI-Scores aus Präferenz-
Matching und Zusammenstellung des TOPTW-Eingabeformats (Depot, Zeitbudget
je Tag, Tagesanzahl).
"""
from __future__ import annotations

import re
from dataclasses import replace

from src.api.google_maps import mindest_tageszeit_fuer_typ
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
# Kein Eintrag -> Fußweg-Default (konservativste, bisherige Annahme).
_TRANSPORT_PARAMETER: dict[str, tuple[float, int]] = {
    "fahrrad": (15.0, 8000), "rad": (15.0, 8000), "bike": (15.0, 8000), "fahrradfahren": (15.0, 8000),
    "auto": (40.0, 15000), "wagen": (40.0, 15000), "pkw": (40.0, 15000),
    "öffentlich": (25.0, 8000), "bus": (25.0, 8000), "bahn": (25.0, 8000), "u-bahn": (25.0, 8000),
    "tram": (25.0, 8000), "öpnv": (25.0, 8000),
    "zu fuß": (4.5, 1500), "fuß": (4.5, 1500), "laufen": (4.5, 1500), "fußweg": (4.5, 1500),
}
_STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH = 4.5
_STANDARD_TRANSPORT_RADIUS_METER = 3000


def parameter_fuer_lokalen_transport(lokaler_transport_praeferenz: str | None) -> tuple[float, int]:
    """
    Ermittelt (Geschwindigkeit km/h, POI-Suchradius Meter) aus der Freitext-
    Antwort auf F14. Regelbasiertes Schlüsselwort-Matching statt LLM-
    Erkennung (analog zu vorschlaege.py `ist_all_inclusive_wunsch`) – die
    Entscheidung bleibt damit im deterministischen Layer (CLAUDE.md,
    Grundprinzip 1/3). Ohne Angabe oder unbekannte Formulierung: konservative
    Fußweg-Annahme, wie bisher.
    """
    if not lokaler_transport_praeferenz:
        return _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH, _STANDARD_TRANSPORT_RADIUS_METER
    text_klein = lokaler_transport_praeferenz.lower()
    for schluesselwort, parameter in _TRANSPORT_PARAMETER.items():
        if schluesselwort in text_klein:
            return parameter
    return _STANDARD_TRANSPORT_GESCHWINDIGKEIT_KMH, _STANDARD_TRANSPORT_RADIUS_METER


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
    return 1.0 + (gewichtung or {}).get(poi.nutzerinteresse, 1.0) * 2.0


def schaetze_reisedauer_tage(reisezeitraum_rohtext: str | None, standard_tage: int = 5) -> int:
    """
    Heuristische Schätzung der Reisedauer aus dem Freitext der Zeitraum-Frage
    (siehe katalog.py, Anmerkung zu F07: das Rohmaterial kombiniert "wie
    lange" und "welcher Zeitraum" in einer einzigen, als "Date" vermerkten
    Frage) – `reisezeitraum_rohtext` wird als reiner Freitext gespeichert
    (Rueckgabetyp.STRING), dieser einfache Regex-Parser liest daraus die
    Anzahl Tage für Optimierung 1/main.py-Tests, ohne eine LLM-Anbindung zu
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


def erstelle_toptw_instanz(
    anfrage: ReiseAnfrage,
    pois: list[POI],
    standard_tagesbudget_minuten: int,
    depot_koordinaten: tuple[float, float],
    depot_name: str = "Unterkunft",
    max_aktivitaetszeit_minuten: int = 10**9,
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
    return TOPTWInstanz(
        pois=wende_tageszeitfenster_an(list(pois)), tagesbudget_minuten=tagesbudget, anzahl_tage=tage, depot=depot,
        geschwindigkeit_kmh=geschwindigkeit_kmh, max_aktivitaetszeit_minuten=max_aktivitaetszeit_minuten,
    )

"""
Gemeinsame Planungs-Pipeline nach Abschluss der Dialogschleife: Datenaufbereitung -> Optimierung 1
-> Optimierung 2 -> Monte-Carlo-Härtetest -> Reiseplan. Wird sowohl vom echten interaktiven Chat
(chat.py) als auch vom schnellen, dialogfreien Planungstest (pruefe_planung.py) verwendet, damit
diese Logik nur an einer Stelle gepflegt werden muss.
"""
from __future__ import annotations

import math

from src.api.google_maps import (
    MapsClient,
    ist_lernaktivitaet_bezogenes_interesse,
    ist_markt_bezogenes_interesse,
    ist_tour_bezogenes_interesse,
)
from src.ausgabe.reiseplan import SICHERHEITSHINWEISE_URL, Reiseplan
from src.config import EINSTELLUNGEN
from src.ausgabe.debug import PlanungsDebugSammlung
from src.datenaufbereitung.aufbereitung import (
    erkenne_leihwunsch,
    ergaenze_anfahrt_modus_je_etappe,
    erstelle_toptw_instanz,
    gewichte_nach_naehe_zum_depot,
    max_pois_fuer_reise,
    modi_fuer_lokalen_transport,
    parameter_fuer_lokalen_transport,
    schaetze_reisedauer_tage,
    waehle_top_pois,
)
from src.datenaufbereitung.poi_sammlung import sammle_pois
from src.datenaufbereitung.vertraeglichkeit import filtere_pois_hart
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.kostenschaetzung import schaetze_gesamtkosten
from src.optimierung.monte_carlo import haertetest_teilstrecken
from src.optimierung.toptw import Tagesroute, plane_gesamte_reise
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative, bewerte_alternativen, nachhaltigkeits_nudge

# Obergrenze für Reiseplan.beispielrestaurants (siehe dort) – großzügig genug für Rotation über
# mehrere Tage (reiseplan.py `_restaurants_fuer_tag`, 3 je Tag), ohne unbegrenzt viele Treffer zu
# behalten.
_MAX_BEISPIELRESTAURANTS = 9


def _trenne_beispielrestaurants_ab(
    pois: list, depot_koordinaten: tuple[float, float]
) -> tuple[list, list]:
    """
    Trennt essens-/abendausgehbezogene Treffer (`POI.besuchsklasse` in "mahlzeit"/"bar", z.B. aus
    dem Interesse "Restaurants"/"abends essen gehen"/"urige Kneipe" bei gewünschtem lokalem
    Kontakt, siehe katalog.py F19) von den übrigen Kandidaten – siehe `plane_reise`: diese laufen
    NICHT mehr durch Optimierung 1 (ursprünglich konkurrierten sie dort als normale POI-Kandidaten
    um Zeitfenster/Score und konnten dabei komplett aussortiert werden, obwohl "essen gehen" dem
    Nutzer wichtig war), sondern werden hier nach Entfernung zur Unterkunft sortiert für
    `Reiseplan.beispielrestaurants` zurückgegeben (auf `_MAX_BEISPIELRESTAURANTS` gekappt).

    "bar" (Kneipen) wurde bewusst ERGÄNZT (siehe Rückfrage zu lokalem Kontakt: eine "urige Kneipe"
    landet bei Google häufig unter dem Typ "bar", nicht "restaurant" – ohne diese Ergänzung würden
    genau die für lokalen Kontakt typischen Treffer nicht erscheinen). Cafés (besuchsklasse
    "kaffee") sind davon weiterhin NICHT betroffen, bleiben normale Kandidaten (siehe stattdessen
    `_trenne_markt_beispiele_ab` für den Mittags-Fall).

    Gibt (uebrige_pois, beispielrestaurants) zurück.
    """
    restaurant_pois = [poi for poi in pois if poi.besuchsklasse in ("mahlzeit", "bar")]
    uebrige_pois = [poi for poi in pois if poi.besuchsklasse not in ("mahlzeit", "bar")]
    beispielrestaurants = sorted(
        restaurant_pois, key=lambda poi: math.dist((poi.x, poi.y), depot_koordinaten)
    )[:_MAX_BEISPIELRESTAURANTS]
    return uebrige_pois, beispielrestaurants


# Obergrenze für Reiseplan.markt_beispiele (siehe dort) – analog zu _MAX_BEISPIELRESTAURANTS.
_MAX_MARKT_BEISPIELE = 9


def _trenne_markt_beispiele_ab(pois: list, depot_koordinaten: tuple[float, float]) -> tuple[list, list]:
    """
    Trennt markt-/cafébezogene Treffer (`POI.besuchsklasse == "kaffee"` ODER `POI.nutzerinteresse`
    passt auf google_maps.py `ist_markt_bezogenes_interesse`) von den übrigen Kandidaten ab – NUR
    aufgerufen, wenn `anfrage.lokaler_kontakt_wichtig` (siehe `plane_reise`), sonst bleiben Cafés
    normale Kandidaten wie sonst auch. Analog zu `_trenne_beispielrestaurants_ab`: läuft NICHT durch
    Optimierung 1, sondern wird nach Entfernung zur Unterkunft sortiert für den Mittags-Zeitblock
    zurückgegeben (siehe `Reiseplan.markt_beispiele`, `reiseplan.py::_markt_beispiele_fuer_tag`).

    Gibt (uebrige_pois, markt_beispiele) zurück.
    """
    markt_pois = [
        poi for poi in pois
        if poi.besuchsklasse == "kaffee" or (poi.nutzerinteresse and ist_markt_bezogenes_interesse(poi.nutzerinteresse))
    ]
    markt_ids = {poi.id for poi in markt_pois}
    uebrige_pois = [poi for poi in pois if poi.id not in markt_ids]
    markt_beispiele = sorted(
        markt_pois, key=lambda poi: math.dist((poi.x, poi.y), depot_koordinaten)
    )[:_MAX_MARKT_BEISPIELE]
    return uebrige_pois, markt_beispiele


# Für den Mittags-Zeitblock bei gewünschtem lokalem Kontakt reserviert (siehe `plane_reise`) – NUR
# an "vollen" Tagen (nicht Anreise-, nicht Abreisetag, siehe Rückfrage-Ergebnis), damit Optimierung
# 1 diesen Block gar nicht erst mit anderen POIs füllt, statt ihn nur nachträglich anzuzeigen.
_LOKALER_KONTAKT_BLOCK_MINUTEN = 120


# Bewusst klein gehalten (siehe `_trenne_sonderkategorie_ab`): begrenzt, wie viele Treffer
# überhaupt einzeln auf Barrierefreiheit geprüft werden – Rückfrage-Ergebnis nach einem Live-Vorfall
# ("die App hat sich aufgehängt"), bei dem ALLE Roh-Treffer einzeln geprüft wurden.
_SONDERKATEGORIE_KANDIDATEN_POOL = 8
_SONDERKATEGORIE_BEISPIELE_ANZAHL = 3


def _trenne_sonderkategorie_ab(
    pois: list, depot_koordinaten: tuple[float, float],
    mobilitaetseinschraenkung_stufe: str | None, client: MapsClient, gehoert_zur_kategorie,
) -> tuple[list, list]:
    """
    Trennt Treffer EINER Sonderkategorie (z.B. geführte Touren, Lernaktivitäten ODER Markt-/
    Café-Beispiele – erkannt über `gehoert_zur_kategorie(poi)`, siehe google_maps.py
    `ist_tour_bezogenes_interesse`/`ist_lernaktivitaet_bezogenes_interesse` für die
    `nutzerinteresse`-basierten Fälle bzw. `poi.besuchsklasse` für Café) von den übrigen Kandidaten
    ab. Touren/Lernaktivitäten laufen NICHT durch Optimierung 1 (siehe `plane_reise`: dafür wird
    stattdessen je Kategorie ein kompletter Tag aus der Optimierung herausgenommen und die hier
    ausgewählten Beispiele direkt eingetragen, ohne Score/Auswahl durch den Algorithmus –
    Rückfrage-Ergebnis zu Lernaktivitäten: "das möchte ich auf jeden Fall lernen" darf NIE vom
    Optimierungsalgorithmus aussortiert werden können, exakt dasselbe Argument wie bei geführten
    Touren). Markt-/Café-Beispiele (siehe `_trenne_markt_beispiele_ab`) laufen NICHT durch einen
    ganzen reservierten Tag, sondern nur durch einen kürzeren Zeitblock – dieselbe Auswahllogik
    (Pool-Begrenzung, Barrierefreiheits-Staffelung) gilt aber identisch.

    NUR die `_SONDERKATEGORIE_KANDIDATEN_POOL` nächstgelegenen (zur Unterkunft) werden überhaupt
    betrachtet, NICHT alle Roh-Treffer – begrenzt die Anzahl teurer Barrierefreiheits-
    Einzelabfragen (siehe Konstante oben, Live-Vorfall).

    Barrierefreiheits-Anforderung an die gezeigten `_SONDERKATEGORIE_BEISPIELE_ANZAHL` Beispiele,
    gestaffelt nach `mobilitaetseinschraenkung_stufe` (dieselbe Stufe wie überall sonst – "das muss
    an beide Algorithmen gehen, das muss die KI wissen und das muss genauso auch der
    Optimierungsalgorithmus wissen"):
    - "leicht"/None: keine Prüfung, einfach die nächstgelegenen.
    - "mittel": mindestens die Hälfte (aufgerundet) muss eindeutig bestätigt barrierefrei sein.
    - "stark": ALLE gezeigten Beispiele müssen eindeutig bestätigt barrierefrei sein – reicht der
      Pool nicht aus, werden weniger als `_SONDERKATEGORIE_BEISPIELE_ANZAHL` gezeigt statt ein nicht
      bestätigtes Beispiel zu erfinden (Grundprinzip 1).

    Gibt (uebrige_pois, kategorie_beispiele) zurück.
    """
    kategorie_ids = {poi.id for poi in pois if gehoert_zur_kategorie(poi)}
    uebrige_pois = [poi for poi in pois if poi.id not in kategorie_ids]
    if not kategorie_ids:
        return uebrige_pois, []

    kategorie_pois = [poi for poi in pois if poi.id in kategorie_ids]
    naechste = sorted(
        kategorie_pois, key=lambda poi: math.dist((poi.x, poi.y), depot_koordinaten)
    )[:_SONDERKATEGORIE_KANDIDATEN_POOL]

    if mobilitaetseinschraenkung_stufe not in ("mittel", "stark"):
        return uebrige_pois, naechste[:_SONDERKATEGORIE_BEISPIELE_ANZAHL]

    status_je_id = {poi.id: client.ist_barrierefrei(poi.place_id) for poi in naechste if poi.place_id}
    barrierefrei = [poi for poi in naechste if status_je_id.get(poi.id) is True]
    nicht_bestaetigt = [poi for poi in naechste if status_je_id.get(poi.id) is not True]

    if mobilitaetseinschraenkung_stufe == "stark":
        return uebrige_pois, barrierefrei[:_SONDERKATEGORIE_BEISPIELE_ANZAHL]

    # "mittel": mindestens die Hälfte (aufgerundet) der gezeigten Beispiele barrierefrei bestätigt.
    mindestanzahl = math.ceil(_SONDERKATEGORIE_BEISPIELE_ANZAHL / 2)
    auswahl = barrierefrei[:mindestanzahl]
    auswahl += nicht_bestaetigt[:_SONDERKATEGORIE_BEISPIELE_ANZAHL - len(auswahl)]
    return uebrige_pois, auswahl


def _nur_bestaetigte_verkehrsmittel(
    bewertete: list[BewerteteAlternative], verkehrsmittel_praeferenz: list[str]
) -> list[BewerteteAlternative]:
    """
    Schränkt die von Optimierung 2 (siehe verkehrsmittelwahl.py) bewerteten Alternativen auf die
    ein, die der Nutzer im Dialog (F13, verkehrsmittel_praeferenz) tatsächlich bestätigt hat –
    `bewerte_alternativen` würde sonst eine bereits bestätigte, konkrete Entscheidung überstimmen
    (CO2-Gewichtung begünstigt strukturell die Bahn).

    Ohne erkennbare Übereinstimmung (z.B. wenn `verkehrsmittel_praeferenz` unklarer Freitext ist,
    der keinen der echten Alternativen-Namen enthält) bleibt die volle Liste als Fallback erhalten,
    statt mit einer leeren Auswahl abzustürzen oder eine Wahl zu erfinden.
    """
    praeferenz_text = " ".join(verkehrsmittel_praeferenz).lower()
    passende = [b for b in bewertete if b.alternative.verkehrsmittel.lower() in praeferenz_text]
    return passende or bewertete


def plane_reise(
    anfrage: ReiseAnfrage, client: MapsClient, barrierefreiheit_strikt: bool = False,
) -> tuple[Reiseplan, str | None, PlanungsDebugSammlung]:
    """
    Führt die deterministische Planung durch (Optimierung 1 + 2 + Monte-Carlo-Härtetest) und gibt
    den fertigen Reiseplan, ggf. den Nachhaltigkeits-Nudge-Text für die An-/Abreise, sowie IMMER
    eine `PlanungsDebugSammlung` (siehe src/ausgabe/debug.py) zurück – rohe POI-Treffer, gefilterte/
    ausgewählte Kandidaten, Optimierung-1-Eingabe/-Ergebnis, Härtetest-Eingabe/-Ergebnis. Die
    Sammlung selbst kostet praktisch nichts (nur Referenzen auf ohnehin berechnete Daten) – OB und
    WOHIN sie geschrieben wird, entscheidet der jeweilige Aufrufer (agent_tools.py schreibt sie
    neben das Sitzungsprotokoll in protokolle/, siehe dort; pruefe_planung.py ebenso).

    `anfrage.zielregionen` ist die einzige im Fragekatalog erfasste Ortsangabe für das Reiseziel –
    Land-/Regionsebene (z.B. "Italien"), keine konkrete Stadt. `anfrage.primaeres_reiseziel()`
    (schema.py) liefert den ersten genannten Zielnamen, der direkt geokodiert/durchsucht wird.
    `anfrage.wohnort` (F08) liefert den Startort für Optimierung 2.

    `anfrage.unterkunft_koordinaten` (F15, im Dialog bereits gesucht UND bestätigt, siehe
    agent_tools.py::speichere_feld) ist das Depot für Optimierung 1 – KEINE zweite, unabhängige
    Unterkunftssuche hier, damit die im Chat bestätigte Unterkunft auch tatsächlich die geplante
    ist. Ist sie ausnahmsweise nicht gesetzt (z.B. eine Reiseanfrage ohne vorherigen Dialog, siehe
    pruefe_planung.py), fällt das Depot auf den geokodierten Zielort zurück statt abzustürzen.

    `barrierefreiheit_strikt` (siehe agent_tools.py::plane_reise_und_abschliessen): zweiter
    Planungsversuch, nachdem eine erste Planung die genannte Barrierefreiheits-/
    Mobilitätsanforderung nicht erfüllt hat – schließt nicht-barrierefreie POIs dann IMMER aus,
    auch ohne Alternative in derselben Kategorie.
    """
    ziel = anfrage.primaeres_reiseziel() or "Zielregion"
    debug_sammlung = PlanungsDebugSammlung()

    if anfrage.wohnort is None:
        raise ValueError(
            "Kein Wohnort in der Reiseanfrage gesetzt (Feld 'wohnort', Fragekatalog F08). "
            "Optimierung 2 (An-/Abreise) kann ohne Startort keine Verbindung berechnen."
        )

    # Genauer Zielpunkt für die An-/Abreise-Routenberechnung: sobald die Unterkunft bestätigt ist
    # (F15, anfrage.unterkunft_koordinaten), wird bis DORTHIN geroutet statt nur bis zur groben
    # Zielstadt (`ziel`) – Live-Vorfall/Rückfrage-Ergebnis: die berechnete Route endete an
    # "Berlin-Spandau" statt am tatsächlichen Hotel, obwohl der separat gebaute Google-Maps-Link
    # (siehe reiseplan.py `_hinreise_ziel_fuer_link`) schon länger die echte Unterkunft zeigte – nur
    # die Route selbst (Dauer/Kosten/Teilstrecken) wurde nie bis dorthin nachgezogen. Google
    # Directions akzeptiert "lat,lng" direkt als Origin/Destination. Fehlt sie ausnahmsweise (siehe
    # Docstring oben: Depot-Fallback), bleibt es beim groben Zielort-Namen.
    ziel_fuer_route = (
        f"{anfrage.unterkunft_koordinaten[0]},{anfrage.unterkunft_koordinaten[1]}"
        if anfrage.unterkunft_koordinaten else ziel
    )

    # Hinreise WIRD VOR Optimierung 1 berechnet: Tag 1 der Tagesroute muss die Ankunftszeit der
    # Hinreise vom Tagesbudget abziehen, sonst plant Optimierung 1 so, als stünde ab Reisebeginn
    # das volle Tagesbudget zur Verfügung.
    alternativen = client.reisealternativen(anfrage.wohnort, ziel_fuer_route)
    if not alternativen:
        raise ValueError(
            f"Für die Strecke '{anfrage.wohnort}' -> '{ziel_fuer_route}' konnte keine einzige "
            "Verkehrsmittel-Alternative (Bahn/Auto/Fernbus) berechnet werden. Vermutlich ist die "
            "Ortsangabe zu ungenau (z.B. eine ganze Region statt eines konkreten Ortes) – bitte "
            "einen konkreteren Wohnort/Zielort verwenden."
        )
    bewertete_alle = bewerte_alternativen(alternativen)
    # Nudge bezieht sich bewusst auf ALLE echten Alternativen (auch die, die der Nutzer nicht
    # gewählt hat) – er ist eine Zusatzinformation, keine Vorgabe für die tatsächliche Wahl unten
    # (siehe _nur_bestaetigte_verkehrsmittel). Dieselbe Berechnung läuft bereits während des
    # F13-Dialogs (siehe vorschlaege.py), damit der Nudge den Nutzer VOR seiner Entscheidung
    # erreicht statt erst hier am Ende – diese Berechnung bleibt zusätzlich bestehen, weil die
    # finale An-/Abreise erst nach dem vollständigen Dialog feststeht.
    nudge = nachhaltigkeits_nudge(bewertete_alle)
    bewertete = _nur_bestaetigte_verkehrsmittel(bewertete_alle, anfrage.verkehrsmittel_praeferenz)

    # Rückreise: ECHTER, EIGENSTÄNDIGER zweiter API-Abruf in umgekehrter Richtung (Rückfrage-
    # Ergebnis) – vorher wurde hier einfach dieselbe `bewertete[0]`-Hinreise-Alternative
    # wiederverwendet ("keine unabhängige Rückreise-Suche in diesem Prototyp"), was strukturell
    # falsch ist: eine Rückverbindung kann andere Umstiege/Linien/Wartezeiten haben als die Hinfahrt.
    rueckreise_alternativen = client.reisealternativen(ziel_fuer_route, anfrage.wohnort)
    if not rueckreise_alternativen:
        raise ValueError(
            f"Für die Rückstrecke '{ziel_fuer_route}' -> '{anfrage.wohnort}' konnte keine einzige "
            "Verkehrsmittel-Alternative (Bahn/Auto/Fernbus) berechnet werden."
        )
    rueckreise_bewertete_alle = bewerte_alternativen(rueckreise_alternativen)
    rueckreise_bewertete = _nur_bestaetigte_verkehrsmittel(rueckreise_bewertete_alle, anfrage.verkehrsmittel_praeferenz)

    tage = schaetze_reisedauer_tage(
        anfrage.reisezeitraum_rohtext, start_datum=anfrage.reise_start_datum, end_datum=anfrage.reise_end_datum
    )

    # Lokales Fortbewegungsmittel (F14) bestimmt den Places-Suchradius – die Geschwindigkeit für
    # die POI-zu-POI-Distanzmatrix setzt erstelle_toptw_instanz selbst (dieselbe Quelle).
    _, radius_meter = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)

    lokales_leihfahrzeug_gewuenscht = erkenne_leihwunsch(anfrage.lokaler_transport_praeferenz)
    # Der Verleih wurde bereits im Dialog gesucht UND ausgewählt (F14, siehe agent_tools.py
    # `hole_api_daten`/vorschlaege.py `suche_verleih_nahe_unterkunft`) – keine zweite Suche hier.
    lokaler_verleih_poi = anfrage.lokaler_verleih_gewaehlt

    # Cap greift HIER wirklich, nicht nur als Chat-Vorschau: mehr als max_pois_fuer_reise() bekommt
    # Optimierung 1 gar nicht erst als Kandidaten zu sehen. Kappung passiert NACH dem Scoring
    # (waehle_top_pois), damit Präferenzen/Gewichtung tatsächlich bestimmen, WELCHE POIs als
    # Kandidaten übrig bleiben, statt nur beliebige erste Fundstellen zu behalten.
    alle_pois = sammle_pois(
        ziel, anfrage.aktivitaeten_interessen, anfrage.aktivitaeten_mit_spezialrecherche, client,
        radius_meter=radius_meter, ernaehrung_einschraenkungen=anfrage.ernaehrung_einschraenkungen,
    )
    debug_sammlung.rohe_pois = list(alle_pois)
    depot_koordinaten = anfrage.unterkunft_koordinaten or client.geocode(ziel)
    # Tour- UND lernaktivitätsbezogene Treffer raus, VOR der teuren harten Filterung (siehe
    # `_trenne_sonderkategorie_ab`, Live-Vorfall: "die App hat sich aufgehängt", weil jeder
    # Roh-Treffer einzeln auf Barrierefreiheit geprüft wurde) – laufen NIE durch Optimierung 1
    # (Rückfrage-Ergebnis zu Lernaktivitäten: "das möchte ich auf jeden Fall lernen" darf NIE vom
    # Optimierungsalgorithmus aussortiert werden können, exakt dasselbe Argument wie bei Touren).
    alle_pois, tour_beispiele = _trenne_sonderkategorie_ab(
        alle_pois, depot_koordinaten, anfrage.mobilitaetseinschraenkung_stufe, client,
        lambda poi: bool(poi.nutzerinteresse) and ist_tour_bezogenes_interesse(poi.nutzerinteresse),
    )
    alle_pois, lernaktivitaet_beispiele = _trenne_sonderkategorie_ab(
        alle_pois, depot_koordinaten, anfrage.mobilitaetseinschraenkung_stufe, client,
        lambda poi: bool(poi.nutzerinteresse) and ist_lernaktivitaet_bezogenes_interesse(poi.nutzerinteresse),
    )
    # Je gefundener Sonderkategorie wird mindestens EIN kompletter Tag reserviert (bewusst die
    # LETZTEN Tage, einfachste vorhersehbare Regel; bei BEIDEN Funden zwei GETRENNTE Tage-Blöcke,
    # siehe Rückfrage) – ohne Treffer bleibt es bei der vollen Reisedauer für Optimierung 1, statt
    # Tage ohne Grund leerzuräumen. Reihenfolge (Lernaktivität ganz zuletzt, Tour davor) bestimmt,
    # welcher Tag welcher Kategorie zugeordnet wird (siehe reiseplan.py `_reservierte_sondertage`).
    # Die Tour kann MEHRERE Tage umfassen (Rückfrage-Ergebnis: NUR bei explizit geäußertem
    # Mehrtages-Wunsch, siehe `anfrage.tour_tage_anzahl`/katalog.py F04 – sonst bleibt es bei einer
    # Eintagestour), Lernaktivität (Kochkurs o.Ä.) bleibt fest bei einem Tag. Gedeckelt auf
    # mindestens 1 (sonst kein reservierter Tag trotz Treffer) und höchstens `tage` minus dem
    # Lernaktivitäts-Tag (sonst bliebe kein einziger Tag für die eigentliche Rundreise übrig).
    lernaktivitaet_tage = 1 if lernaktivitaet_beispiele else 0
    tour_tage = 0
    if tour_beispiele:
        gewuenscht = anfrage.tour_tage_anzahl or 1
        tour_tage = max(1, min(gewuenscht, tage - lernaktivitaet_tage))
    reservierte_tage = tour_tage + lernaktivitaet_tage
    tage_fuer_optimierung = tage - reservierte_tage

    # Basis-Tagesbudget: das vom LLM aus F20 interpretierte Zeitfenster (siehe schema.py
    # `tagesstart_minuten`/`tagesende_minuten`), wenn vorhanden – sonst der Konfigurations-Default.
    # Ein vom Nutzer tatsächlich genanntes Zeitfenster bestimmt damit direkt die Optimierung, statt
    # nur zur Anzeige berechnet und verworfen zu werden.
    basis_tagesbudget = (
        anfrage.tagesende_minuten - anfrage.tagesstart_minuten
        if anfrage.tagesstart_minuten is not None and anfrage.tagesende_minuten is not None
        and anfrage.tagesende_minuten > anfrage.tagesstart_minuten
        else EINSTELLUNGEN.standard_tagesbudget_minuten
    )
    tag1_budget = max(0, basis_tagesbudget - bewertete[0].alternative.dauer_minuten)
    tagesbudget_je_tag = [tag1_budget] + [basis_tagesbudget] * (tage_fuer_optimierung - 1)

    # Mittags-Zeitblock bei gewünschtem lokalem Kontakt (siehe katalog.py F19, Rückfrage-Ergebnis):
    # NUR "volle" Tage (nicht Anreise-, nicht Abreisetag) bekommen 120 Min. WENIGER Tagesbudget für
    # Optimierung 1 – der Algorithmus lässt den Block dadurch von selbst frei, statt ihn mit anderen
    # POIs vollzustopfen. WELCHER Markt/welches Café konkret reinpasst, entscheidet NICHT der
    # Algorithmus (siehe `_trenne_markt_beispiele_ab` unten). Ist der Abreisetag NICHT innerhalb
    # dieser Liste (weil ein Sonderkategorie-Tag – Tour/Lernaktivität – dahinter angehängt wird,
    # siehe `reservierte_tage` oben), ist JEDER Tag außer Tag 1 ein "voller" Tag.
    if anfrage.lokaler_kontakt_wichtig:
        letzter_voller_index = len(tagesbudget_je_tag) if reservierte_tage > 0 else len(tagesbudget_je_tag) - 1
        for index in range(1, letzter_voller_index):
            tagesbudget_je_tag[index] = max(0, tagesbudget_je_tag[index] - _LOKALER_KONTAKT_BLOCK_MINUTEN)

    # Harte Einschränkungen (Ernährung F18, Barrierefreiheit F09/F10/F15) VOR dem Präferenz-Scoring
    # aussortieren (siehe vertraeglichkeit.py) – ein Fisch-Restaurant bei genannter Fischallergie
    # soll erst gar nicht als Kandidat in Optimierung 1 landen.
    alle_pois, einschraenkungshinweise = filtere_pois_hart(
        alle_pois, anfrage, client, barrierefreiheit_strikt=barrierefreiheit_strikt
    )
    debug_sammlung.pois_nach_harten_einschraenkungen = list(alle_pois)
    # Essensbezogene Treffer raus (siehe `_trenne_beispielrestaurants_ab` – Projektkonversation,
    # revidiert: "das soll gar nicht in diesen Tagesplan integriert sein... einfach
    # Beispielrestaurants in der Nähe von der Unterkunft").
    alle_pois, beispielrestaurants = _trenne_beispielrestaurants_ab(alle_pois, depot_koordinaten)
    # Markt-/Café-Beispiele für den Mittags-Block NUR bei gewünschtem lokalem Kontakt – sonst
    # bleiben Cafés normale Kandidaten wie bisher (siehe `_trenne_markt_beispiele_ab`).
    markt_beispiele: list = []
    if anfrage.lokaler_kontakt_wichtig:
        alle_pois, markt_beispiele = _trenne_markt_beispiele_ab(alle_pois, depot_koordinaten)
    # Nähe-Gewichtung VOR der Kappung (nicht erst danach): zu diesem Zeitpunkt hätte ein rein
    # interessenbasiertes Ranking bereits geografisch verstreute Kandidaten endgültig ausgewählt
    # haben können, ohne dass eine spätere Distanz-Gewichtung daran noch etwas ändern könnte.
    if anfrage.barrierefreiheit_oder_eingeschraenkt():
        alle_pois = gewichte_nach_naehe_zum_depot(alle_pois, depot_koordinaten)
    pois = waehle_top_pois(
        alle_pois, anfrage.aktivitaeten_interessen, max_pois_fuer_reise(anfrage), anfrage.aktivitaeten_gewichtung
    )
    debug_sammlung.ausgewaehlte_pois = list(pois)

    instanz = erstelle_toptw_instanz(
        anfrage, pois,
        standard_tagesbudget_minuten=EINSTELLUNGEN.standard_tagesbudget_minuten,
        max_aktivitaetszeit_minuten=EINSTELLUNGEN.max_aktivitaetszeit_minuten,
        depot_koordinaten=depot_koordinaten,
        depot_name=anfrage.unterkunft_name or "Unterkunft",
        client=client,
        anzahl_tage_override=tage_fuer_optimierung,
    )
    tagesrouten = plane_gesamte_reise(instanz, tagesbudget_je_tag=tagesbudget_je_tag)
    # Reservierte Tage bekommen KEIN optimiertes Programm – die Beispiele werden in reiseplan.py
    # direkt eingetragen (siehe `Reiseplan.tour_tag_beispiele`/`lernaktivitaet_tag_beispiele`), ohne
    # Score/Auswahl durch Optimierung 1. Reihenfolge (Tour-Tage zuerst, dann der Lernaktivitäts-Tag
    # ganz am Ende) MUSS zur Zuordnung in reiseplan.py `_reservierte_sondertage` passen – bei
    # mehreren Tour-Tagen (siehe `tour_tage` oben) wird DIESELBE Beispiel-Auswahl auf jedem dieser
    # Tage gezeigt (keine künstlich aufgeblähte, echte-Daten-arme Auswahl nur um jeden Tag zu
    # füllen).
    for _ in range(tour_tage):
        tagesrouten.append(Tagesroute())
    if lernaktivitaet_beispiele:
        tagesrouten.append(Tagesroute())

    # Verkehrsmittel je Etappe NACHTRÄGLICH ergänzen (siehe aufbereitung.py
    # `ergaenze_anfahrt_modus_je_etappe`, "Variante B") – reine Anzeige-Ergänzung, verändert die
    # bereits feststehenden Ankunfts-/Abfahrtszeiten nicht.
    modi = modi_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    ergaenze_anfahrt_modus_je_etappe(client, depot_koordinaten, tagesrouten, modi)

    debug_sammlung.toptw_instanz = instanz
    debug_sammlung.tagesrouten = tagesrouten

    # Härtetest NUR für die An-/Abreise, NUR bei Bahn/Fernbus (siehe monte_carlo.py
    # `haertetest_teilstrecken`, ENTSCHEIDUNGSLOG.md Rückfrage): der POI-vor-Ort-Härtetest wurde
    # abgeschafft (die Verpassgefahr durch ein paar Minuten Fußweg/Fahrrad zwischen zwei
    # Sehenswürdigkeiten ist praktisch nie relevant) – riskant sind reale Bus-/Bahn-Umstiege.
    # `teilstrecken` ist NUR bei Bahn/Fernbus gefüllt (siehe google_maps.py); bei Auto oder falls
    # Google keine Schritt-Details lieferte (z.B. Mock-Modus) bleibt es leer -> kein Härtetest statt
    # eines erfundenen Ergebnisses. Hinreise UND Rückreise laufen jetzt UNABHÄNGIG (siehe eigener
    # `rueckreise_bewertete`-Abruf oben) – eine Rückverbindung kann andere Umstiege/Wartezeiten haben
    # als die Hinfahrt, ein gemeinsames Ergebnis wäre nicht mehr korrekt.
    hinreise_teilstrecken = bewertete[0].alternative.teilstrecken
    hinreise_robustheit = haertetest_teilstrecken(hinreise_teilstrecken) if hinreise_teilstrecken else None
    rueckreise_teilstrecken = rueckreise_bewertete[0].alternative.teilstrecken
    rueckreise_robustheit = haertetest_teilstrecken(rueckreise_teilstrecken) if rueckreise_teilstrecken else None
    debug_sammlung.hinreise_teilstrecken = hinreise_teilstrecken
    debug_sammlung.hinreise_robustheit = hinreise_robustheit
    debug_sammlung.rueckreise_teilstrecken = rueckreise_teilstrecken
    debug_sammlung.rueckreise_robustheit = rueckreise_robustheit

    # NICHT eingeplante Kandidaten: Optimierung 1 liefert weiterhin EINE realisierbare, optimierte
    # Tagesroute als konkreten Vorschlag, aber alle Kandidaten aus `pois`, die NICHT in dieser
    # Route gelandet sind (Zeitfenster/Budget hat nicht gereicht), werden zusätzlich als frei
    # kombinierbare Empfehlungen mitgegeben statt verworfen zu werden.
    eingeplante_ids = {besuch.poi.id for route in tagesrouten for besuch in route.besuche}
    weitere_empfehlungen = [poi for poi in pois if poi.id not in eingeplante_ids]

    # Grobe, informative Kostenschätzung (siehe kostenschaetzung.py) – NUR Anzeige/Vergleich mit
    # anfrage.budget_gesamt im Reiseplan, beeinflusst NICHT die obige Auswahl/Optimierung (siehe
    # Rückfrage beim Product Owner nach dem ersten Nutzertest).
    eingeplante_pois = [besuch.poi for route in tagesrouten for besuch in route.besuche]
    geschaetzte_kosten_euro, kosten_unvollstaendig = schaetze_gesamtkosten(
        bewertete[0].alternative.kosten_euro, rueckreise_bewertete[0].alternative.kosten_euro,
        anfrage.unterkunft_preisniveau, naechte=max(tage - 1, 1),
        eingeplante_pois=eingeplante_pois, tage=tage,
    )

    plan = Reiseplan(
        hinreise=bewertete[0],
        tagesrouten=tagesrouten,
        rueckreise=rueckreise_bewertete[0],
        hinreise_robustheit=hinreise_robustheit,
        rueckreise_robustheit=rueckreise_robustheit,
        unterkunft_name=anfrage.unterkunft_name,
        unterkunft_place_id=anfrage.unterkunft_place_id,
        unterkunft_foto_referenz=anfrage.unterkunft_foto_referenz,
        geschaetzte_kosten_euro=geschaetzte_kosten_euro,
        kosten_unvollstaendig=kosten_unvollstaendig,
        budget_gesamt=anfrage.budget_gesamt,
        # NUR für die Google-Maps-Routen-Links (siehe reiseplan.py `routen_link`) – die eigentliche
        # Optimierung nutzt `depot_koordinaten`/`anfrage.wohnort`/`ziel` bereits oben direkt.
        unterkunft_koordinaten=depot_koordinaten,
        wohnort=anfrage.wohnort,
        zielort=ziel,
        weitere_aktivitaeten_empfehlungen=weitere_empfehlungen,
        beispielrestaurants=beispielrestaurants,
        tour_tag_beispiele=tour_beispiele,
        tour_tage_anzahl=tour_tage,
        lernaktivitaet_tag_beispiele=lernaktivitaet_beispiele,
        markt_beispiele=markt_beispiele,
        einschraenkungshinweise=einschraenkungshinweise,
        lokales_leihfahrzeug_gewuenscht=lokales_leihfahrzeug_gewuenscht,
        lokaler_verleih_poi=lokaler_verleih_poi,
        # NUR gesetzt, wenn das LLM aus F20 tatsächlich eine Startuhrzeit interpretiert hat (siehe
        # schema.py) – sonst würde eine reine Standardannahme als scheinbar reale Uhrzeit
        # ausgegeben (Grundprinzip 1: keine erfundene Uhrzeit).
        tagesstart_minuten=anfrage.tagesstart_minuten,
        # Echte, offizielle Quelle statt einer selbst erfundenen Sicherheitsbewertung (Grundprinzip 1),
        # siehe reiseplan.py `SICHERHEITSHINWEISE_URL`/schema.py `sicherheit_bedenklich`.
        sicherheitshinweis=(
            f"Das LLM hat eine mögliche Sicherheitssorge erkannt – aktuelle Reise- und Sicherheitshinweise "
            f"des Auswärtigen Amts für Ihr Reiseziel finden Sie hier: {SICHERHEITSHINWEISE_URL} (bitte vor "
            "Abreise prüfen)."
            if anfrage.sicherheit_bedenklich
            else None
        ),
    )
    return plan, nudge, debug_sammlung

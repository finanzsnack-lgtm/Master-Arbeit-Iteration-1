"""
Optimierung 1 – Vor-Ort-Planung (TTDP als TOPTW, gelöst mit ILS).

Modellierung nach Vansteenwegen et al. (2009, 2011) und Gavalas et al.
(2014); siehe CLAUDE.md, Abschnitt "Optimierung 1 – Vor-Ort-Planung".

HINWEIS ZUR REFERENZIMPLEMENTIERUNG: CLAUDE.md nennt github.com/Constantino/
TOPTW (Python 2) als Referenz. Diese Datei lag für den Prototyp nicht lokal
vor und konnte daher nicht direkt portiert werden. Die folgende Implementierung
ist eine eigenständige Python-3-Umsetzung, die sich an der in CLAUDE.md
dokumentierten Algorithmus-Struktur orientiert (Greedy-Startlösung, ILS-
Schleife mit NoImprovementCounter, shake(R,S) als eskalierende Perturbation)
– kein Direkt-Port. Sobald die Referenzdatei vorliegt, kann diese
Implementierung gegen sie abgeglichen bzw. ersetzt werden.

Ort 0 = Depot (Unterkunft), Start- und Endpunkt jeder Tagesroute.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from src.api.typen import POI

# Mindestabstand (Minuten) zwischen zwei Besuchen AM SELBEN TAG, je Paar von `POI.besuchsklasse`-
# Werten (siehe typen.py) – Standardwert für `TOPTWInstanz.mindestabstand_je_klassenpaar`.
#
# WARUM (siehe Projektkonversation): "zwei Restaurants hintereinander direkt macht keinen Sinn,
# dabei geht es wirklich um Mahlzeiten" – zwei "mahlzeit"-Besuche (Restaurants) am selben Tag
# brauchen einen echten Abstand. Kaffee NACH einem Restaurant ist dagegen ausdrücklich erwünscht
# ("noch einen Kaffee zum Abschluss") – kein Eintrag für {"mahlzeit", "kaffee"} bedeutet: kein
# Mindestabstand. Kaffee und Bar bekommen "einen gewissen Abstand" zueinander (Nutzerwunsch, ohne
# konkrete Zahl genannt – 60 Minuten als begründeter Startwert, siehe ENTSCHEIDUNGSLOG.md).
# Selbst-Paare (z.B. zwei Bars am selben Abend) sind bewusst NICHT eingeschränkt ("wenn ich sage,
# ich geh in eine Bar oder in Kaffee, brauch ich das nicht separieren").
_STANDARD_MINDESTABSTAND_MINUTEN: dict[frozenset[str], int] = {
    frozenset({"mahlzeit"}): 4 * 60,
    frozenset({"kaffee", "bar"}): 60,
}


@dataclass
class TOPTWInstanz:
    """Eingabedaten für Optimierung 1 (siehe CLAUDE.md: "Eingabe je POI")."""

    pois: list[POI]
    tagesbudget_minuten: int
    anzahl_tage: int
    depot: POI = field(
        default_factory=lambda: POI(
            id=0, name="Unterkunft", kategorie="depot", x=0.0, y=0.0,
            score=0.0, required_time=0, opening=0, closing=24 * 60,
        )
    )
    # Konfigurierbar statt hartcodiert (siehe Projektkonversation: "wenn ich
    # angebe, ich möchte mich vor Ort mit dem Fahrrad fortbewegen, sollte das
    # die Planung beeinflussen") – Default bleibt Fußweg-Tempo, damit
    # bestehende Aufrufer ohne Angabe unverändert funktionieren. Wird von
    # aufbereitung.py::erstelle_toptw_instanz anhand von
    # `ReiseAnfrage.lokaler_transport_praeferenz` gesetzt.
    geschwindigkeit_kmh: float = 4.5
    # Reine Besuchszeit (Summe `required_time` der eingeplanten POIs, OHNE Fahrzeit dazwischen) –
    # härtere Nebenbedingung als `tagesbudget_minuten` (das Fahrzeit einschließt), siehe
    # config.py `max_aktivitaetszeit_minuten` (siehe Projektkonversation: "da wurden zehn Stunden
    # Aktivitäten geplant, das macht ja keiner"). Default sehr groß = praktisch keine zusätzliche
    # Einschränkung, damit bestehende Aufrufer/Tests ohne explizite Angabe unverändert funktionieren;
    # `erstelle_toptw_instanz` (aufbereitung.py) setzt den echten, konfigurierten Wert.
    max_aktivitaetszeit_minuten: int = 10**9
    # Mindestabstand zwischen zwei Besuchen AM SELBEN TAG, je Paar von `POI.besuchsklasse`-Werten
    # (siehe `_STANDARD_MINDESTABSTAND_MINUTEN` oben für die Begründung). Konfigurierbar wie die
    # anderen Nebenbedingungen, Default deckt bereits den besprochenen Fall ab.
    mindestabstand_je_klassenpaar: dict[frozenset[str], int] = field(
        default_factory=lambda: dict(_STANDARD_MINDESTABSTAND_MINUTEN)
    )
    # Pausen bei eingeschränkter Gehfähigkeit (siehe aufbereitung.py `erstelle_toptw_instanz`,
    # Projektkonversation: "Pausen eingeplant werden"): None = keine Pausenpflicht (Standardfall,
    # bestehende Aufrufer/Tests bleiben unverändert). Gesetzt: nach `pause_intervall_minuten`
    # kumulierter Fahr-/Aktivitätszeit wird vor dem nächsten Besuch zusätzlich `pause_dauer_minuten`
    # gewartet (siehe `simuliere_route`).
    pause_intervall_minuten: int | None = None
    pause_dauer_minuten: int = 20
    # Echte, vorab abgerufene Reisezeiten (siehe aufbereitung.py `erstelle_toptw_instanz`,
    # `google_maps.py::MapsClient.distanzmatrix`) – Schlüssel `(a.id, b.id)`, Wert Minuten.
    # UMSETZUNG von CLAUDE.md, "Zentrale Anpassung": "Distanzberechnung aus Koordinaten (Luftlinie)
    # durch echte Reisezeiten aus der Google Distance Matrix ersetzen" (siehe Projektkonversation:
    # "die Zeiten sind falsch" – Luftlinie ignoriert Straßennetz/Umwege komplett). None (Default) =
    # bestehendes Verhalten (Luftlinien-Schätzung), damit ältere Aufrufer/Tests ohne Matrix
    # unverändert funktionieren. Fehlt ein EINZELNES Paar in der Matrix (z.B. Google fand keine
    # Route), fällt NUR dieses Paar auf die Luftlinien-Schätzung zurück statt die ganze Route
    # scheitern zu lassen.
    reisezeiten_minuten: dict[tuple[int, int], int] | None = None
    # Maximale Anzahl POI-Besuche PRO TAG (siehe aufbereitung.py `erstelle_toptw_instanz`,
    # `max_pois_pro_tag_fuer_flexibilitaet`) – None (Default) = keine zusätzliche Einschränkung
    # (bestehendes Verhalten, Anzahl ergibt sich nur aus Zeitfenstern/Tagesbudget). Gesetzt: harte
    # Obergrenze, unabhängig davon, ob zeitlich noch mehr reinpassen würde (siehe
    # Projektkonversation: "wenn er sagt, er möchte flexibler sein, dann setzt man nur ein
    # gewisses Fenster an POIs in einen Tag, bei unflexibel ein höheres Maß").
    max_pois_pro_tag: int | None = None

    def reisezeit_minuten(self, a: POI, b: POI) -> int:
        """
        Bevorzugt eine ECHTE, vorab abgerufene Reisezeit (siehe `reisezeiten_minuten`), sonst
        Luftlinien-Schätzung (Koordinaten-Distanz / `geschwindigkeit_kmh`) als Fallback.
        """
        if self.reisezeiten_minuten is not None:
            echte_minuten = self.reisezeiten_minuten.get((a.id, b.id))
            if echte_minuten is not None:
                return echte_minuten
        distanz_km = math.dist((a.x, a.y), (b.x, b.y)) * 111  # grobe Umrechnung Grad -> km
        return max(1, round(distanz_km / self.geschwindigkeit_kmh * 60))


@dataclass
class Besuch:
    """Interner Berechnungszustand eines POI-Besuchs innerhalb einer Route (arrival/wait/leave nach CLAUDE.md)."""

    poi: POI
    ankunft: int = 0
    wartezeit: int = 0
    abfahrt: int = 0


@dataclass
class Tagesroute:
    besuche: list[Besuch] = field(default_factory=list)

    @property
    def score(self) -> float:
        return sum(besuch.poi.score for besuch in self.besuche)


def _mindestabstand_verletzt(instanz: TOPTWInstanz, route: Tagesroute, poi: POI, beginn_besuch: int) -> bool:
    """
    Prüft, ob `poi` (Besuchsbeginn `beginn_besuch`) zu einem BEREITS in `route` eingeplanten Besuch
    DERSELBEN oder einer gekoppelten Besuchsklasse zu nah liegt (siehe `TOPTWInstanz.
    mindestabstand_je_klassenpaar`). `route.besuche` ist beim Aufruf immer schon chronologisch
    (jeder bisherige Besuch endet vor `beginn_besuch`, da `simuliere_route` die Reihenfolge
    sequentiell abarbeitet) – die Lücke ist daher einfach `beginn_besuch - bestehender.abfahrt`.
    """
    if poi.besuchsklasse is None:
        return False
    for bestehender_besuch in route.besuche:
        andere_klasse = bestehender_besuch.poi.besuchsklasse
        if andere_klasse is None:
            continue
        mindestabstand = instanz.mindestabstand_je_klassenpaar.get(frozenset({poi.besuchsklasse, andere_klasse}))
        if mindestabstand is None:
            continue
        if beginn_besuch - bestehender_besuch.abfahrt < mindestabstand:
            return True
    return False


def simuliere_route(instanz: TOPTWInstanz, reihenfolge: list[POI]) -> Tagesroute | None:
    """
    Berechnet Ankunfts-/Warte-/Abfahrtszeiten für eine Reihenfolge von POIs an
    einem Tag. Gibt None zurück, wenn dabei ein Zeitfenster, das Tagesbudget,
    die maximale reine Aktivitätszeit ODER der Mindestabstand zwischen
    thematisch gekoppelten Besuchen (z.B. zwei Restaurants am selben Tag,
    siehe `TOPTWInstanz.mindestabstand_je_klassenpaar`) verletzt wird (harte
    Constraints, siehe CLAUDE.md bzw. `TOPTWInstanz.max_aktivitaetszeit_minuten`).

    Ist `TOPTWInstanz.pause_intervall_minuten` gesetzt (siehe aufbereitung.py
    `erstelle_toptw_instanz`, Projektkonversation: "Pausen eingeplant werden"), wird zusätzlich
    kumulierte Fahr-/Aktivitätszeit seit der letzten Pause mitgezählt: wird das Intervall
    überschritten, wartet die Route vor dem NÄCHSTEN Besuch `pause_dauer_minuten` zusätzlich (wie
    eine verlängerte Öffnungszeiten-Wartezeit) und der Zähler beginnt neu – keine eigene Pause als
    separater "Besuch", sondern zusätzliche Wartezeit, spart eine künstliche Pseudo-Station.

    Ist `TOPTWInstanz.max_pois_pro_tag` gesetzt (siehe aufbereitung.py
    `max_pois_pro_tag_fuer_flexibilitaet`, F05 Flexibilitätspräferenz), wird zusätzlich die reine
    ANZAHL Besuche pro Tag gedeckelt – unabhängig davon, ob zeitlich noch mehr reinpassen würde.
    """
    route = Tagesroute()
    aktueller_ort = instanz.depot
    uhrzeit = 0
    aktivitaetszeit = 0
    zeit_seit_pause = 0

    for poi in reihenfolge:
        fahrzeit = instanz.reisezeit_minuten(aktueller_ort, poi)
        ankunft = uhrzeit + fahrzeit
        zeit_seit_pause += fahrzeit
        pause = 0
        if instanz.pause_intervall_minuten is not None and zeit_seit_pause >= instanz.pause_intervall_minuten:
            pause = instanz.pause_dauer_minuten
            zeit_seit_pause = 0
        wartezeit = max(0, poi.opening - ankunft) + pause
        beginn_besuch = ankunft + wartezeit
        if beginn_besuch > poi.closing:
            return None  # Zeitfenster verpasst
        if _mindestabstand_verletzt(instanz, route, poi, beginn_besuch):
            return None  # z.B. zwei Restaurants zu dicht hintereinander am selben Tag
        if instanz.max_pois_pro_tag is not None and len(route.besuche) >= instanz.max_pois_pro_tag:
            return None  # Tages-Obergrenze erreicht (siehe Flexibilitätspräferenz, F05)
        abfahrt = beginn_besuch + poi.required_time
        route.besuche.append(Besuch(poi=poi, ankunft=ankunft, wartezeit=wartezeit, abfahrt=abfahrt))
        uhrzeit = abfahrt
        aktueller_ort = poi
        aktivitaetszeit += poi.required_time
        zeit_seit_pause += poi.required_time
        if aktivitaetszeit > instanz.max_aktivitaetszeit_minuten:
            return None  # reine Aktivitätszeit überschritten (siehe Projektkonversation: "10 Stunden Aktivitäten, das macht keiner")

    rueckweg = instanz.reisezeit_minuten(aktueller_ort, instanz.depot)
    if uhrzeit + rueckweg > instanz.tagesbudget_minuten:
        return None  # Tagesbudget überschritten

    return route


def _greedy_einfuegen(instanz: TOPTWInstanz, verfuegbare_pois: list[POI]) -> Tagesroute:
    """
    Konstruktionsheuristik: fügt iterativ den POI mit dem besten
    Nutzen-Kosten-Verhältnis (Score / zusätzlicher Zeitaufwand) an der
    Position ein, die die geringsten Mehrkosten verursacht – solange keine
    Zeitfenster- oder Budgetverletzung entsteht (siehe CLAUDE.md: "Greedy-
    Konstruktion als Startlösung").
    """
    route = Tagesroute()
    kandidaten = list(verfuegbare_pois)

    while kandidaten:
        beste_option = None  # (ratio, kandidaten_index, neue_reihenfolge)

        for i, poi in enumerate(kandidaten):
            for position in range(len(route.besuche) + 1):
                testreihenfolge = [besuch.poi for besuch in route.besuche]
                testreihenfolge.insert(position, poi)
                testroute = simuliere_route(instanz, testreihenfolge)
                if testroute is None:
                    continue

                bisherige_endzeit = route.besuche[-1].abfahrt if route.besuche else 0
                zusatzzeit = testroute.besuche[-1].abfahrt - bisherige_endzeit
                ratio = poi.score / max(1, zusatzzeit)

                if beste_option is None or ratio > beste_option[0]:
                    beste_option = (ratio, i, testreihenfolge)

        if beste_option is None:
            break  # kein POI mehr einfügbar, ohne eine Constraint zu verletzen

        _, index, neue_reihenfolge = beste_option
        route = simuliere_route(instanz, neue_reihenfolge)
        del kandidaten[index]

    return route


def _shake(route: Tagesroute, staerke: int, zufall: random.Random) -> list[POI]:
    """
    Perturbation: entfernt `staerke` zufällige POIs aus der Route (siehe
    CLAUDE.md: "shake(R,S) als Perturbation, entfernt Orte, R eskaliert").
    Gibt die verbleibende Reihenfolge zurück.
    """
    reihenfolge = [besuch.poi for besuch in route.besuche]
    anzahl_entfernen = min(staerke, len(reihenfolge))
    if anzahl_entfernen == 0:
        return reihenfolge
    entferne_indizes = set(zufall.sample(range(len(reihenfolge)), anzahl_entfernen))
    return [poi for i, poi in enumerate(reihenfolge) if i not in entferne_indizes]


def iterated_local_search(
    instanz: TOPTWInstanz,
    verfuegbare_pois: list[POI],
    max_ohne_verbesserung: int = 70,
    zufalls_seed: int | None = None,
) -> Tagesroute:
    """
    ILS nach Vansteenwegen et al. (2009): Greedy-Startlösung, danach
    wiederholt shake() + Greedy-Reparatur; eine neue Lösung wird nur bei
    Verbesserung akzeptiert. Abbruch nach `max_ohne_verbesserung` Iterationen
    ohne Verbesserung (Default 70, siehe CLAUDE.md:
    "while NoImprovementCounter < 70").
    """
    zufall = random.Random(zufalls_seed)

    beste_route = _greedy_einfuegen(instanz, verfuegbare_pois)
    ohne_verbesserung = 0
    staerke = 1

    while ohne_verbesserung < max_ohne_verbesserung:
        reduzierte_reihenfolge = _shake(beste_route, staerke, zufall)
        verbleibende_pois = [poi for poi in verfuegbare_pois if poi not in reduzierte_reihenfolge]

        reparierte_route = _greedy_einfuegen(instanz, verbleibende_pois)
        kombinierte_reihenfolge = reduzierte_reihenfolge + [
            besuch.poi for besuch in reparierte_route.besuche if besuch.poi not in reduzierte_reihenfolge
        ]
        kandidatenroute = simuliere_route(instanz, kombinierte_reihenfolge)

        if kandidatenroute is not None and kandidatenroute.score > beste_route.score:
            beste_route = kandidatenroute
            ohne_verbesserung = 0
            staerke = 1  # Eskalationsstufe nach Erfolg zurücksetzen
        else:
            ohne_verbesserung += 1
            staerke = min(staerke + 1, max(1, len(verfuegbare_pois)))  # R eskaliert

    return beste_route


def plane_gesamte_reise(
    instanz: TOPTWInstanz, max_ohne_verbesserung: int = 70, tagesbudget_je_tag: list[int] | None = None
) -> list[Tagesroute]:
    """
    Plant jeden Reisetag einzeln; bereits verplante POIs stehen an
    Folgetagen nicht mehr zur Verfügung.

    `tagesbudget_je_tag`, falls gesetzt: individuelles Tagesbudget PRO Tag
    (Länge = `instanz.anzahl_tage`) statt für alle Tage `instanz.
    tagesbudget_minuten` zu verwenden – siehe pipeline.py: Tag 1 wird um die
    Ankunftszeit der Hinreise verkürzt, sonst würde die Route so geplant, als
    stünde ab Reisebeginn das volle Tagesbudget zur Verfügung, obwohl ein
    Großteil davon schon durch die Anreise verbraucht ist (siehe Projekt-
    konversation).
    """
    verbleibende_pois = list(instanz.pois)
    tagesrouten: list[Tagesroute] = []

    for tag in range(instanz.anzahl_tage):
        tages_instanz = instanz if tagesbudget_je_tag is None else replace(instanz, tagesbudget_minuten=tagesbudget_je_tag[tag])
        route = iterated_local_search(tages_instanz, verbleibende_pois, max_ohne_verbesserung)
        tagesrouten.append(route)
        besuchte_ids = {besuch.poi.id for besuch in route.besuche}
        verbleibende_pois = [poi for poi in verbleibende_pois if poi.id not in besuchte_ids]

    return tagesrouten

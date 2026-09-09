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

    def reisezeit_minuten(self, a: POI, b: POI) -> int:
        """
        Luftlinien-Schätzung (siehe CLAUDE.md: "Zentrale Anpassung":
        Distanzberechnung aus Koordinaten durch echte Reisezeiten aus der
        Google Distance Matrix ersetzen, sobald der API-Key vorliegt).
        """
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


def simuliere_route(instanz: TOPTWInstanz, reihenfolge: list[POI]) -> Tagesroute | None:
    """
    Berechnet Ankunfts-/Warte-/Abfahrtszeiten für eine Reihenfolge von POIs an
    einem Tag. Gibt None zurück, wenn dabei ein Zeitfenster, das Tagesbudget
    ODER die maximale reine Aktivitätszeit verletzt wird (harte Constraints,
    siehe CLAUDE.md bzw. `TOPTWInstanz.max_aktivitaetszeit_minuten`).
    """
    route = Tagesroute()
    aktueller_ort = instanz.depot
    uhrzeit = 0
    aktivitaetszeit = 0

    for poi in reihenfolge:
        fahrzeit = instanz.reisezeit_minuten(aktueller_ort, poi)
        ankunft = uhrzeit + fahrzeit
        wartezeit = max(0, poi.opening - ankunft)
        beginn_besuch = ankunft + wartezeit
        if beginn_besuch > poi.closing:
            return None  # Zeitfenster verpasst
        abfahrt = beginn_besuch + poi.required_time
        route.besuche.append(Besuch(poi=poi, ankunft=ankunft, wartezeit=wartezeit, abfahrt=abfahrt))
        uhrzeit = abfahrt
        aktueller_ort = poi
        aktivitaetszeit += poi.required_time
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

"""
Fasst die Ergebnisse aus Optimierung 1, Optimierung 2 und dem
Monte-Carlo-Härtetest zu einer Rundreise nach UNWTO-Definition zusammen
(Hinreise -> Aufenthalt mit POIs -> Rückreise, siehe CLAUDE.md, Architektur-
Grundprinzip 4) und stellt die Ausgabe bereit (Text, HTML-Mail, Datei/JSON).
"""
from __future__ import annotations

import csv
import html
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from src.api.typen import POI, ReiseAlternative
from src.config import EINSTELLUNGEN
from src.optimierung.monte_carlo import RobustheitsErgebnis
from src.optimierung.toptw import Besuch, Tagesroute
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative

# Places API `place_id` -> klickbarer Google-Maps-Link. Funktioniert auch
# ohne Places-Details-Aufruf, siehe https://developers.google.com/maps/
# documentation/urls/get-started#search-place-id.
_MAPS_LINK_VORLAGE = "https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

# Echte, offizielle Quelle (verifiziert, siehe Projektkonversation) – KEIN
# länderspezifischer Deep-Link, da sich Auswärtiges-Amt-URLs pro Land nicht
# zuverlässig aus dem Ländernamen ableiten lassen (Grundprinzip 1: keine
# geratenen URLs). Nutzer:innen navigieren von hier zu ihrem Reiseland.
SICHERHEITSHINWEISE_URL = "https://www.auswaertiges-amt.de/de/reiseundsicherheit/reise-und-sicherheitshinweise"


def maps_link(place_id: str | None) -> str | None:
    return _MAPS_LINK_VORLAGE.format(place_id=place_id) if place_id else None


# Deutsche Anzeige-Labels für Googles Distance-Matrix-`mode`-Werte (siehe `Besuch.anfahrt_modus`,
# aufbereitung.py `ergaenze_anfahrt_modus_je_etappe`) – NUR für die Anzeige, keine eigene Logik.
_VERKEHRSMITTEL_LABEL_JE_MODUS = {
    "walking": "zu Fuß", "bicycling": "mit dem Fahrrad",
    "transit": "mit öffentlichen Verkehrsmitteln", "driving": "mit dem Auto",
}


def _verkehrsmittel_label(modus: str | None) -> str:
    """Leerstring statt einer erfundenen Angabe, wenn `modus` (noch) nicht gesetzt ist (Grundprinzip 1)."""
    return _VERKEHRSMITTEL_LABEL_JE_MODUS.get(modus, "") if modus else ""


def _hinreise_ziel_fuer_link(plan: "Reiseplan") -> tuple[float, float] | str | None:
    """
    Präziser Hin-/Rückreise-Endpunkt für `routen_link`: die genaue Unterkunft (Koordinaten), sobald
    bestätigt – NUR wenn sie (noch) fehlt, Rückfall auf den groben Zielort-Namen, statt gar keinen
    Link zu zeigen (siehe Nutzerfeedback: der bisherige Link zur Zielstadt allein war "nur halbwegs
    gut", eine echte Adresse zeigt die tatsächlich gebuchte Route in Google Maps).
    """
    return plan.unterkunft_koordinaten or plan.zielort


# "Bahn"/"Fernbus"/"Auto" (siehe ReiseAlternative.verkehrsmittel, google_maps.py `reisealternativen`)
# -> Googles Directions-URL-`travelmode` (siehe `routen_link` unten). "Bahn"/"Fernbus" werden beide
# über Googles `mode=transit` abgefragt (kein eigener Fernbus-Modus, siehe google_maps.py) – für den
# Link reicht "transit" bei beiden.
_TRAVELMODE_JE_VERKEHRSMITTEL = {"Bahn": "transit", "Fernbus": "transit", "Auto": "driving"}


def routen_link(ursprung: tuple[float, float] | str | None, ziel: tuple[float, float] | str | None, travelmode: str | None) -> str | None:
    """
    Google-Maps-Directions-Link (https://developers.google.com/maps/documentation/urls/get-started
    #directions-action) – öffnet die Route direkt mit Start-/Zielpunkt UND (falls bekannt) dem
    tatsächlich geplanten Verkehrsmittel vorausgewählt, statt wie `maps_link` nur einen einzelnen
    Ort zu zeigen. `ursprung`/`ziel` als Koordinaten-Tupel (POI-zu-POI-Etappen, exakt) ODER als
    Orts-/Adressname-String (An-/Abreise, wo keine Koordinaten vorliegen – Google löst Ortsnamen
    selbst auf). None, wenn `ursprung` oder `ziel` fehlt (z.B. Unterkunft-Koordinaten unbekannt) –
    kein Link mit geratenen Punkten (Grundprinzip 1).
    """
    if ursprung is None or ziel is None:
        return None

    def formatiere(punkt: tuple[float, float] | str) -> str:
        return f"{punkt[0]},{punkt[1]}" if isinstance(punkt, tuple) else punkt

    parameter = {"api": "1", "origin": formatiere(ursprung), "destination": formatiere(ziel)}
    if travelmode:
        parameter["travelmode"] = travelmode
    return f"https://www.google.com/maps/dir/?{urlencode(parameter)}"


def _format_dauer(minuten: int) -> str:
    """"Xh Ymin" statt roher Minutenzahl (siehe Projektkonversation: erzählter statt tabellarischer
    Tagesplan) – bewusst KEINE Uhrzeit (z.B. "09:15"): ein reales Abfahrts-/Ankunftsdatum mit fester
    Uhrzeit liegt nirgends vor, eine erfundene Uhrzeit wäre ein Verstoß gegen Grundprinzip 1. Alle
    Zeitangaben bleiben deshalb relativ (Tag 1: seit Ankunft, weitere Tage: seit Tagesbeginn)."""
    stunden, rest_minuten = divmod(minuten, 60)
    if stunden == 0:
        return f"{rest_minuten}min"
    if rest_minuten == 0:
        return f"{stunden}h"
    return f"{stunden}h {rest_minuten}min"


def _format_uhrzeit(minuten_seit_mitternacht: int) -> str:
    """"HH:MM", auf einen 24h-Tag umgebrochen (ein Besuch nach Mitternacht bleibt dadurch lesbar)."""
    minuten_seit_mitternacht %= 24 * 60
    stunden, rest_minuten = divmod(minuten_seit_mitternacht, 60)
    return f"{stunden:02d}:{rest_minuten:02d}"


def _fahrzeit_vor_besuch(besuche: list[Besuch], index: int) -> int:
    """
    Reine Fahrzeit (Minuten) unmittelbar VOR `besuche[index]` – von der Unterkunft (erster Besuch
    des Tages) bzw. vom vorherigen Besuch. Keine Schätzung nötig: `toptw.py::simuliere_route` setzt
    `ankunft = uhrzeit_vorher + fahrzeit` (Tagesbeginn `uhrzeit=0`), die Fahrzeit steckt also bereits
    exakt in der Differenz zwischen dieser Ankunft und der vorherigen Abfahrt (bzw. für den ersten
    Besuch direkt in `ankunft` selbst, da `uhrzeit_vorher` zu Tagesbeginn 0 ist).
    """
    if index == 0:
        return besuche[0].ankunft
    return besuche[index].ankunft - besuche[index - 1].abfahrt


def _teilstrecken_zeilen(alternative: ReiseAlternative, praefix: str = "  ") -> list[str]:
    """
    Zeilen für die einzelnen Umstiege/Linien einer Bahn-/Fernbus-Alternative
    (siehe `Teilstrecke` in typen.py) – ersetzt die reine Gesamtdauer durch
    die echte Fahrt-Kette (Projektkonversation: "nicht nur eine Stunde,
    sondern 30 min dahin, dann umsteigen mit 5 min Wartezeit, dann 25 min
    Fahrzeit"). Leer, wenn Google keine Schritt-Details geliefert hat (z.B.
    Auto, oder Mock-Modus) – dann bleibt es bei der Gesamtdauer.
    """
    zeilen = []
    for teilstrecke in alternative.teilstrecken:
        if teilstrecke.wartezeit_minuten is not None:
            wartezeit_text = (
                "sofortiger Anschluss" if teilstrecke.wartezeit_minuten == 0 else f"{teilstrecke.wartezeit_minuten} min Wartezeit"
            )
            zeilen.append(f"{praefix}Umstieg in {teilstrecke.von} ({wartezeit_text})")
        if teilstrecke.modus == "TRANSIT":
            linie_text = f"{teilstrecke.linie}: " if teilstrecke.linie else ""
            zeilen.append(f"{praefix}{linie_text}{teilstrecke.von} → {teilstrecke.nach} ({teilstrecke.dauer_minuten} min)")
        else:
            zeilen.append(f"{praefix}Fußweg ({teilstrecke.dauer_minuten} min)")
    return zeilen


def _zeitpunkt_text(plan: "Reiseplan", tag_nr: int, minuten_seit_tagesbeginn: int, praefix: str) -> str:
    """`praefix` + relative Dauer (Standard, siehe `_format_dauer`) ODER `praefix` + echte Uhrzeit
    (NUR ab Tag 2 UND nur, wenn der Nutzer F20 tagesstart_praeferenz tatsächlich beantwortet hat,
    siehe `Reiseplan.tagesstart_minuten`) – Tag 1 bleibt IMMER relativ, weil die tatsächliche
    Ankunftsuhrzeit der Hinreise nirgends bekannt ist (kein reales Ticket vorhanden, Grundprinzip 1)."""
    if tag_nr == 1 or plan.tagesstart_minuten is None:
        return f"{praefix} {_format_dauer(minuten_seit_tagesbeginn)}"
    return f"{praefix} {_format_uhrzeit(plan.tagesstart_minuten + minuten_seit_tagesbeginn)} Uhr"


def _verleih_hinweis_text(plan: "Reiseplan") -> str | None:
    """Formuliert `lokales_leihfahrzeug_gewuenscht`/`lokaler_verleih_poi` (siehe Reiseplan-Doku) als
    fertigen Satz: echter Fund mit Link, oder ehrliche Fehlanzeige – nie ein erfundener Verleih."""
    fahrzeug = plan.lokales_leihfahrzeug_gewuenscht
    if fahrzeug is None:
        return None
    if plan.lokaler_verleih_poi is None:
        return (
            f"Sie möchten sich vor Ort mit einem geliehenen {fahrzeug} fortbewegen – in der Nähe "
            "konnten wir aber keinen Verleih finden. Bitte selbst vor Ort recherchieren."
        )
    poi = plan.lokaler_verleih_poi
    zusatz = " (laut Google als Fahrradgeschäft gelistet, keine Verleih-Garantie)" if fahrzeug == "Fahrrad" else ""
    satz = f"Für Ihre gewünschte lokale Fortbewegung mit geliehenem {fahrzeug} haben wir in der Nähe gefunden: {poi.name}{zusatz}"
    link = maps_link(poi.place_id)
    if link:
        satz += f" — {link}"
    return satz + " (bitte Verfügbarkeit/Konditionen vor Ort bestätigen)."


@dataclass
class Reiseplan:
    hinreise: BewerteteAlternative
    tagesrouten: list[Tagesroute]
    rueckreise: BewerteteAlternative
    # Monte-Carlo-Härtetest AUSSCHLIESSLICH für die An-/Abreise (siehe monte_carlo.py
    # `haertetest_teilstrecken`, ENTSCHEIDUNGSLOG.md) – None, wenn keine Teilstrecken-Daten
    # vorlagen (Auto, oder Mock-Modus ohne Schritt-Details). Der frühere POI-vor-Ort-Härtetest
    # wurde abgeschafft (siehe dort für die Begründung).
    hinreise_robustheit: RobustheitsErgebnis | None = None
    rueckreise_robustheit: RobustheitsErgebnis | None = None
    # Die im Dialog (F15) gesuchte und vom Nutzer bestätigte Unterkunft (siehe schema.py
    # `ReiseAnfrage.unterkunft_name`) – None, wenn keine Unterkunft gefunden wurde.
    unterkunft_name: str | None = None
    # place_id derselben Unterkunft, für einen klickbaren Google-Maps-Link in der
    # Mail-/Textausgabe (siehe maps_link unten). None im Mock-Modus.
    unterkunft_place_id: str | None = None
    # Places-Foto-Referenz derselben Unterkunft (siehe schema.py `unterkunft_foto_referenz`) – für
    # die Bild-Karte im fertigen Reiseplan der Web-UI (webapp.py/src/ausgabe/fotos.py). None im
    # Mock-Modus oder wenn Places kein Foto zu dieser Unterkunft hat.
    unterkunft_foto_referenz: str | None = None
    # Grobe, informative Gesamtkostenschätzung PRO PERSON (Aktivitäten+Unterkunft+Fahrt+
    # Verpflegungspauschale, siehe src/optimierung/kostenschaetzung.py) – None nur, wenn keine
    # Hinreise berechnet werden konnte (praktisch nie, plane_reise bricht in dem Fall vorher ab).
    # Rein informativ, beeinflusst NICHT die Auswahl in Optimierung 1.
    geschaetzte_kosten_euro: float | None = None
    # True, wenn die Unterkunft kein Places-Preisniveau hatte und daher nicht in
    # `geschaetzte_kosten_euro` eingerechnet werden konnte (siehe kostenschaetzung.py) – macht die
    # Schätzung erkennbar unvollständig statt fälschlich vollständig wirkend.
    kosten_unvollstaendig: bool = False
    # Direkt aus `ReiseAnfrage.budget_gesamt` übernommen, NUR für den Vergleichstext in
    # als_text/als_html – Reiseplan bleibt sonst frei von ReiseAnfrage-Abhängigkeiten.
    budget_gesamt: float | None = None
    # Koordinaten derselben Unterkunft (siehe `ReiseAnfrage.unterkunft_koordinaten`) – NUR für die
    # Google-Maps-ROUTEN-Links der ersten Etappe jedes Tages (siehe `routen_link`/`als_text`), die
    # tatsächliche Optimierung nutzt weiterhin `anfrage.unterkunft_koordinaten` direkt (pipeline.py).
    # None, wenn keine Unterkunft bestätigt wurde – dann bleibt der Routen-Link für diese eine
    # Etappe schlicht weg, statt einen geratenen Startpunkt zu erfinden (Grundprinzip 1).
    unterkunft_koordinaten: tuple[float, float] | None = None
    # Wohnort (F08) und geplanter Zielort, NUR für den Hin-/Rückreise-Routen-Link (siehe `als_text`)
    # – Reiseplan speichert sonst bewusst keine rohen Ortsnamen, hier aber nötig, weil für die
    # An-/Abreise (anders als POI-zu-POI) keine Koordinaten vorliegen.
    wohnort: str | None = None
    zielort: str | None = None
    # Nur gesetzt, wenn das LLM aus dem Gesprächskontext eine echte Sicherheitssorge erkannt hat
    # (siehe schema.py `sicherheit_bedenklich`) – Verweis auf eine ECHTE, offizielle Quelle statt
    # einer selbst erfundenen Sicherheitseinschätzung (Grundprinzip 1).
    sicherheitshinweis: str | None = None
    # POIs, die als Kandidaten gefunden, aber NICHT in die von Optimierung 1
    # gewählte Tagesroute übernommen wurden (Zeitfenster/Budget hat nicht für
    # alle gereicht, siehe pipeline.py) – werden NICHT verworfen, sondern als
    # frei kombinierbare Zusatz-Empfehlungen mitgegeben (siehe Projekt-
    # konversation: "eine grobe Struktur liefern, er trifft dann Entscheidungen"
    # statt einer vollkommen fertig geplanten Reise).
    weitere_aktivitaeten_empfehlungen: list[POI] = field(default_factory=list)
    # Hinweise zu Kandidaten, die einer genannten harten Einschränkung
    # (Ernährung F18, Barrierefreiheit F09/F10/F15) widersprechen könnten,
    # aber NICHT ausgefiltert werden konnten, weil keine unbedenkliche
    # Alternative gefunden wurde (siehe src/datenaufbereitung/
    # vertraeglichkeit.py – kein Verschweigen des Konflikts, aber auch kein
    # Erfinden einer nicht existierenden Alternative, Grundprinzip 1).
    einschraenkungshinweise: list[str] = field(default_factory=list)
    # "Fahrrad"/"Auto", NUR gesetzt, wenn F14 (lokaler_transport_praeferenz) erkennbar einen Wunsch
    # nach einem vor Ort GELIEHENEN Fahrzeug ausdrückt (siehe aufbereitung.py `erkenne_leihwunsch`,
    # z.B. Anreise mit Bahn, vor Ort aber Fahrrad gewünscht -> im Dialog nachgefragt, ob eigenes
    # Fahrzeug dabei ist oder ein Verleih gesucht werden soll). None = kein solcher Wunsch erkannt.
    lokales_leihfahrzeug_gewuenscht: str | None = None
    # Der real gefundene Verleih-Kandidat (siehe pipeline.py), falls einer existiert – None sowohl
    # wenn kein Leihwunsch vorliegt ALS AUCH wenn einer vorliegt, aber nichts gefunden wurde (siehe
    # `lokales_leihfahrzeug_gewuenscht`, um die beiden Fälle zu unterscheiden). Nie erfunden
    # (Grundprinzip 1) – für Fahrräder liefert Google nur "bicycle_store" (Laden, keine Verleih-
    # Garantie, siehe google_maps.py), daher der Formulierungs-Hinweis in der Ausgabe.
    lokaler_verleih_poi: POI | None = None
    # Startuhrzeit (Minuten seit Mitternacht) NUR gesetzt, wenn F20 (tagesstart_praeferenz) vom LLM
    # tatsächlich in `ReiseAnfrage.tagesstart_minuten` interpretiert wurde (siehe pipeline.py) –
    # sonst würde eine reine Standardannahme als scheinbar reale Uhrzeit ausgegeben (Grundprinzip
    # 1). Ermöglicht echte Uhrzeiten AB TAG 2 in
    # der Ausgabe (siehe `_zeitpunkt_text`) – Tag 1 bleibt relativ, weil die tatsächliche
    # Ankunftsuhrzeit der Hinreise nirgends bekannt ist (kein reales Fahrplan-Ticket vorhanden).
    tagesstart_minuten: int | None = None


_EINLEITUNG = (
    "Das Folgende ist eine grobe Struktur auf Basis Ihrer Angaben – kein fertig gebuchter Plan. Unterkunft "
    "und Aktivitäten sind Empfehlungen, die zu Ihren Präferenzen passen; die Tagesrouten zeigen EIN Beispiel, "
    "wie sich Ihre gewünschten Aktivitäten zeitlich realistisch kombinieren lassen. Schauen Sie sich in Ruhe "
    "an, was Ihnen gefällt, und stellen Sie sich Ihre Reise daraus selbst zusammen."
)


def _uhrzeit_hinweis_text(plan: "Reiseplan") -> str | None:
    """Einmaliger Hinweis, WARUM ab Tag 2 echte Uhrzeiten stehen, Tag 1 aber nicht – nur relevant,
    wenn `tagesstart_minuten` überhaupt gesetzt ist (siehe Reiseplan-Doku)."""
    if plan.tagesstart_minuten is None:
        return None
    return (
        f"Die Uhrzeiten ab Tag 2 basieren auf Ihrer angegebenen Tagesstart-Präferenz (ca. "
        f"{_format_uhrzeit(plan.tagesstart_minuten)} Uhr). Tag 1 hängt von der tatsächlichen "
        "Ankunftszeit der Hinreise ab, die nirgends real feststeht, und bleibt daher bei relativen "
        "Zeitangaben."
    )


def _kosten_text(plan: "Reiseplan") -> str | None:
    """Formuliert `geschaetzte_kosten_euro`/`budget_gesamt` (siehe kostenschaetzung.py) als Satz –
    None nur, wenn keine Schätzung berechnet wurde (praktisch nie, siehe Reiseplan-Doku)."""
    if plan.geschaetzte_kosten_euro is None:
        return None
    text = (
        "Geschätzte Gesamtkosten pro Person (grobe Schätzung auf Basis von Googles Preisniveau-"
        f"Einstufung, keine echten Einzelpreise): ca. {plan.geschaetzte_kosten_euro:.0f} € "
        "(Unterkunft, Aktivitäten, An-/Abreise, Verpflegungspauschale)"
        + (", unvollständig – für die Unterkunft lag kein Preisniveau vor" if plan.kosten_unvollstaendig else "")
        + "."
    )
    if plan.budget_gesamt is not None:
        differenz = plan.budget_gesamt - plan.geschaetzte_kosten_euro
        if differenz >= 0:
            text += f" Das liegt im Rahmen Ihres angegebenen Budgets von {plan.budget_gesamt:.0f} € (ca. {differenz:.0f} € Puffer)."
        else:
            text += f" Das übersteigt Ihr angegebenes Budget von {plan.budget_gesamt:.0f} € um ca. {abs(differenz):.0f} €."
    return text


def _robustheit_text(richtung: str, robustheit: "RobustheitsErgebnis | None") -> str | None:
    """Formuliert EIN Härtetest-Ergebnis (Hinreise ODER Rückreise, siehe monte_carlo.py
    `haertetest_teilstrecken`) als Satz – None, wenn kein Härtetest lief (z.B. Auto, kein
    Umstiegsrisiko)."""
    if robustheit is None:
        return None
    status = "robust" if robustheit.ist_robust else "NICHT robust – Anschluss-Risiko"
    return (
        f"Verbindungssicherheit {richtung}: {robustheit.quote_ohne_verletzung:.1%} der "
        f"{robustheit.laeufe} simulierten Läufe ohne verpassten Anschluss ({status})."
    )


def als_text(plan: Reiseplan) -> str:
    """Erzeugt eine lesbare Textzusammenfassung des Reiseplans."""
    zeilen = ["=== Reiseplan ===", "", _EINLEITUNG, ""]
    uhrzeit_hinweis = _uhrzeit_hinweis_text(plan)
    if uhrzeit_hinweis:
        zeilen.append(uhrzeit_hinweis)
        zeilen.append("")
    if plan.einschraenkungshinweise:
        for hinweis in plan.einschraenkungshinweise:
            zeilen.append(hinweis)
        zeilen.append("")
    verleih_hinweis = _verleih_hinweis_text(plan)
    if verleih_hinweis:
        zeilen.append(verleih_hinweis)
        zeilen.append("")
    if plan.unterkunft_name:
        zeile = f"Unterkunft: {plan.unterkunft_name}"
        link = maps_link(plan.unterkunft_place_id)
        if link:
            zeile += f" — {link}"
        zeilen.append(zeile)
        zeilen.append("")
    kosten_text = _kosten_text(plan)
    if kosten_text:
        zeilen.append(kosten_text)
        zeilen.append("")
    if plan.sicherheitshinweis:
        zeilen.append(plan.sicherheitshinweis)
        zeilen.append("")
    zeilen.append(
        f"Hinreise: {plan.hinreise.alternative.verkehrsmittel} "
        f"({plan.hinreise.alternative.dauer_minuten} min, "
        f"{plan.hinreise.alternative.kosten_euro:.2f} €, "
        f"{plan.hinreise.co2_kg:.1f} kg CO2)"
    )
    zeilen.extend(_teilstrecken_zeilen(plan.hinreise.alternative))
    hinreise_link = routen_link(
        plan.wohnort, _hinreise_ziel_fuer_link(plan), _TRAVELMODE_JE_VERKEHRSMITTEL.get(plan.hinreise.alternative.verkehrsmittel)
    )
    if hinreise_link:
        zeilen.append(f"  Route: {hinreise_link}")
    zeilen.append("")

    letzter_tag = len(plan.tagesrouten)
    for tag_nr, tagesroute in enumerate(plan.tagesrouten, start=1):
        ist_ankunftstag = tag_nr == 1
        zeilen.append(f"Tag {tag_nr}" + (" (Ankunft)" if ist_ankunftstag else "") + " – unser Vorschlag:")
        if ist_ankunftstag:
            zeilen.append(
                f"  Ankunft mit {plan.hinreise.alternative.verkehrsmittel} nach "
                f"{_format_dauer(plan.hinreise.alternative.dauer_minuten)} – danach Check-in in der Unterkunft."
            )
        if not tagesroute.besuche:
            zeilen.append("  (kein Programm eingeplant)")
        else:
            zeilen.append("  Ab Ankunft:" if ist_ankunftstag else "  Ab Tagesbeginn:")
            for index, besuch in enumerate(tagesroute.besuche):
                fahrzeit = _fahrzeit_vor_besuch(tagesroute.besuche, index)
                herkunft = "Unterkunft" if index == 0 else tagesroute.besuche[index - 1].poi.name
                herkunft_koordinaten = (
                    plan.unterkunft_koordinaten if index == 0
                    else (tagesroute.besuche[index - 1].poi.x, tagesroute.besuche[index - 1].poi.y)
                )
                verkehrsmittel = _verkehrsmittel_label(besuch.anfahrt_modus)
                zusatz = f" ({verkehrsmittel})" if verkehrsmittel else ""
                etappen_zeile = f"    → {fahrzeit} Min.{zusatz} von {herkunft}"
                etappen_link = routen_link(herkunft_koordinaten, (besuch.poi.x, besuch.poi.y), besuch.anfahrt_modus)
                if etappen_link:
                    etappen_zeile += f" — {etappen_link}"
                zeilen.append(etappen_zeile)
                pause_hinweis = f", davon {besuch.wartezeit} Min. Pause/Wartezeit" if besuch.wartezeit > 0 else ""
                zeile = (
                    f"    {_zeitpunkt_text(plan, tag_nr, besuch.ankunft, 'nach')}: {besuch.poi.name} "
                    f"({_zeitpunkt_text(plan, tag_nr, besuch.abfahrt, 'bis')}{pause_hinweis}, Score {besuch.poi.score:.1f})"
                )
                link = maps_link(besuch.poi.place_id)
                if link:
                    zeile += f" — {link}"
                zeilen.append(zeile)
            if tag_nr != letzter_tag:
                zeilen.append("  Rückweg zur Unterkunft, Zeit zum Umziehen – der Abend steht für ein Abendessen in der Nähe zur freien Verfügung.")
        zeilen.append("")

    if plan.weitere_aktivitaeten_empfehlungen:
        zeilen.append("Weitere Empfehlungen in der Nähe (nicht im Vorschlag oben, zum selbst Ergänzen/Tauschen):")
        for poi in plan.weitere_aktivitaeten_empfehlungen:
            zeile = f"  - {poi.name} ({poi.kategorie}, ca. {poi.required_time} Minuten)"
            link = maps_link(poi.place_id)
            if link:
                zeile += f" — {link}"
            zeilen.append(zeile)
        zeilen.append("")

    zeilen.append(
        f"Rückreise: {plan.rueckreise.alternative.verkehrsmittel} "
        f"({plan.rueckreise.alternative.dauer_minuten} min, "
        f"{plan.rueckreise.alternative.kosten_euro:.2f} €, "
        f"{plan.rueckreise.co2_kg:.1f} kg CO2)"
    )
    zeilen.extend(_teilstrecken_zeilen(plan.rueckreise.alternative))
    rueckreise_link = routen_link(
        _hinreise_ziel_fuer_link(plan), plan.wohnort, _TRAVELMODE_JE_VERKEHRSMITTEL.get(plan.rueckreise.alternative.verkehrsmittel)
    )
    if rueckreise_link:
        zeilen.append(f"  Route: {rueckreise_link}")

    hinreise_robustheit_text = _robustheit_text("Hinreise", plan.hinreise_robustheit)
    rueckreise_robustheit_text = _robustheit_text("Rückreise", plan.rueckreise_robustheit)
    if hinreise_robustheit_text or rueckreise_robustheit_text:
        zeilen.append("")
        if hinreise_robustheit_text:
            zeilen.append(hinreise_robustheit_text)
        if rueckreise_robustheit_text:
            zeilen.append(rueckreise_robustheit_text)

    return "\n".join(zeilen)


def als_html(plan: Reiseplan) -> str:
    """
    Erzeugt eine HTML-Fassung des Reiseplans mit klickbaren Google-Maps-
    Links zu Unterkunft und POIs (siehe Projektkonversation: Nutzer möchte
    Unterkünfte/Aktivitäten in der Mail direkt anklicken können). Nutzt
    dieselben Daten wie als_text(), nur als <a href> statt Klartext-URL.
    """

    def esc(text: str) -> str:
        return html.escape(str(text))

    def link_html(name: str, place_id: str | None) -> str:
        link = maps_link(place_id)
        return f'<a href="{esc(link)}">{esc(name)}</a>' if link else esc(name)

    def routen_link_html(link: str | None) -> str:
        return f' <a href="{esc(link)}">Route in Google Maps ansehen</a>' if link else ""

    def teilstrecken_html(alternative: ReiseAlternative) -> str:
        zeilen = _teilstrecken_zeilen(alternative, praefix="")
        if not zeilen:
            return ""
        eintraege = "".join(f"<li>{esc(zeile)}</li>" for zeile in zeilen)
        return f"<ul>{eintraege}</ul>"

    teile = ["<h2>Reiseplan</h2>", f"<p>{esc(_EINLEITUNG)}</p>"]

    uhrzeit_hinweis = _uhrzeit_hinweis_text(plan)
    if uhrzeit_hinweis:
        teile.append(f"<p>{esc(uhrzeit_hinweis)}</p>")

    if plan.einschraenkungshinweise:
        for hinweis in plan.einschraenkungshinweise:
            teile.append(f"<p>{esc(hinweis)}</p>")

    verleih_hinweis = _verleih_hinweis_text(plan)
    if verleih_hinweis:
        teile.append(f"<p>{esc(verleih_hinweis)}</p>")

    if plan.unterkunft_name:
        teile.append(
            "<p><strong>Unterkunft:</strong> "
            f"{link_html(plan.unterkunft_name, plan.unterkunft_place_id)}</p>"
        )

    kosten_text = _kosten_text(plan)
    if kosten_text:
        teile.append(f"<p>{esc(kosten_text)}</p>")

    if plan.sicherheitshinweis:
        teile.append(f"<p>{esc(plan.sicherheitshinweis)}</p>")

    hinreise_link = routen_link(
        plan.wohnort, _hinreise_ziel_fuer_link(plan), _TRAVELMODE_JE_VERKEHRSMITTEL.get(plan.hinreise.alternative.verkehrsmittel)
    )
    teile.append(
        "<p><strong>Hinreise:</strong> "
        f"{esc(plan.hinreise.alternative.verkehrsmittel)} "
        f"({plan.hinreise.alternative.dauer_minuten} min, "
        f"{plan.hinreise.alternative.kosten_euro:.2f} €, "
        f"{plan.hinreise.co2_kg:.1f} kg CO2){routen_link_html(hinreise_link)}</p>"
    )
    teile.append(teilstrecken_html(plan.hinreise.alternative))

    letzter_tag = len(plan.tagesrouten)
    for tag_nr, tagesroute in enumerate(plan.tagesrouten, start=1):
        ist_ankunftstag = tag_nr == 1
        teile.append(f"<h3>Tag {tag_nr}{' (Ankunft)' if ist_ankunftstag else ''} – unser Vorschlag</h3>")
        if ist_ankunftstag:
            teile.append(
                f"<p>Ankunft mit {esc(plan.hinreise.alternative.verkehrsmittel)} nach "
                f"{_format_dauer(plan.hinreise.alternative.dauer_minuten)} – danach Check-in in der Unterkunft.</p>"
            )
        if not tagesroute.besuche:
            teile.append("<p>(kein Programm eingeplant)</p>")
            continue
        teile.append(f"<p>{'Ab Ankunft' if ist_ankunftstag else 'Ab Tagesbeginn'}:</p><ul>")
        for index, besuch in enumerate(tagesroute.besuche):
            fahrzeit = _fahrzeit_vor_besuch(tagesroute.besuche, index)
            herkunft = "Unterkunft" if index == 0 else tagesroute.besuche[index - 1].poi.name
            herkunft_koordinaten = (
                plan.unterkunft_koordinaten if index == 0
                else (tagesroute.besuche[index - 1].poi.x, tagesroute.besuche[index - 1].poi.y)
            )
            verkehrsmittel = _verkehrsmittel_label(besuch.anfahrt_modus)
            verkehrsmittel_zusatz = f" ({esc(verkehrsmittel)})" if verkehrsmittel else ""
            etappen_link = routen_link(herkunft_koordinaten, (besuch.poi.x, besuch.poi.y), besuch.anfahrt_modus)
            pause_hinweis = f", davon {besuch.wartezeit} min Pause/Wartezeit" if besuch.wartezeit > 0 else ""
            teile.append(
                "<li>"
                f"<span style=\"color:#666\">→ {fahrzeit} min{verkehrsmittel_zusatz} von {esc(herkunft)}"
                f"{routen_link_html(etappen_link)}</span><br>"
                f"{esc(_zeitpunkt_text(plan, tag_nr, besuch.ankunft, 'nach'))}: "
                f"{link_html(besuch.poi.name, besuch.poi.place_id)} "
                f"({esc(_zeitpunkt_text(plan, tag_nr, besuch.abfahrt, 'bis'))}{esc(pause_hinweis)}, Score {besuch.poi.score:.1f})"
                "</li>"
            )
        teile.append("</ul>")
        if tag_nr != letzter_tag:
            teile.append(
                "<p>Rückweg zur Unterkunft, Zeit zum Umziehen – der Abend steht für ein Abendessen "
                "in der Nähe zur freien Verfügung.</p>"
            )

    if plan.weitere_aktivitaeten_empfehlungen:
        teile.append(
            "<p><strong>Weitere Empfehlungen in der Nähe</strong> "
            "(nicht im Vorschlag oben, zum selbst Ergänzen/Tauschen):</p><ul>"
        )
        for poi in plan.weitere_aktivitaeten_empfehlungen:
            zusatz = f" ({esc(poi.kategorie)}, ca. {poi.required_time} Minuten)"
            teile.append(f"<li>{link_html(poi.name, poi.place_id)}{zusatz}</li>")
        teile.append("</ul>")

    rueckreise_link = routen_link(
        _hinreise_ziel_fuer_link(plan), plan.wohnort, _TRAVELMODE_JE_VERKEHRSMITTEL.get(plan.rueckreise.alternative.verkehrsmittel)
    )
    teile.append(
        "<p><strong>Rückreise:</strong> "
        f"{esc(plan.rueckreise.alternative.verkehrsmittel)} "
        f"({plan.rueckreise.alternative.dauer_minuten} min, "
        f"{plan.rueckreise.alternative.kosten_euro:.2f} €, "
        f"{plan.rueckreise.co2_kg:.1f} kg CO2){routen_link_html(rueckreise_link)}</p>"
    )
    teile.append(teilstrecken_html(plan.rueckreise.alternative))

    for richtung, robustheit in [("Hinreise", plan.hinreise_robustheit), ("Rückreise", plan.rueckreise_robustheit)]:
        text = _robustheit_text(richtung, robustheit)
        if text:
            teile.append(f"<p>{esc(text)}</p>")

    return "\n".join(teile)


def als_kartendaten(plan: Reiseplan, foto_url_fuer_place_id: Callable[[str | None], str | None]) -> dict[str, Any]:
    """
    Strukturierte Kartendaten (Unterkunft + eingeplante POIs je Tag) für die Web-UI (webapp.py) –
    Foto, kurze Beschreibung, ungefährer Preis, Google-Maps-Link, analog zur kleinen Vorschau, die
    Google Maps beim Anklicken eines Ortes zeigt (siehe Nutzerwunsch). Als Beschreibung dient
    `POI.kategorie` (bereits vorhandene Daten) statt einer zusätzlichen, kostenpflichtigen
    Place-Details-Anfrage für einen redaktionellen Text – kein neuer API-Aufruf nur für diese
    Kartenansicht (Grundprinzip 1: keine erfundenen/zusätzlich erkauften Fakten ohne Not).

    `foto_url_fuer_place_id` bildet eine `place_id` auf eine bereits heruntergeladene, ausgelieferte
    Bild-URL ab (siehe src/ausgabe/fotos.py `lade_fotos_fuer_plan` + webapp.py) – None, wenn kein
    Foto vorliegt. Diese Funktion selbst kennt keine URLs/Dateipfade, nur die Struktur der Daten.
    """

    def poi_karte(poi: POI, ankunft_text: str, abfahrt_text: str, verkehrsmittel: str, routen_link_wert: str | None) -> dict[str, Any]:
        return {
            "name": poi.name,
            "kategorie": poi.kategorie,
            "foto_url": foto_url_fuer_place_id(poi.place_id),
            "maps_link": maps_link(poi.place_id),
            "routen_link": routen_link_wert,
            "score": poi.score,
            "ankunft": ankunft_text,
            "abfahrt": abfahrt_text,
            "verkehrsmittel": verkehrsmittel,
        }

    tage = []
    for tag_nr, tagesroute in enumerate(plan.tagesrouten, start=1):
        besuche = []
        for index, besuch in enumerate(tagesroute.besuche):
            herkunft_koordinaten = (
                plan.unterkunft_koordinaten if index == 0
                else (tagesroute.besuche[index - 1].poi.x, tagesroute.besuche[index - 1].poi.y)
            )
            besuche.append(poi_karte(
                besuch.poi,
                _zeitpunkt_text(plan, tag_nr, besuch.ankunft, "ab").strip(),
                _zeitpunkt_text(plan, tag_nr, besuch.abfahrt, "bis").strip(),
                _verkehrsmittel_label(besuch.anfahrt_modus),
                routen_link(herkunft_koordinaten, (besuch.poi.x, besuch.poi.y), besuch.anfahrt_modus),
            ))
        tage.append({"tag": tag_nr, "ankunftstag": tag_nr == 1, "besuche": besuche})

    unterkunft = None
    if plan.unterkunft_name:
        unterkunft = {
            "name": plan.unterkunft_name,
            "foto_url": foto_url_fuer_place_id(plan.unterkunft_place_id),
            "maps_link": maps_link(plan.unterkunft_place_id),
        }

    return {
        "unterkunft": unterkunft,
        "tage": tage,
        "sicherheitshinweis": plan.sicherheitshinweis,
        "weitere_empfehlungen": [
            {
                "name": poi.name,
                "kategorie": poi.kategorie,
                "foto_url": foto_url_fuer_place_id(poi.place_id),
                "maps_link": maps_link(poi.place_id),
            }
            for poi in plan.weitere_aktivitaeten_empfehlungen
        ],
    }


def speichere_datei(plan: Reiseplan, pfad: Path) -> None:
    """Schreibt den Reiseplan als lesbare Textdatei (Ersatz für Mailversand, siehe CLAUDE.md)."""
    pfad.write_text(als_text(plan), encoding="utf-8")


def speichere_json(plan: Reiseplan, pfad: Path) -> None:
    """Schreibt den Reiseplan zusätzlich als JSON, z.B. für eine spätere Weiterverarbeitung/Visualisierung."""
    pfad.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def speichere_poi_uebersicht(plan: Reiseplan, pfad: Path) -> None:
    """
    Schreibt EINE CSV-Zeile pro POI-Kandidat, den Optimierung 1 gesehen hat – nicht nur die
    tatsächlich eingeplanten (siehe Projektkonversation: "ich brauch ein Dokument, wo mir alle
    POIs aufgezeigt werden, sodass ich sagen kann, dass dieser Optimierungsalgorithmus
    funktioniert"). Erlaubt einen direkten Soll/Ist-Abgleich: welche POIs standen mit welchem
    Score/Zeitfenster zur Auswahl, welche davon hat Optimierung 1 tatsächlich in die Tagesroute
    übernommen und welche nicht (siehe `Reiseplan.weitere_aktivitaeten_empfehlungen`) – ohne
    dafür extra die `TOPTWInstanz` durchreichen zu müssen, die Daten stecken schon vollständig in
    `Reiseplan`.

    Semikolon statt Komma als Trennzeichen + UTF-8-BOM (`utf-8-sig`): deutsches Excel interpretiert
    eine reine Komma-CSV sonst falsch (Komma ist dort das Dezimaltrennzeichen), das BOM sorgt
    dafür, dass Umlaute nicht als Mojibake erscheinen.
    """
    zeilen = [
        ["tag", "status", "name", "kategorie", "score", "besuchsdauer_minuten",
         "zeitfenster_oeffnung", "zeitfenster_schliessung", "ankunft", "abfahrt", "quelle", "maps_link"]
    ]
    for tag_nr, tagesroute in enumerate(plan.tagesrouten, start=1):
        for besuch in tagesroute.besuche:
            poi = besuch.poi
            zeilen.append([
                str(tag_nr), "eingeplant", poi.name, poi.kategorie, f"{poi.score:.2f}",
                str(poi.required_time), str(poi.opening), str(poi.closing),
                str(besuch.ankunft), str(besuch.abfahrt), poi.quelle, maps_link(poi.place_id) or "",
            ])
    for poi in plan.weitere_aktivitaeten_empfehlungen:
        zeilen.append([
            "-", "nicht eingeplant (Kandidat)", poi.name, poi.kategorie, f"{poi.score:.2f}",
            str(poi.required_time), str(poi.opening), str(poi.closing), "-", "-",
            poi.quelle, maps_link(poi.place_id) or "",
        ])
    with pfad.open("w", encoding="utf-8-sig", newline="") as datei:
        schreiber = csv.writer(datei, delimiter=";")
        schreiber.writerows(zeilen)


def sende_mail(plan: Reiseplan, empfaenger: str) -> None:
    """
    Verschickt den Reiseplan als HTML-Mail (klickbare Google-Maps-Links zu
    Unterkunft/POIs, siehe als_html()) über die Mailjet Send API v3.1
    (https://dev.mailjet.com/email/guides/send-api-v31/). Braucht
    MAILJET_API_KEY, MAILJET_SECRET_KEY und MAILJET_ABSENDER in der .env
    (siehe .env.example) sowie eine bei Mailjet verifizierte Absenderadresse.

    Wirft RuntimeError, wenn die Konfiguration fehlt oder Mailjet einen
    Fehler zurückgibt (bewusst KEIN stiller Fehlschlag, siehe Projekt-
    konversation: "die Mail ist nie gekommen" sollte künftig sichtbar
    scheitern statt zu verschwinden).
    """
    if not EINSTELLUNGEN.mailjet_api_key or not EINSTELLUNGEN.mailjet_secret_key:
        raise RuntimeError(
            "MAILJET_API_KEY/MAILJET_SECRET_KEY fehlen in der .env. "
            "Nutze stattdessen speichere_datei() oder als_text(), oder trage die Keys ein."
        )
    if not EINSTELLUNGEN.mailjet_absender:
        raise RuntimeError(
            "MAILJET_ABSENDER fehlt in der .env (bei Mailjet verifizierte Absenderadresse nötig)."
        )

    nutzlast = {
        "Messages": [
            {
                "From": {"Email": EINSTELLUNGEN.mailjet_absender, "Name": "Reisebot"},
                "To": [{"Email": empfaenger}],
                "Subject": "Dein Reiseplan",
                "TextPart": als_text(plan),
                "HTMLPart": als_html(plan),
            }
        ]
    }
    antwort = requests.post(
        "https://api.mailjet.com/v3.1/send",
        auth=(EINSTELLUNGEN.mailjet_api_key, EINSTELLUNGEN.mailjet_secret_key),
        json=nutzlast,
        timeout=10,
    )
    if antwort.status_code >= 400:
        raise RuntimeError(f"Mailjet-Fehler ({antwort.status_code}): {antwort.text}")

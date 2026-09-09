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
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from src.api.typen import POI, ReiseAlternative, Unterkunft
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


def _maps_link(place_id: str | None) -> str | None:
    return _MAPS_LINK_VORLAGE.format(place_id=place_id) if place_id else None


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
    link = _maps_link(poi.place_id)
    if link:
        satz += f" — {link}"
    return satz + " (bitte Verfügbarkeit/Konditionen vor Ort bestätigen)."


def _maps_link_fuer_unterkunft(unterkunft: Unterkunft) -> str | None:
    """
    Wie `_maps_link`, aber mit Koordinaten-Fallback: Unterkünfte aus der
    Hotelbeds-Hotelsuche (All-Inclusive, siehe src/api/hotelbeds.py) haben keine
    Google-`place_id` (andere Datenquelle), aber echte Koordinaten – nutzt
    dasselbe offizielle Google-Maps-URL-Schema (query=lat,lng statt
    query_place_id), siehe https://developers.google.com/maps/documentation/
    urls/get-started#search-action, statt gar keinen Link anzubieten.
    """
    link = _maps_link(unterkunft.place_id)
    if link:
        return link
    return f"https://www.google.com/maps/search/?api=1&query={unterkunft.x},{unterkunft.y}"


@dataclass
class Reiseplan:
    hinreise: BewerteteAlternative
    tagesrouten: list[Tagesroute]
    rueckreise: BewerteteAlternative
    robustheit: RobustheitsErgebnis | None
    # Name der von Optimierung 1 unter mehreren echten Kandidaten gewählten
    # Unterkunft (siehe pipeline.py::_plane_bestes_depot). None, wenn keine
    # Unterkunfts-Kandidaten verfügbar waren (Fallback auf Zielregion-Punkt).
    unterkunft_name: str | None = None
    # place_id derselben Unterkunft, für einen klickbaren Google-Maps-Link
    # in der Mail-/Textausgabe (siehe _maps_link unten). None im Mock-Modus
    # oder ohne Unterkunfts-Kandidaten, siehe unterkunft_name.
    unterkunft_place_id: str | None = None
    # ALLE echten Unterkunfts-Kandidaten, die Optimierung 1 verglichen hat
    # (siehe pipeline.py::_plane_bestes_depot) bzw. alle gefundenen All-
    # Inclusive-Hotels (siehe pipeline.py::plane_reise) – NICHT nur der
    # gewählte (`unterkunft_name`), siehe Projektkonversation: "alle
    # Empfehlungen sollen in die Mail". Leer, wenn keine Kandidaten gefunden
    # wurden (z.B. Mock ohne mehrere Beispiele).
    alle_unterkunft_kandidaten: list[Unterkunft] = field(default_factory=list)
    # Nur gesetzt, wenn der Nutzer Sicherheit/Stabilität des Ziels laut F11
    # (sicherheitsbeduerfnis) als wichtig markiert hat (siehe schema.py
    # `sicherheit_ist_wichtig`) – Verweis auf eine ECHTE, offizielle Quelle
    # statt einer selbst erfundenen Sicherheitseinschätzung (Grundprinzip 1).
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
    # Startuhrzeit (Minuten seit Mitternacht) NUR gesetzt, wenn der Nutzer F20
    # (tagesstart_praeferenz) tatsächlich beantwortet hat (siehe pipeline.py) – sonst würde die
    # reine Standardannahme (09:00, siehe aufbereitung.py `parameter_fuer_tagesablauf`) als
    # scheinbar reale Uhrzeit ausgegeben (Grundprinzip 1). Ermöglicht echte Uhrzeiten AB TAG 2 in
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
        zeile = f"Unterkunft: {plan.unterkunft_name} (unsere Empfehlung unter mehreren geprüften Kandidaten)"
        link = _maps_link(plan.unterkunft_place_id)
        if link:
            zeile += f" — {link}"
        zeilen.append(zeile)
        zeilen.append("")
    if plan.alle_unterkunft_kandidaten:
        zeilen.append("Weitere gefundene Unterkunfts-Empfehlungen:")
        for kandidat in plan.alle_unterkunft_kandidaten:
            zeile = f"  - {kandidat.name}"
            if kandidat.board_type:
                zeile += f" ({kandidat.board_type})"
            link = _maps_link_fuer_unterkunft(kandidat)
            if link:
                zeile += f" — {link}"
            zeilen.append(zeile)
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
                zeilen.append(f"    → {fahrzeit} Min. von {herkunft}")
                pause_hinweis = f", davon {besuch.wartezeit} Min. Pause/Wartezeit" if besuch.wartezeit > 0 else ""
                zeile = (
                    f"    {_zeitpunkt_text(plan, tag_nr, besuch.ankunft, 'nach')}: {besuch.poi.name} "
                    f"({_zeitpunkt_text(plan, tag_nr, besuch.abfahrt, 'bis')}{pause_hinweis}, Score {besuch.poi.score:.1f})"
                )
                link = _maps_link(besuch.poi.place_id)
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
            link = _maps_link(poi.place_id)
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

    if plan.robustheit is not None:
        zeilen.append("")
        status = "robust" if plan.robustheit.ist_robust else "NICHT robust – Sicherheitspuffer nötig"
        zeilen.append(
            f"Monte-Carlo-Härtetest: {plan.robustheit.quote_ohne_verletzung:.1%} der "
            f"{plan.robustheit.laeufe} Läufe ohne Zeitfensterbruch ({status})."
        )

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
        link = _maps_link(place_id)
        return f'<a href="{esc(link)}">{esc(name)}</a>' if link else esc(name)

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
            f"{link_html(plan.unterkunft_name, plan.unterkunft_place_id)} "
            "(unsere Empfehlung unter mehreren geprüften Kandidaten)</p>"
        )

    if plan.alle_unterkunft_kandidaten:
        teile.append("<p><strong>Weitere gefundene Unterkunfts-Empfehlungen:</strong></p><ul>")
        for kandidat in plan.alle_unterkunft_kandidaten:
            zusatz = f" ({esc(kandidat.board_type)})" if kandidat.board_type else ""
            link = _maps_link_fuer_unterkunft(kandidat)
            eintrag = f'<a href="{esc(link)}">{esc(kandidat.name)}</a>' if link else esc(kandidat.name)
            teile.append(f"<li>{eintrag}{zusatz}</li>")
        teile.append("</ul>")

    if plan.sicherheitshinweis:
        teile.append(f"<p>{esc(plan.sicherheitshinweis)}</p>")

    teile.append(
        "<p><strong>Hinreise:</strong> "
        f"{esc(plan.hinreise.alternative.verkehrsmittel)} "
        f"({plan.hinreise.alternative.dauer_minuten} min, "
        f"{plan.hinreise.alternative.kosten_euro:.2f} €, "
        f"{plan.hinreise.co2_kg:.1f} kg CO2)</p>"
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
            pause_hinweis = f", davon {besuch.wartezeit} min Pause/Wartezeit" if besuch.wartezeit > 0 else ""
            teile.append(
                "<li>"
                f"<span style=\"color:#666\">→ {fahrzeit} min von {esc(herkunft)}</span><br>"
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

    teile.append(
        "<p><strong>Rückreise:</strong> "
        f"{esc(plan.rueckreise.alternative.verkehrsmittel)} "
        f"({plan.rueckreise.alternative.dauer_minuten} min, "
        f"{plan.rueckreise.alternative.kosten_euro:.2f} €, "
        f"{plan.rueckreise.co2_kg:.1f} kg CO2)</p>"
    )
    teile.append(teilstrecken_html(plan.rueckreise.alternative))

    if plan.robustheit is not None:
        status = "robust" if plan.robustheit.ist_robust else "NICHT robust – Sicherheitspuffer nötig"
        teile.append(
            "<p><strong>Monte-Carlo-Härtetest:</strong> "
            f"{plan.robustheit.quote_ohne_verletzung:.1%} der {plan.robustheit.laeufe} "
            f"Läufe ohne Zeitfensterbruch ({status}).</p>"
        )

    return "\n".join(teile)


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
                str(besuch.ankunft), str(besuch.abfahrt), poi.quelle, _maps_link(poi.place_id) or "",
            ])
    for poi in plan.weitere_aktivitaeten_empfehlungen:
        zeilen.append([
            "-", "nicht eingeplant (Kandidat)", poi.name, poi.kategorie, f"{poi.score:.2f}",
            str(poi.required_time), str(poi.opening), str(poi.closing), "-", "-",
            poi.quelle, _maps_link(poi.place_id) or "",
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

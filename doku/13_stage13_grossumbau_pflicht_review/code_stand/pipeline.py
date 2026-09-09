"""
Gemeinsame Planungs-Pipeline nach Abschluss der Dialogschleife:
Datenaufbereitung -> Optimierung 1 -> Optimierung 2 -> Monte-Carlo-Härtetest
-> Reiseplan (siehe CLAUDE.md, Prozessmodell-Lane "Regelbasierte
Anwendung"). Wird sowohl vom echten interaktiven Chat (chat.py) als auch vom
schnellen, dialogfreien Planungstest (pruefe_planung.py) verwendet, damit
diese Logik nur an einer Stelle gepflegt werden muss.
"""
from __future__ import annotations

import math
from dataclasses import replace

from src.api.flightapi import FlugClient
from src.api.google_maps import MapsClient
from src.api.hotelbeds import HotelClient
from src.api.typen import POI, Unterkunft
from src.ausgabe.reiseplan import SICHERHEITSHINWEISE_URL, Reiseplan
from src.config import EINSTELLUNGEN
from src.datenaufbereitung.aufbereitung import (
    erkenne_leihwunsch,
    erstelle_toptw_instanz,
    gewichte_nach_naehe_zum_depot,
    max_pois_fuer_reise,
    parameter_fuer_lokalen_transport,
    parameter_fuer_tagesablauf,
    schaetze_reisedauer_tage,
    waehle_top_pois,
)
from src.datenaufbereitung.poi_sammlung import sammle_pois
from src.datenaufbereitung.vertraeglichkeit import filtere_pois_hart, filtere_unterkuenfte_barrierefrei
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.monte_carlo import haertetest
from src.optimierung.toptw import Tagesroute, TOPTWInstanz, plane_gesamte_reise
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative, bewerte_alternativen, nachhaltigkeits_nudge

# Begrenzt, wie viele echte Unterkunfts-Kandidaten Optimierung 1 komplett
# durchplant (siehe _plane_bestes_depot) UND wie viele im finalen Reiseplan/
# in der Mail als "weitere Empfehlungen" auftauchen (siehe Projekt-
# konversation: "wie viele Unterkünfte das dann immer sind, such die Top 5
# raus") – jeder Kandidat kostet einen vollen ILS-Lauf über alle Reisetage,
# daher eine Obergrenze statt alle gefundenen Unterkünfte zu prüfen. Dieselbe
# Obergrenze gilt auch für die Chat-Vorschau (siehe vorschlaege.py
# `_MAX_UNTERKUNFT_KANDIDATEN`), damit dort und in der Mail dieselbe Anzahl
# auftaucht.
_MAX_UNTERKUNFT_KANDIDATEN = 5

# F14-Fahrzeugname -> Suchbegriff für `sammle_pois` (als Freitext direkt an Google Places Text
# Search durchgereicht, siehe google_maps.py `suche_pois`; aufbereitung.py `erkenne_leihwunsch`).
_VERLEIH_KATEGORIE_JE_FAHRZEUG = {"Auto": "Autoverleih", "Fahrrad": "Fahrradverleih"}


def _nur_bestaetigte_verkehrsmittel(
    bewertete: list[BewerteteAlternative], verkehrsmittel_praeferenz: list[str]
) -> list[BewerteteAlternative]:
    """
    Schränkt die von Optimierung 2 (siehe verkehrsmittelwahl.py) bewerteten Alternativen auf die
    ein, die der Nutzer im Dialog (F13, verkehrsmittel_praeferenz) tatsächlich bestätigt hat.

    BEHOBENER BUG (siehe Projektkonversation: "ich habe im Chat Auto bestätigt, aber am Ende steht
    in der Reise Bahn – das darf nie passieren"): `bewerte_alternativen` gewichtet ALLE echten
    Alternativen (Bahn/Auto/Fernbus) nach Zeit/Kosten/CO2 und wählt objektiv die beste – das ist
    die richtige Aufgabe für Optimierung 2 SOLANGE der Nutzer noch keine konkrete Wahl getroffen
    hat, überstimmt aber fälschlich eine bereits im Dialog bestätigte, konkrete Entscheidung (CO2-
    Gewichtung/Bahn-Nudging aus Grundprinzip 5 begünstigt strukturell die Bahn). Optimierung 2
    bewertet danach weiterhin gewichtet, aber NUR NOCH innerhalb der vom Nutzer bestätigten Auswahl.

    Ohne erkennbare Übereinstimmung (z.B. wenn `verkehrsmittel_praeferenz` unklarer Freitext ist,
    der keinen der echten Alternativen-Namen enthält) bleibt die volle Liste als Fallback erhalten,
    statt mit einer leeren Auswahl abzustürzen oder eine Wahl zu erfinden.
    """
    praeferenz_text = " ".join(verkehrsmittel_praeferenz).lower()
    passende = [b for b in bewertete if b.alternative.verkehrsmittel.lower() in praeferenz_text]
    return passende or bewertete


def _suche_lokalen_verleih(fahrzeug: str, ziel: str, client: MapsClient, radius_meter: int) -> POI | None:
    """
    Sucht real nach einem Verleih für `fahrzeug` ("Auto"/"Fahrrad") in der
    Nähe von `ziel` (siehe Projektkonversation: Anreise mit Bahn, vor Ort
    aber Fahrrad gewünscht -> im Dialog nachgefragt, ob ein eigenes Fahrrad
    dabei ist oder ein Verleih gesucht werden soll; bei Bestätigung hier
    real geprüft). Gibt den besten Treffer zurück, `None` ohne Treffer –
    NIE ein erfundener Verleih (Grundprinzip 1).
    """
    kategorie = _VERLEIH_KATEGORIE_JE_FAHRZEUG[fahrzeug]
    kandidaten = sammle_pois(ziel, [kategorie], [], client, radius_meter=radius_meter)
    treffer = waehle_top_pois(kandidaten, [kategorie], max_anzahl=1)
    return treffer[0] if treffer else None


def plane_reise(
    anfrage: ReiseAnfrage, client: MapsClient, flug_client: FlugClient | None = None,
    hotel_client: HotelClient | None = None,
) -> tuple[Reiseplan, str | None]:
    """
    Führt die deterministische Planung durch (Optimierung 1 + 2 +
    Monte-Carlo-Härtetest) und gibt den fertigen Reiseplan sowie ggf. den
    Nachhaltigkeits-Nudge-Text für die An-/Abreise zurück.

    WICHTIG (siehe Projektkonversation): `anfrage.zielregionen` ist die
    einzige im Fragekatalog erfasste Ortsangabe für das Reiseziel – Land-
    /Regionsebene (z.B. "Italien"), keine konkrete Stadt. Für Places-Anfragen
    (Optimierung 1) ist das eine Vereinfachung: `anfrage.primaeres_reiseziel()`
    (schema.py) liefert den ersten genannten Zielnamen, der dann direkt
    geokodiert/durchsucht wird, ohne weitere Eingrenzung auf eine Stadt.
    `anfrage.wohnort` (F08, siehe katalog.py) liefert den Startort für
    Optimierung 2 – im Mock-Modus ignoriert `MockGoogleMapsClient.
    reisealternativen` beide Ortsargumente ohnehin (liefert immer
    `mock_data.BEISPIEL_REISEALTERNATIVEN`), im Live-Modus wird der echte
    Wohnort verwendet.
    """
    ziel = anfrage.primaeres_reiseziel() or "Zielregion"

    if anfrage.wohnort is None:
        raise ValueError(
            "Kein Wohnort in der Reiseanfrage gesetzt (Feld 'wohnort', Fragekatalog F08). "
            "Optimierung 2 (An-/Abreise) kann ohne Startort keine Verbindung berechnen."
        )

    # Hinreise WIRD VOR Optimierung 1 berechnet (nicht erst danach): Tag 1 der
    # Tagesroute muss die Ankunftszeit der Hinreise vom Tagesbudget abziehen,
    # sonst plant Optimierung 1 so, als stünde ab Reisebeginn das volle
    # Tagesbudget zur Verfügung, obwohl ein Großteil davon schon durch die
    # Anreise verbraucht ist (siehe Projektkonversation).
    alternativen = client.reisealternativen(anfrage.wohnort, ziel)
    if not alternativen and not (anfrage.all_inclusive_gewuenscht and flug_client is not None):
        # BEHOBENER BUG (siehe Projektkonversation: live abgestürzt mit einem kryptischen
        # IndexError auf `bewertete[0]`, als eine zu vage Zielangabe wie "Mittelmeerraum" für
        # KEINE einzige Verkehrsmittel-Alternative eine Route lieferte): klare, verständliche
        # Fehlermeldung statt eines rohen Python-Tracebacks – Grundprinzip 1, kein Verschweigen,
        # aber auch keine erfundene Route.
        raise ValueError(
            f"Für die Strecke '{anfrage.wohnort}' -> '{ziel}' konnte keine einzige Verkehrsmittel-"
            "Alternative (Bahn/Auto/Fernbus) berechnet werden. Vermutlich ist die Ortsangabe zu "
            "ungenau (z.B. eine ganze Region statt eines konkreten Ortes) – bitte einen konkreteren "
            "Wohnort/Zielort verwenden."
        )
    if anfrage.all_inclusive_gewuenscht and flug_client is not None:
        # All-Inclusive ist strukturell aufs Fliegen ausgelegt (siehe vorschlaege.py, Grundprinzip 5 bleibt
        # Querschnittsprinzip über den CO2-Wert in `bewerte_alternativen`, aber keine Blockade) – der im
        # Dialog gezeigte Flug muss auch in der TATSÄCHLICHEN An-/Abreise landen, nicht nur im Chat-Vorschlag.
        distanz_km = math.dist(client.geocode(anfrage.wohnort), client.geocode(ziel)) * 111
        alternativen = alternativen + flug_client.suche_fluege(anfrage.wohnort, ziel, distanz_km)
    bewertete_alle = bewerte_alternativen(alternativen)
    # Nudge bezieht sich bewusst auf ALLE echten Alternativen (auch die, die der Nutzer nicht
    # gewählt hat) – er ist eine Zusatzinformation im Dialog, keine Vorgabe für die tatsächliche
    # Wahl unten (siehe _nur_bestaetigte_verkehrsmittel).
    nudge = nachhaltigkeits_nudge(bewertete_alle)
    bewertete = _nur_bestaetigte_verkehrsmittel(bewertete_alle, anfrage.verkehrsmittel_praeferenz)

    tage = schaetze_reisedauer_tage(anfrage.reisezeitraum_rohtext)
    tag1_budget = max(0, EINSTELLUNGEN.standard_tagesbudget_minuten - bewertete[0].alternative.dauer_minuten)
    tagesbudget_je_tag = [tag1_budget] + [EINSTELLUNGEN.standard_tagesbudget_minuten] * (tage - 1)

    # Lokales Fortbewegungsmittel (F14) bestimmt den Places-Suchradius (siehe
    # google_maps.py) – die Geschwindigkeit für die POI-zu-POI-Distanzmatrix
    # setzt erstelle_toptw_instanz selbst (dieselbe Quelle, siehe aufbereitung.py).
    _, radius_meter = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)

    lokales_leihfahrzeug_gewuenscht = erkenne_leihwunsch(anfrage.lokaler_transport_praeferenz)
    lokaler_verleih_poi = (
        _suche_lokalen_verleih(lokales_leihfahrzeug_gewuenscht, ziel, client, radius_meter)
        if lokales_leihfahrzeug_gewuenscht is not None
        else None
    )

    # Cap greift HIER wirklich, nicht nur als Chat-Vorschau (siehe
    # vorschlaege.py): mehr als max_pois_fuer_reise() bekommt Optimierung 1
    # gar nicht erst als Kandidaten zu sehen (siehe Projektkonversation:
    # "wir können nicht optimieren" muss auch tatsächlich stimmen). Kappung
    # passiert NACH dem Scoring (waehle_top_pois), damit Präferenzen/
    # Gewichtung tatsächlich bestimmen, WELCHE POIs als Kandidaten übrig
    # bleiben, statt nur beliebige erste Fundstellen zu behalten.
    #
    # `aktivitaeten_noch_per_poi_zu_planen` (statt `aktivitaeten_interessen`),
    # falls gesetzt: bei All-Inclusive wurden bereits paketinklusive
    # Aktivitäten herausgefiltert (siehe vorschlaege.py `trenne_bereits_im_
    # paket_enthalten`) – sonst würden z.B. Pool/Spa doppelt eingeplant.
    aktivitaeten_fuer_poi_suche = (
        anfrage.aktivitaeten_noch_per_poi_zu_planen
        if anfrage.aktivitaeten_noch_per_poi_zu_planen is not None
        else anfrage.aktivitaeten_interessen
    )
    alle_pois = sammle_pois(
        ziel, aktivitaeten_fuer_poi_suche, anfrage.aktivitaeten_mit_spezialrecherche, client, radius_meter=radius_meter,
        ernaehrung_einschraenkungen=anfrage.ernaehrung_einschraenkungen,
    )
    # Harte Einschränkungen (Ernährung F18, Barrierefreiheit F09/F10/F15) VOR
    # dem Präferenz-Scoring aussortieren (siehe vertraeglichkeit.py) – ein
    # Fisch-Restaurant bei genannter Fischallergie soll erst gar nicht als
    # Kandidat in Optimierung 1 landen, nicht nur zufällig durch Scoring
    # verdrängt werden (siehe Projektkonversation).
    alle_pois, einschraenkungshinweise = filtere_pois_hart(alle_pois, anfrage, client)
    # BEHOBENE LÜCKE (siehe Projektkonversation: "es braucht auch die Abstände zwischen den POIs
    # untereinander, ich will ja nicht nach jedem POI zurück ins Hotel"): Die Nähe-Gewichtung in
    # erstelle_toptw_instanz (siehe dort, `gewichte_nach_naehe_zum_depot`) griff bisher erst NACH
    # dieser Kappung – zu diesem Zeitpunkt hätte ein rein interessenbasiertes Ranking bereits
    # geografisch verstreute Kandidaten endgültig ausgewählt haben können, ohne dass die spätere
    # Distanz-Gewichtung daran noch etwas ändern konnte (sie kann nur noch die Reihenfolge INNERHALB
    # der bereits gekappten Auswahl beeinflussen). Fix: bei eingeschränkter Gehfähigkeit wird VOR der
    # Kappung schon anhand des groben Zielorts (echter Unterkunfts-Standort folgt erst später, siehe
    # _plane_bestes_depot) gewichtet, damit die Auswahl selbst schon geografisch kompakter ausfällt.
    if anfrage.eingeschraenkte_gehfaehigkeit():
        alle_pois = gewichte_nach_naehe_zum_depot(alle_pois, client.geocode(ziel))
    pois = waehle_top_pois(
        alle_pois, aktivitaeten_fuer_poi_suche, max_pois_fuer_reise(anfrage), anfrage.aktivitaeten_gewichtung
    )

    if anfrage.all_inclusive_gewuenscht and anfrage.all_inclusive_hotel_koordinaten:
        # Bereits im Dialog (F15) bestätigtes All-Inclusive-Hotel bleibt AUCH das Depot für Optimierung 1 –
        # keine zweite, unabhängige Google-Places-Unterkunftssuche (siehe _plane_bestes_depot), die zu einem
        # ANDEREN Hotel als dem im Chat gezeigten führen könnte.
        instanz = erstelle_toptw_instanz(
            anfrage, pois,
            standard_tagesbudget_minuten=EINSTELLUNGEN.standard_tagesbudget_minuten,
            max_aktivitaetszeit_minuten=EINSTELLUNGEN.max_aktivitaetszeit_minuten,
            depot_koordinaten=anfrage.all_inclusive_hotel_koordinaten,
            depot_name=anfrage.all_inclusive_hotel_name or "All-Inclusive-Hotel",
            client=client,
        )
        tagesrouten = plane_gesamte_reise(instanz, tagesbudget_je_tag=tagesbudget_je_tag)
        unterkunft_name, unterkunft_place_id = anfrage.all_inclusive_hotel_name, None
        # Alle im Dialog gefundenen All-Inclusive-Hotels (nicht nur das gewählte), siehe
        # Projektkonversation "alle Empfehlungen sollen in die Mail" – gleiche Suche wie in
        # chat.py bei der F15-Bestätigung, damit dieselben Kandidaten wie im Chat auftauchen.
        # Günstigster zuerst (echter Preis, siehe hotelbeds.py) als Budget-Signal, dann auf
        # _MAX_UNTERKUNFT_KANDIDATEN gekappt (siehe Projektkonversation: "Top 5 nach Budget/
        # Vorstellungen/Lage").
        alle_kandidaten = (
            sorted(
                hotel_client.suche_all_inclusive_hotels(client.geocode(ziel)),
                key=lambda h: h.preis_pro_nacht if h.preis_pro_nacht is not None else float("inf"),
            )[:_MAX_UNTERKUNFT_KANDIDATEN]
            if hotel_client
            else []
        )
        alle_kandidaten, unterkunft_hinweise = filtere_unterkuenfte_barrierefrei(alle_kandidaten, anfrage, client)
        einschraenkungshinweise = einschraenkungshinweise + unterkunft_hinweise
    else:
        instanz, tagesrouten, unterkunft_name, unterkunft_place_id, alle_kandidaten, unterkunft_hinweise = (
            _plane_bestes_depot(anfrage, pois, ziel, client, tagesbudget_je_tag)
        )
        einschraenkungshinweise = einschraenkungshinweise + unterkunft_hinweise

    # Härtetest nur, wenn am ersten Tag überhaupt etwas eingeplant wurde
    # (leere Route hat keine Zeitfenster, die brechen könnten). Nutzt das
    # tatsächliche Tag-1-Budget (verkürzt um die Hinreise, siehe oben), sonst
    # würde der Härtetest gegen ein zu großzügiges Budget prüfen.
    tag1_instanz = replace(instanz, tagesbudget_minuten=tagesbudget_je_tag[0])
    robustheit = haertetest(tag1_instanz, tagesrouten[0]) if tagesrouten and tagesrouten[0].besuche else None

    # NICHT eingeplante Kandidaten (siehe Projektkonversation: "ich möchte
    # nicht, dass am Ende eine vollkommen fertig geplante Reise entsteht –
    # eine grobe Struktur, der Nutzer trifft dann Entscheidungen"): Optimierung
    # 1 bleibt unverändert (liefert weiterhin EINE realisierbare, optimierte
    # Tagesroute als konkreten Vorschlag), aber alle Kandidaten aus `pois`, die
    # NICHT in dieser Route gelandet sind (Zeitfenster/Budget hat nicht
    # gereicht, nicht "haben nicht gepasst"), werden zusätzlich als frei
    # kombinierbare Empfehlungen mitgegeben statt verworfen zu werden.
    eingeplante_ids = {besuch.poi.id for route in tagesrouten for besuch in route.besuche}
    weitere_empfehlungen = [poi for poi in pois if poi.id not in eingeplante_ids]

    plan = Reiseplan(
        hinreise=bewertete[0],
        tagesrouten=tagesrouten,
        rueckreise=bewertete[0],
        robustheit=robustheit,
        unterkunft_name=unterkunft_name,
        unterkunft_place_id=unterkunft_place_id,
        alle_unterkunft_kandidaten=alle_kandidaten,
        weitere_aktivitaeten_empfehlungen=weitere_empfehlungen,
        einschraenkungshinweise=einschraenkungshinweise,
        lokales_leihfahrzeug_gewuenscht=lokales_leihfahrzeug_gewuenscht,
        lokaler_verleih_poi=lokaler_verleih_poi,
        # NUR gesetzt, wenn der Nutzer F20 tatsächlich beantwortet hat (siehe reiseplan.py) – sonst
        # würde die reine Standardannahme (09:00, siehe aufbereitung.py) als scheinbar reale
        # Uhrzeit ausgegeben (Grundprinzip 1: keine erfundene Uhrzeit).
        tagesstart_minuten=(
            parameter_fuer_tagesablauf(anfrage.tagesstart_praeferenz)[0]
            if anfrage.tagesstart_praeferenz
            else None
        ),
        # Echte, offizielle Quelle statt einer selbst erfundenen Sicherheitsbewertung (Grundprinzip 1),
        # siehe reiseplan.py `SICHERHEITSHINWEISE_URL`/schema.py `sicherheit_ist_wichtig`.
        sicherheitshinweis=(
            f"Sicherheit war Ihnen wichtig – aktuelle Reise- und Sicherheitshinweise des Auswärtigen "
            f"Amts für Ihr Reiseziel finden Sie hier: {SICHERHEITSHINWEISE_URL} (bitte vor Abreise prüfen)."
            if anfrage.sicherheit_ist_wichtig()
            else None
        ),
    )
    return plan, nudge


def _plane_bestes_depot(
    anfrage: ReiseAnfrage, pois: list[POI], ziel: str, client: MapsClient, tagesbudget_je_tag: list[int]
) -> tuple[TOPTWInstanz, list[Tagesroute], str | None, str | None, list[Unterkunft], list[str]]:
    """
    Erweitert Optimierung 1 um die Wahl der Unterkunft selbst: statt eines
    einzelnen, geokodierten Punkts (Zielregion-Zentrum) als festem Depot
    werden bis zu `_MAX_UNTERKUNFT_KANDIDATEN` echte Unterkünfte (dieselbe
    Places-Suche wie im Chat, Knoten c1) VOLLSTÄNDIG durchgeplant – gewählt
    wird die Unterkunft, deren resultierende Gesamtroute den höchsten
    Score erreicht (dieselbe Zielgröße, die ILS ohnehin pro Tag optimiert;
    siehe CLAUDE.md, Optimierung 1). Ohne Kandidaten (z.B. Places liefert für
    diese Region nichts) Fallback auf den bisherigen geokodierten
    Zielregion-Punkt, statt eine Unterkunft zu erfinden (Grundprinzip 1).

    Grund für diese Erweiterung: die im Chat abgefragten Unterkunfts-
    Kandidaten (unterkunft_anforderungen, Typ C) wurden vorher nach der
    Zustimmung des Nutzers verworfen und nie tatsächlich für die Planung
    verwendet – Optimierung 1 kannte nur die grobe Zielregion, nie eine
    echte Unterkunft (siehe Projektkonversation).

    Der 5. Rückgabewert (ALLE Kandidaten) geht unverändert in `Reiseplan.
    alle_unterkunft_kandidaten` (siehe Projektkonversation: "alle Empfehlungen
    sollen in die Mail") – NACH Passform sortiert, nicht in Places-Fundreihen-
    folge: primär nach der resultierenden Gesamtroute ("Lage" – ein günstig
    gelegenes Depot ermöglicht mehr/bessere POI-Besuche), bei Gleichstand nach
    `preisniveau` aufsteigend ("Budget"). "Vorstellungen" (Freitext aus F15)
    fließt schon VOR dieser Funktion ein: `client.suche_unterkuenfte` bekommt
    die Antwort als `praeferenz_text` und lässt Google selbst danach
    relevanzsortieren (siehe google_maps.py), statt hier einen eigenen,
    ungesicherten Text-Matching-Heuristik zu erfinden (Grundprinzip 1).

    Der 6. Rückgabewert enthält Hinweise zu Kandidaten, die laut genanntem
    Barrierefreiheitsbedarf (siehe vertraeglichkeit.py) NICHT ausgefiltert
    werden konnten, weil keine unbedenkliche Alternative übrig war.
    """
    kandidaten = client.suche_unterkuenfte(ziel, praeferenz_text=anfrage.unterkunft_anforderungen)
    kandidaten = kandidaten[:_MAX_UNTERKUNFT_KANDIDATEN]
    # Barrierefreiheitsbedarf (siehe vertraeglichkeit.py) VOR der Depot-Auswahl aussortieren – ein laut
    # Google-Maps-Daten nicht barrierefreies Hotel soll nicht als Depot gewählt werden, wenn eine
    # unbedenkliche Alternative vorliegt (siehe Projektkonversation).
    kandidaten, unterkunft_hinweise = filtere_unterkuenfte_barrierefrei(kandidaten, anfrage, client)
    if not kandidaten:
        instanz = erstelle_toptw_instanz(
            anfrage, pois,
            standard_tagesbudget_minuten=EINSTELLUNGEN.standard_tagesbudget_minuten,
            max_aktivitaetszeit_minuten=EINSTELLUNGEN.max_aktivitaetszeit_minuten,
            depot_koordinaten=client.geocode(ziel),
            client=client,
        )
        return (
            instanz, plane_gesamte_reise(instanz, tagesbudget_je_tag=tagesbudget_je_tag),
            None, None, [], unterkunft_hinweise,
        )

    ausgewertet: list[tuple[TOPTWInstanz, list[Tagesroute], float, Unterkunft]] = []
    for unterkunft in kandidaten:
        instanz = erstelle_toptw_instanz(
            anfrage, pois,
            standard_tagesbudget_minuten=EINSTELLUNGEN.standard_tagesbudget_minuten,
            max_aktivitaetszeit_minuten=EINSTELLUNGEN.max_aktivitaetszeit_minuten,
            depot_koordinaten=(unterkunft.x, unterkunft.y),
            depot_name=unterkunft.name,
            client=client,
        )
        tagesrouten = plane_gesamte_reise(instanz, tagesbudget_je_tag=tagesbudget_je_tag)
        gesamtscore = sum(route.score for route in tagesrouten)
        ausgewertet.append((instanz, tagesrouten, gesamtscore, unterkunft))

    ausgewertet.sort(key=lambda eintrag: (-eintrag[2], eintrag[3].preisniveau))
    instanz, tagesrouten, _, gewaehlt = ausgewertet[0]
    kandidaten_sortiert = [eintrag[3] for eintrag in ausgewertet]
    return instanz, tagesrouten, gewaehlt.name, gewaehlt.place_id, kandidaten_sortiert, unterkunft_hinweise

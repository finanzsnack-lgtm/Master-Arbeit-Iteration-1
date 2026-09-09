"""
Gemeinsame Planungs-Pipeline nach Abschluss der Dialogschleife: Datenaufbereitung -> Optimierung 1
-> Optimierung 2 -> Monte-Carlo-Härtetest -> Reiseplan. Wird sowohl vom echten interaktiven Chat
(chat.py) als auch vom schnellen, dialogfreien Planungstest (pruefe_planung.py) verwendet, damit
diese Logik nur an einer Stelle gepflegt werden muss.
"""
from __future__ import annotations

from dataclasses import replace

from src.api.google_maps import MapsClient
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
from src.optimierung.monte_carlo import haertetest
from src.optimierung.toptw import plane_gesamte_reise
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative, bewerte_alternativen, nachhaltigkeits_nudge


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
    debug_sammlung: PlanungsDebugSammlung | None = None,
) -> tuple[Reiseplan, str | None]:
    """
    Führt die deterministische Planung durch (Optimierung 1 + 2 + Monte-Carlo-Härtetest) und gibt
    den fertigen Reiseplan sowie ggf. den Nachhaltigkeits-Nudge-Text für die An-/Abreise zurück.

    `debug_sammlung` (siehe src/ausgabe/debug.py, NUR von pruefe_planung.py übergeben): wenn
    gesetzt, werden die Zwischenergebnisse (rohe POI-Treffer, gefilterte/ausgewählte Kandidaten,
    Optimierung-1-Eingabe/-Ergebnis, Härtetest-Eingabe/-Ergebnis) zusätzlich hineingeschrieben –
    ohne Angabe (Standardfall in chat.py/webapp.py) entsteht dadurch kein Mehraufwand.

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

    if anfrage.wohnort is None:
        raise ValueError(
            "Kein Wohnort in der Reiseanfrage gesetzt (Feld 'wohnort', Fragekatalog F08). "
            "Optimierung 2 (An-/Abreise) kann ohne Startort keine Verbindung berechnen."
        )

    # Hinreise WIRD VOR Optimierung 1 berechnet: Tag 1 der Tagesroute muss die Ankunftszeit der
    # Hinreise vom Tagesbudget abziehen, sonst plant Optimierung 1 so, als stünde ab Reisebeginn
    # das volle Tagesbudget zur Verfügung.
    alternativen = client.reisealternativen(anfrage.wohnort, ziel)
    if not alternativen:
        raise ValueError(
            f"Für die Strecke '{anfrage.wohnort}' -> '{ziel}' konnte keine einzige Verkehrsmittel-"
            "Alternative (Bahn/Auto/Fernbus) berechnet werden. Vermutlich ist die Ortsangabe zu "
            "ungenau (z.B. eine ganze Region statt eines konkreten Ortes) – bitte einen konkreteren "
            "Wohnort/Zielort verwenden."
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

    tage = schaetze_reisedauer_tage(anfrage.reisezeitraum_rohtext)
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
    tagesbudget_je_tag = [tag1_budget] + [basis_tagesbudget] * (tage - 1)

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
    if debug_sammlung is not None:
        debug_sammlung.rohe_pois = list(alle_pois)
    # Harte Einschränkungen (Ernährung F18, Barrierefreiheit F09/F10/F15) VOR dem Präferenz-Scoring
    # aussortieren (siehe vertraeglichkeit.py) – ein Fisch-Restaurant bei genannter Fischallergie
    # soll erst gar nicht als Kandidat in Optimierung 1 landen.
    alle_pois, einschraenkungshinweise = filtere_pois_hart(
        alle_pois, anfrage, client, barrierefreiheit_strikt=barrierefreiheit_strikt
    )
    if debug_sammlung is not None:
        debug_sammlung.pois_nach_harten_einschraenkungen = list(alle_pois)
    # Nähe-Gewichtung VOR der Kappung (nicht erst danach): zu diesem Zeitpunkt hätte ein rein
    # interessenbasiertes Ranking bereits geografisch verstreute Kandidaten endgültig ausgewählt
    # haben können, ohne dass eine spätere Distanz-Gewichtung daran noch etwas ändern könnte.
    depot_koordinaten = anfrage.unterkunft_koordinaten or client.geocode(ziel)
    if anfrage.barrierefreiheit_oder_eingeschraenkt():
        alle_pois = gewichte_nach_naehe_zum_depot(alle_pois, depot_koordinaten)
    pois = waehle_top_pois(
        alle_pois, anfrage.aktivitaeten_interessen, max_pois_fuer_reise(anfrage), anfrage.aktivitaeten_gewichtung
    )
    if debug_sammlung is not None:
        debug_sammlung.ausgewaehlte_pois = list(pois)

    instanz = erstelle_toptw_instanz(
        anfrage, pois,
        standard_tagesbudget_minuten=EINSTELLUNGEN.standard_tagesbudget_minuten,
        max_aktivitaetszeit_minuten=EINSTELLUNGEN.max_aktivitaetszeit_minuten,
        depot_koordinaten=depot_koordinaten,
        depot_name=anfrage.unterkunft_name or "Unterkunft",
        client=client,
    )
    tagesrouten = plane_gesamte_reise(instanz, tagesbudget_je_tag=tagesbudget_je_tag)

    # Verkehrsmittel je Etappe NACHTRÄGLICH ergänzen (siehe aufbereitung.py
    # `ergaenze_anfahrt_modus_je_etappe`, "Variante B") – reine Anzeige-Ergänzung, verändert die
    # bereits feststehenden Ankunfts-/Abfahrtszeiten nicht.
    modi = modi_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    ergaenze_anfahrt_modus_je_etappe(client, depot_koordinaten, tagesrouten, modi)

    if debug_sammlung is not None:
        debug_sammlung.toptw_instanz = instanz
        debug_sammlung.tagesrouten = tagesrouten

    # Härtetest nur, wenn am ersten Tag überhaupt etwas eingeplant wurde (leere Route hat keine
    # Zeitfenster, die brechen könnten). Nutzt das tatsächliche Tag-1-Budget (verkürzt um die
    # Hinreise), sonst würde der Härtetest gegen ein zu großzügiges Budget prüfen.
    tag1_instanz = replace(instanz, tagesbudget_minuten=tagesbudget_je_tag[0])
    robustheit = haertetest(tag1_instanz, tagesrouten[0]) if tagesrouten and tagesrouten[0].besuche else None
    if debug_sammlung is not None:
        debug_sammlung.haertetest_instanz = tag1_instanz
        debug_sammlung.haertetest_route = tagesrouten[0] if tagesrouten and tagesrouten[0].besuche else None
        debug_sammlung.robustheit = robustheit

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
        bewertete[0].alternative.kosten_euro, bewertete[0].alternative.kosten_euro,
        anfrage.unterkunft_preisniveau, naechte=max(tage - 1, 1),
        eingeplante_pois=eingeplante_pois, tage=tage,
    )

    plan = Reiseplan(
        hinreise=bewertete[0],
        tagesrouten=tagesrouten,
        rueckreise=bewertete[0],
        robustheit=robustheit,
        unterkunft_name=anfrage.unterkunft_name,
        unterkunft_place_id=anfrage.unterkunft_place_id,
        unterkunft_foto_referenz=anfrage.unterkunft_foto_referenz,
        geschaetzte_kosten_euro=geschaetzte_kosten_euro,
        kosten_unvollstaendig=kosten_unvollstaendig,
        budget_gesamt=anfrage.budget_gesamt,
        weitere_aktivitaeten_empfehlungen=weitere_empfehlungen,
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
    return plan, nudge

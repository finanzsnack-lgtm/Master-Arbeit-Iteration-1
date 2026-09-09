"""
Datenabruf für Typ-C-Fragen (Unterkunft/Aktivitäten/Verkehrsmittel): wird vom
LLM-Agenten über das Werkzeug `hole_api_daten` (siehe agent_tools.py)
aufgerufen, BEVOR ein Vorschlag formuliert wird.

Bewusste Trennung von agent_tools.py: der eigentliche API-/Mock-Aufruf ist
reiner, deterministischer Code ohne LLM-Beteiligung (CLAUDE.md, Grundprinzip
1 – "Alle Fakten kommen aus realen APIs"). Das LLM bekommt das Ergebnis
anschließend nur noch als fertigen Text zur Formulierung.
"""
from __future__ import annotations

import math

from requests.exceptions import RequestException

from src.api.flightapi import FlugClient
from src.api.google_maps import MapsClient
from src.api.hotelbeds import HotelClient, amenity_fuer_aktivitaet
from src.api.typen import POI
from src.datenaufbereitung.aufbereitung import max_pois_fuer_reise, parameter_fuer_lokalen_transport, waehle_top_pois
from src.datenaufbereitung.poi_sammlung import sammle_pois
from src.datenaufbereitung.vertraeglichkeit import filtere_pois_hart, filtere_unterkuenfte_barrierefrei
from src.fragekatalog.katalog import FrageDefinition
from src.fragekatalog.schema import ReiseAnfrage

# Verkehrsmittel, für die je Aktivität eine Anfahrtszeit ermittelt wird
# (siehe `_anfahrtsempfehlung_je_poi`) – Projektwunsch: pro Aktivität max. 2
# konkrete, mit echten Reisezeiten begründete Optionen statt einer erfundenen
# pauschalen Empfehlung (CLAUDE.md, Grundprinzip 1).
_ANFAHRT_MODI_LABEL = {"walking": "zu Fuß", "transit": "mit öffentlichen Verkehrsmitteln", "driving": "mit dem Auto"}
_ANFAHRT_MAX_OPTIONEN = 2
# Grenze, ab der "zu Fuß" trotz kurzer werdender Distanz als eher unbequem
# statt als "gut machbar" begründet wird (grobe, dokumentierte Annahme, keine
# echte Quelle nötig – dient nur der Textformulierung, nicht der Optimierung).
_ANFAHRT_ZU_FUSS_ANGENEHM_MINUTEN = 20

# Ab wie vielen ROH-Treffern (vor der Kappung) der Bot den Nutzer explizit
# informiert und fragt, statt einfach still zu kappen (siehe Projekt-
# konversation: "wenn es drüber ist soll [...] der Nutzer informiert und
# gefragt werden"). Der tatsächlich angebotene/verwendete Wert ist
# `max_pois_fuer_reise(anfrage)` (aufbereitung.py, Tage-Formel) – DERSELBE
# Wert, den pipeline.py auch wirklich an Optimierung 1 übergibt (siehe dort),
# damit "wir können nicht mehr optimieren" nicht nur eine Chat-Behauptung
# bleibt, sondern stimmt.
_WARNSCHWELLE_ROHTREFFER = 10

# Ab welcher schnellsten nachhaltigen Reisezeit (Bahn/Auto/Fernbus) ein Ziel
# als "nicht mehr menschlich sinnvoll erreichbar" gilt (siehe Projekt-
# konversation) – löst den Alternativ-Ziel-Vorschlag aus, BEVOR überhaupt an
# einen Flug gedacht wird (CLAUDE.md, Grundprinzip 5: Flüge ausgeschlossen,
# außer der Nutzer besteht danach ausdrücklich auf dem Fernziel).
_MAX_NACHHALTIGE_REISEZEIT_MINUTEN = 12 * 60

# Erkennung eines All-Inclusive-Wunsches bei F15 (unterkunft_anforderungen):
# bewusst regelbasiertes Schlüsselwort-Matching statt LLM-Erkennung (wie bei
# `besteht_auf_fernziel`) – die Entscheidung, welche DATENQUELLE angefragt
# wird, bleibt damit vollständig im deterministischen Layer (CLAUDE.md,
# Grundprinzip 1/3), nicht im LLM.
_ALL_INCLUSIVE_SCHLUESSELWOERTER = ("all inclusive", "all-inclusive", "allinclusive")

# Begrenzt, wie viele Unterkunfts-Kandidaten in der Chat-Vorschau (F15)
# gelistet werden – DIESELBE Zahl wie pipeline.py `_MAX_UNTERKUNFT_KANDIDATEN`
# (siehe Projektkonversation: "wie viele Unterkünfte das dann immer sind,
# such die Top 5 raus"), damit Chat-Vorschau und finale Mail übereinstimmen.
# Kein gemeinsamer Import, um keine Abhängigkeit von vorschlaege.py (Dialog-
# schicht) zu pipeline.py (Planungsschicht) einzuführen – zwei Konstanten
# mit demselben Wert statt eines Cross-Layer-Imports.
_MAX_UNTERKUNFT_KANDIDATEN = 5


def ist_all_inclusive_wunsch(text: str | None) -> bool:
    if not text:
        return False
    text_klein = text.lower()
    return any(schluesselwort in text_klein for schluesselwort in _ALL_INCLUSIVE_SCHLUESSELWOERTER)


def hole_echte_daten_fuer_vorschlag(
    frage: FrageDefinition,
    anfrage: ReiseAnfrage,
    client: MapsClient,
    spezialrecherche_aktivitaeten: list[str] | None = None,
    flug_client: FlugClient | None = None,
    flug_erwuenscht: bool = False,
    hotel_client: HotelClient | None = None,
    unterkunft_antwort_text: str | None = None,
    aktivitaeten_aktuell: list[str] | None = None,
) -> str:
    """
    Dispatch-Tabelle: welches Fragekatalog-Feld löst welchen API-/Mock-Aufruf
    aus. Gibt eine kompakte Textzusammenfassung zurück, die als Werkzeug-
    Ergebnis von `hole_api_daten` (siehe agent_tools.py) an das LLM zurückgeht,
    das daraus einen Vorschlag formuliert.

    Nutzt `anfrage.primaeres_reiseziel()`/`anfrage.wohnort` statt fester
    Platzhalterstrings – frühere Version schickte hier buchstäblich
    "Zielregion"/"Wohnort" an die Google-Maps-API, was im Live-Modus zu
    einem Absturz führte (siehe Projektkonversation). Da F07 (zielregionen)
    und F08 (wohnort) im Fragekatalog VOR allen Typ-C-Fragen liegen (F13,
    F15, F16), sind beide Werte an dieser Stelle im Dialog bereits gesetzt.

    `spezialrecherche_aktivitaeten`/`aktivitaeten_aktuell` (NUR für F16 relevant) kommen direkt vom
    Aufrufer (siehe agent_tools.py `hole_api_daten`), NICHT aus `anfrage` – die Frage ist zu diesem
    Zeitpunkt noch nicht bestätigt/gespeichert (`speichere_feld` läuft erst NACH Zustimmung des
    Nutzers). BEHOBENER BUG (siehe Projektkonversation: "Museen werden gefunden, aber keine
    Restaurants/Cafés"): `aktivitaeten_aktuell` fehlte ursprünglich komplett als Parameter – die
    Funktion fiel dadurch auf das noch leere `anfrage.aktivitaeten_interessen` zurück und suchte de
    facto nach GAR KEINER Kategorie (Places-Fallback auf den generischen Typ "tourist_attraction",
    siehe google_maps.py `_STANDARD_PLACE_TYPE") statt nach den tatsächlich genannten Interessen.

    `flug_client`/`flug_erwuenscht` (NUR für F13, verkehrsmittel_praeferenz,
    relevant): `flug_erwuenscht=True` heißt, der Nutzer hat im vorherigen
    Zustimmungs-Durchlauf einen Alternativ-Ziel-Vorschlag abgelehnt und
    besteht ausdrücklich auf dem ursprünglichen, weit entfernten Ziel (siehe
    agent_tools.py `hole_api_daten` – das LLM erkennt das selbst und setzt das Tool-Argument) – dann
    UND NUR DANN wird `flug_client` (siehe src/api/flightapi.py) tatsächlich
    für eine echte Flugsuche verwendet (CLAUDE.md, Grundprinzip 5: bewusste,
    eng begrenzte Ausnahme vom Flugverbot) – AUSSER `anfrage.all_inclusive_
    gewuenscht` ist gesetzt, dann direkt ohne Alternativziel-Umweg (siehe
    Projektkonversation: All-Inclusive-Pakete sind strukturell aufs Fliegen
    ausgelegt).

    `hotel_client`/`unterkunft_antwort_text` (NUR für F15, unterkunft_
    anforderungen, relevant): erkennt `unterkunft_antwort_text` (die noch
    unbestätigte aktuelle Antwort, analog zu `aktivitaeten_aktuell`)
    einen All-Inclusive-Wunsch, wird `hotel_client` (Hotelbeds-Hotelsuche,
    boardType=ALL_INCLUSIVE) statt der üblichen Google-Places-Unterkunftssuche
    verwendet.
    """
    ziel = anfrage.primaeres_reiseziel() or "Zielregion"

    if frage.feld == "unterkunft_anforderungen":
        if ist_all_inclusive_wunsch(unterkunft_antwort_text):
            if hotel_client is None:
                return (
                    "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Der Nutzer wünscht sich All-Inclusive, aber es "
                    "ist aktuell kein Hotelbeds-API-Zugang eingerichtet. Sag das ehrlich, statt ein Hotel zu erfinden."
                )
            hotels = hotel_client.suche_all_inclusive_hotels(client.geocode(ziel))
            if not hotels:
                return (
                    "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Der Nutzer wünscht sich All-Inclusive, aber es "
                    f"wurden für '{ziel}' keine All-Inclusive-Hotelangebote gefunden. Sag das ehrlich."
                )
            # Günstigster zuerst (echter Preis, siehe hotelbeds.py) – bestes verfügbares Budget-Signal,
            # dann auf die Top _MAX_UNTERKUNFT_KANDIDATEN gekappt (siehe Projektkonversation: "die Top 5,
            # die zu Budget/Vorstellungen/Lage passen"). Hotels ohne Preisangabe zuletzt, nicht erfunden.
            hotels = sorted(hotels, key=lambda h: h.preis_pro_nacht if h.preis_pro_nacht is not None else float("inf"))
            hotels = hotels[:_MAX_UNTERKUNFT_KANDIDATEN]
            hotels, barrierefrei_hinweise = filtere_unterkuenfte_barrierefrei(hotels, anfrage, client)
            zeilen = [
                f"- {h.name} (All Inclusive"
                + (f", ca. {h.preis_pro_nacht:.0f} €/Nacht" if h.preis_pro_nacht is not None else "")
                + f", Hotelbeds-Hotel-ID {h.externe_hotel_id})"
                for h in hotels
            ]
            return _mit_hinweisen(zeilen, barrierefrei_hinweise)
        # `praeferenz_text` lässt Google selbst nach Relevanz zur Nutzerantwort sortieren (siehe
        # google_maps.py), danach auf die Top _MAX_UNTERKUNFT_KANDIDATEN gekappt.
        unterkuenfte = client.suche_unterkuenfte(ziel, praeferenz_text=unterkunft_antwort_text)
        unterkuenfte = unterkuenfte[:_MAX_UNTERKUNFT_KANDIDATEN]
        unterkuenfte, barrierefrei_hinweise = filtere_unterkuenfte_barrierefrei(unterkuenfte, anfrage, client)
        zeilen = [
            f"- {u.name} (Preisniveau {u.preisniveau}/4, "
            f"{'zertifiziert nachhaltig' if u.zertifiziert_nachhaltig else 'nicht zertifiziert'})"
            for u in unterkuenfte
        ]
        return _mit_hinweisen(zeilen, barrierefrei_hinweise)

    if frage.feld == "aktivitaeten_interessen":
        # `aktivitaeten_aktuell`, falls übergeben (noch unbestätigte Antwort, siehe Moduldoku oben)
        # – NICHT `anfrage.aktivitaeten_interessen` (das ist beim ERSTEN Durchlauf noch leer, siehe
        # behobener Bug). Bei einer Korrektur/erneuten Suche ohne explizite Übergabe bleibt der
        # bereits bestätigte Wert der Fallback.
        aktivitaeten_fuer_suche = aktivitaeten_aktuell if aktivitaeten_aktuell is not None else anfrage.aktivitaeten_interessen
        aktivitaeten_bereits_im_paket, aktivitaeten_noch_zu_planen = trenne_bereits_im_paket_enthalten(
            aktivitaeten_fuer_suche, anfrage, hotel_client
        )
        # Suchradius richtet sich nach dem gewünschten lokalen Fortbewegungsmittel (F14, siehe
        # aufbereitung.py) – dieselbe Chat-Vorschau, die später auch tatsächlich eingeplant wird.
        _, radius_meter = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
        alle_pois = sammle_pois(
            ziel, aktivitaeten_noch_zu_planen, spezialrecherche_aktivitaeten or [], client, radius_meter=radius_meter
        )
        # Dieselbe harte Vorfilterung wie in pipeline.py (siehe vertraeglichkeit.py) – die Chat-Vorschau
        # soll keine Fisch-Restaurants bei genannter Fischallergie o.Ä. zeigen, die später ohnehin nicht
        # eingeplant würden (Chat-Vorschau und finale Planung sollen dieselben Kandidaten sehen).
        alle_pois, einschraenkungshinweise = filtere_pois_hart(alle_pois, anfrage, client)
        ziel_max = max_pois_fuer_reise(anfrage)
        # Vorschau nach Score sortiert (waehle_top_pois), nicht nach beliebiger
        # Fund-Reihenfolge – Gewichtung ist an dieser Stelle noch nicht bekannt
        # (der Nutzer beantwortet die Vergleichsfrage unten erst NACH diesem
        # Vorschlag), daher hier ohne `gewichtung`.
        vorschau = waehle_top_pois(alle_pois, aktivitaeten_noch_zu_planen, ziel_max)
        anfahrt_je_poi = _anfahrtsempfehlung_je_poi(client, client.geocode(ziel), vorschau)
        zeilen = [
            f"- {poi.name} ({poi.kategorie}, ca. {poi.required_time} Minuten"
            + (f", Schwierigkeitsgrad {poi.schwierigkeitsgrad}" if poi.schwierigkeitsgrad else "")
            + (", Quelle: OpenStreetMap statt Google" if poi.quelle == "osm_overpass" else "")
            + ")"
            + (f"\n  Anfahrt ab {ziel}: {anfahrt_je_poi[poi.id]}" if poi.id in anfahrt_je_poi else "")
            for poi in vorschau
        ]
        if aktivitaeten_bereits_im_paket:
            zeilen.insert(
                0,
                "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Folgende gewünschte Aktivitäten sind laut "
                f"Hotelbeds-Hoteldaten bereits im gebuchten All-Inclusive-Paket enthalten, dafür KEINE separate "
                f"Planung/POI-Suche nötig: {', '.join(aktivitaeten_bereits_im_paket)}.",
            )
        for hinweis_text in einschraenkungshinweise:
            zeilen.insert(0, f"HINWEIS AN DICH (LLM), erwähne dies dem Nutzer gegenüber kurz: {hinweis_text}")

        if len(alle_pois) > _WARNSCHWELLE_ROHTREFFER:
            # Bei 2+ genannten Interessen lohnt eine VERGLEICHENDE statt einer
            # pauschalen Rückfrage (siehe Projektkonversation: "hast du mehr
            # Lust auf X oder Y" statt einer Zahlen-/Ratingfrage) – die Antwort
            # geht über werte_zustimmung_aus (gw3) in `kategorie_gewichtung`
            # und beeinflusst, welche der zu vielen Treffer tatsächlich
            # eingeplant werden (siehe aufbereitung.py::waehle_top_pois).
            vergleichs_hinweis = ""
            if len(aktivitaeten_fuer_suche) >= 2:
                vergleichs_hinweis = (
                    " Nutze dafür idealerweise eine VERGLEICHENDE Frage zwischen zwei der genannten Interessen "
                    f"(z.B. 'Reizt dich {aktivitaeten_fuer_suche[0]} oder eher "
                    f"{aktivitaeten_fuer_suche[-1]} mehr?') statt nur pauschal um Zustimmung zu bitten – "
                    "die Antwort hilft, unter den vielen Treffern sinnvoll auszuwählen."
                )
            hinweis = (
                f"HINWEIS AN DICH (LLM), nicht an den Nutzer wörtlich vorlesen: Insgesamt wurden "
                f"{len(alle_pois)} passende Orte gefunden – mehr als {_WARNSCHWELLE_ROHTREFFER} können wir "
                f"nicht sinnvoll gemeinsam optimieren. Erkläre dem Nutzer kurz, dass es zu viele Treffer für "
                f"eine gemeinsame Optimierung sind, und frage, ob eine Auswahl von {ziel_max} Orten "
                f"(passend zur Reisedauer) für ihn in Ordnung ist, oder ob er seine Interessen weiter "
                f"eingrenzen möchte.{vergleichs_hinweis}"
            )
            return f"{hinweis}\n\nBeispielhafte Auswahl (Vorschau, {ziel_max} von {len(alle_pois)}):\n" + "\n".join(zeilen)

        return "\n".join(zeilen)

    if frage.feld == "verkehrsmittel_praeferenz":
        wohnort = anfrage.wohnort or "Wohnort"
        alternativen = client.reisealternativen(wohnort, ziel)
        zeilen = [f"- {alt.verkehrsmittel}: {alt.dauer_minuten} Minuten, {alt.kosten_euro:.0f} €" for alt in alternativen]

        if anfrage.all_inclusive_gewuenscht:
            # All-Inclusive ist strukturell aufs Fliegen ausgelegt (siehe Projektkonversation) – kein
            # Alternativziel-Umweg über die 12h-Schwelle, Flug direkt als Option, weiterhin mit CO2-Hinweis
            # (CLAUDE.md, Grundprinzip 5 bleibt Querschnittsprinzip, nur keine Blockade in diesem Modus).
            zeilen.extend(_hole_flugzeilen(flug_client, client, wohnort, ziel))
            return "\n".join(zeilen)

        nachhaltige_dauern = [alt.dauer_minuten for alt in alternativen if alt.verkehrsmittel.lower() != "flug"]
        kuerzeste_nachhaltige_dauer = min(nachhaltige_dauern) if nachhaltige_dauern else None
        ziel_zu_weit = (
            kuerzeste_nachhaltige_dauer is not None
            and kuerzeste_nachhaltige_dauer > _MAX_NACHHALTIGE_REISEZEIT_MINUTEN
        )

        if ziel_zu_weit and not flug_erwuenscht:
            # Alternativ-Ziel-Vorschlag ZUERST (CLAUDE.md, Grundprinzip 5) –
            # Flugsuche erst, wenn der Nutzer das im nächsten gw3-Durchlauf
            # ausdrücklich ablehnt (das LLM setzt dafür das Tool-Argument `flug_erwuenscht`, siehe
            # agent_tools.py `hole_api_daten`).
            hinweis = (
                "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Die schnellste nachhaltige Verbindung "
                f"(Bahn/Auto/Fernbus) nach '{ziel}' dauert {kuerzeste_nachhaltige_dauer} Minuten "
                f"(> {_MAX_NACHHALTIGE_REISEZEIT_MINUTEN} Minuten) – das ist keine menschlich sinnvolle Anreise "
                f"mehr. Reisewunsch des Nutzers (siehe bisheriges Gespräch): "
                f"{anfrage.reiseerlebnis_beschreibung or '-'!r}. Schlage EINE konkrete, deutlich näher gelegene "
                "Alternativregion vor, die ähnliche Eigenschaften bietet wie das, was sich der Nutzer erhofft "
                "(allgemeines Reisewissen ist hier ausnahmsweise zulässig, da es um eine grobe Gebiets-"
                "empfehlung geht, NICHT um eine konkrete Institution/einen Preis/eine Öffnungszeit). Frag, ob "
                "diese Alternative passt, oder ob der Nutzer trotzdem beim ursprünglichen Ziel bleiben möchte."
            )
            return f"{hinweis}\n\nEchte Reisezeiten zum ursprünglichen Ziel:\n" + "\n".join(zeilen)

        if flug_erwuenscht:
            zeilen.extend(_hole_flugzeilen(flug_client, client, wohnort, ziel))

        return "\n".join(zeilen)

    raise ValueError(
        f"Kein Datenabruf (Knoten c1) für Feld '{frage.feld}' definiert. "
        "Betrifft nur Fragen mit api_abruf_noetig=True (siehe katalog.py)."
    )


def _hole_flugzeilen(flug_client: FlugClient | None, client: MapsClient, wohnort: str, ziel: str) -> list[str]:
    """
    Echte Flugsuche (siehe flightapi.py) – mit ehrlicher Fehlerkommunikation
    statt Absturz oder erfundener Daten (Grundprinzip 1): fehlt der Client
    (keine FlightAPI-Credentials) oder schlägt die Anfrage fehl, wird das dem
    Nutzer über den regulären Vorschlagstext transparent mitgeteilt.
    """
    if flug_client is None:
        return ["- Flug: aktuell keine Flugsuche verfügbar (kein FlightAPI-Zugang eingerichtet)"]
    try:
        distanz_km = _luftlinie_km(client.geocode(wohnort), client.geocode(ziel))
        fluege = flug_client.suche_fluege(wohnort, ziel, distanz_km)
    except (RuntimeError, RequestException) as fehler:
        return [f"- Flug: Suche fehlgeschlagen ({fehler})"]
    if not fluege:
        return ["- Flug: für diese Strecke keine Angebote gefunden"]
    return [
        f"- Flug: {flug.dauer_minuten} Minuten, {flug.kosten_euro:.0f} € "
        "(deutlich höhere CO2-Emissionen als Bahn/Auto/Fernbus)"
        for flug in fluege
    ]


def trenne_bereits_im_paket_enthalten(
    aktivitaeten: list[str], anfrage: ReiseAnfrage, hotel_client: HotelClient | None
) -> tuple[list[str], list[str]]:
    """
    Prüft für JEDE genannte Aktivität, ob sie sich einer Hotelbeds-Amenity
    zuordnen lässt (siehe hotelbeds.py `amenity_fuer_aktivitaet`) UND das
    bereits bestätigte All-Inclusive-Hotel (F15, `anfrage.all_inclusive_
    hotel_id`) diese Amenity laut echter Bestätigungsabfrage tatsächlich hat
    (`hotel_hat_amenity` – KEINE Amenity-Liste wird erfunden, siehe dort).
    Ohne All-Inclusive-Hotel oder ohne zuordenbare Amenity bleibt eine
    Aktivität einfach unverändert in der zweiten Liste (normale POI-Planung).

    `aktivitaeten` wird EXPLIZIT übergeben (nicht aus `anfrage` gelesen):
    zum Zeitpunkt des Datenabrufs (c1, NOCH unbestätigte Antwort) UND zum
    Zeitpunkt der Bestätigung (b6, chat.py) ist der jeweils relevante Wert
    unterschiedlich verlässlich verfügbar – siehe Aufrufer.

    Returns: (bereits_im_paket_enthalten, noch_per_poi_zu_planen)
    """
    if not anfrage.all_inclusive_hotel_id or hotel_client is None or not anfrage.all_inclusive_hotel_koordinaten:
        return [], list(aktivitaeten)

    bereits_enthalten: list[str] = []
    noch_zu_planen: list[str] = []
    for aktivitaet in aktivitaeten:
        amenity = amenity_fuer_aktivitaet(aktivitaet)
        if amenity and hotel_client.hotel_hat_amenity(
            anfrage.all_inclusive_hotel_id, anfrage.all_inclusive_hotel_koordinaten, amenity
        ):
            bereits_enthalten.append(aktivitaet)
        else:
            noch_zu_planen.append(aktivitaet)
    return bereits_enthalten, noch_zu_planen


def _anfahrtsempfehlung_je_poi(
    client: MapsClient, ursprung: tuple[float, float], pois: list[POI]
) -> dict[int, str]:
    """
    Ermittelt je POI die `_ANFAHRT_MAX_OPTIONEN` schnellsten Verkehrsmittel
    (echte Reisezeiten via `client.anfahrtszeiten_minuten`, EIN Aufruf PRO
    Modus statt einer pro POI) mit einer kurzen, aus der Dauer selbst
    abgeleiteten Begründung – keine erfundene Empfehlung (CLAUDE.md,
    Grundprinzip 1), sondern reine Textformulierung echter Zahlen.
    """
    if not pois:
        return {}
    dauer_je_modus: dict[str, list[int]] = {}
    for modus in _ANFAHRT_MODI_LABEL:
        dauer_je_modus[modus] = client.anfahrtszeiten_minuten(ursprung, [(poi.x, poi.y) for poi in pois], modus=modus)

    empfehlung_je_poi: dict[int, str] = {}
    for index, poi in enumerate(pois):
        optionen = sorted(
            (
                (modus, dauern[index])
                for modus, dauern in dauer_je_modus.items()
                if dauern[index] is not None and dauern[index] >= 0  # -1 = keine Route gefunden (siehe google_maps.py)
            ),
            key=lambda eintrag: eintrag[1],
        )[:_ANFAHRT_MAX_OPTIONEN]
        if not optionen:
            continue
        teile = []
        for i, (modus, minuten) in enumerate(optionen):
            if i == 0:
                begruendung = "schnellste Option"
            elif modus == "walking" and minuten <= _ANFAHRT_ZU_FUSS_ANGENEHM_MINUTEN:
                begruendung = "kurze Strecke, gut zu Fuß machbar"
            else:
                begruendung = "gute Alternative"
            teile.append(f"{_ANFAHRT_MODI_LABEL[modus]} ca. {minuten} Min. ({begruendung})")
        empfehlung_je_poi[poi.id] = " oder ".join(teile)
    return empfehlung_je_poi


def _mit_hinweisen(zeilen: list[str], hinweise: list[str]) -> str:
    """Stellt Einschränkungs-Hinweise (siehe vertraeglichkeit.py) als "HINWEIS AN DICH (LLM)"-Block
    voran, analog zu den bestehenden Hinweis-Mechanismen dieser Datei (z.B. `aktivitaeten_bereits_im_paket`)."""
    block = [f"HINWEIS AN DICH (LLM), erwähne dies dem Nutzer gegenüber kurz: {h}" for h in hinweise]
    return "\n".join(block + zeilen)


def _luftlinie_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Grobe Luftlinien-Schätzung (Grad -> km), analog zu google_maps.py/toptw.py."""
    return math.dist(a, b) * 111

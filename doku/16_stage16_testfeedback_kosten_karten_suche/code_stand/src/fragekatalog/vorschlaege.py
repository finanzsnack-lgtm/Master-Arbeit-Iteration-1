"""
Datenabruf für Typ-C-Fragen: wird vom LLM-Agenten über das Werkzeug `hole_api_daten` (siehe
agent_tools.py) aufgerufen, BEVOR ein Vorschlag formuliert wird.

Bewusste Trennung von agent_tools.py: der eigentliche API-/Mock-Aufruf ist reiner,
deterministischer Code ohne LLM-Beteiligung (CLAUDE.md, Grundprinzip 1 – "Alle Fakten kommen aus
realen APIs"). Das LLM bekommt das Ergebnis anschließend nur noch als fertigen Text zur
Formulierung.

Typ-C-Felder: aktivitaeten_interessen (F16, volle Kandidaten-Vorschau) und verkehrsmittel_
praeferenz (F13, echte Alternativen inkl. Nachhaltigkeits-Nudge) laufen über die Dispatch-Tabelle
`hole_echte_daten_fuer_vorschlag` unten. unterkunft_anforderungen (F15, sucht GENAU EINE
Unterkunft und schlägt sie zur Bestätigung vor) und lokaler_transport_praeferenz (F14, Verleih-
Suche) laufen über eigene, direkte Funktionen (`suche_unterkunft`/`suche_verleih_nahe_
unterkunft`), weil ihr Ergebnis zusätzlich als Objekt auf der Anfrage gespeichert werden muss
(siehe agent_tools.py).
"""
from __future__ import annotations

import math

from src.api.google_maps import MapsClient
from src.api.typen import POI, Unterkunft
from src.datenaufbereitung.aufbereitung import (
    erkenne_leihwunsch,
    gewichte_nach_naehe_zum_depot,
    max_pois_fuer_reise,
    parameter_fuer_lokalen_transport,
    waehle_top_pois,
)
from src.datenaufbereitung.poi_sammlung import sammle_pois
from src.datenaufbereitung.vertraeglichkeit import filtere_pois_hart, filtere_unterkuenfte_barrierefrei
from src.fragekatalog.katalog import FrageDefinition
from src.fragekatalog.schema import ReiseAnfrage
from src.optimierung.verkehrsmittelwahl import bewerte_alternativen, nachhaltigkeits_nudge

# Verkehrsmittel, für die je Aktivität eine Anfahrtszeit ermittelt wird (siehe
# `_anfahrtsempfehlung_je_poi`) – maximal zwei konkrete, mit echten Reisezeiten begründete Optionen
# statt einer erfundenen pauschalen Empfehlung (CLAUDE.md, Grundprinzip 1).
_ANFAHRT_MODI_LABEL = {"walking": "zu Fuß", "transit": "mit öffentlichen Verkehrsmitteln", "driving": "mit dem Auto"}
_ANFAHRT_MAX_OPTIONEN = 2
# Grenze, ab der "zu Fuß" trotz kurzer werdender Distanz als eher unbequem statt als "gut machbar"
# begründet wird (grobe, dokumentierte Annahme, dient nur der Textformulierung).
_ANFAHRT_ZU_FUSS_ANGENEHM_MINUTEN = 20

# Ab wie vielen ROH-Treffern (vor der Kappung) der Bot den Nutzer explizit informiert und fragt,
# statt einfach still zu kappen. Der tatsächlich angebotene/verwendete Wert ist
# `max_pois_fuer_reise(anfrage)` (aufbereitung.py, Tage-Formel) – DERSELBE Wert, den pipeline.py
# auch wirklich an Optimierung 1 übergibt, damit "wir können nicht mehr optimieren" stimmt.
_WARNSCHWELLE_ROHTREFFER = 10

# Ab welcher schnellsten Reisezeit (Bahn/Auto/Fernbus) ein Ziel als "nicht mehr menschlich
# sinnvoll erreichbar" gilt (CLAUDE.md, Grundprinzip 5: Flüge sind ausgeschlossen, es gibt daher
# keine Alternative zu Bahn/Auto/Fernbus) – löst einen Alternativ-Ziel-Vorschlag aus.
_MAX_REISEZEIT_MINUTEN = 12 * 60

# F14-Fahrzeugname -> Suchbegriff für die Verleih-Suche (Freitext, direkt an Google Places Text
# Search durchgereicht, siehe google_maps.py `suche_pois`).
_VERLEIH_KATEGORIE_JE_FAHRZEUG = {"Auto": "Autoverleih", "Fahrrad": "Fahrradverleih"}


def suche_unterkunft(
    anfrage: ReiseAnfrage, client: MapsClient, unterkunft_antwort_text: str | None
) -> tuple[str, Unterkunft | None]:
    """
    F15 (unterkunft_anforderungen), eigener direkter Pfad statt Dispatch-Tabelle (analog zu
    `suche_verleih_nahe_unterkunft`): sucht GENAU EINE echte Unterkunft passend zur genannten
    Anforderung und gibt sie als kurzen Vorschlag zurück, den das LLM dem Nutzer zur Bestätigung
    vorlegt ("passt das für dich?").

    Gibt (text, gefundene_unterkunft) zurück – `gefundene_unterkunft` wird vom Aufrufer
    (agent_tools.py) zwischengespeichert und bei Bestätigung durch `speichere_feld` auf
    `anfrage.unterkunft_name`/`_koordinaten`/`_place_id` übernommen, damit später (Optimierung 1,
    Verleih-Suche) dieselbe Unterkunft verwendet wird, die im Chat vorgeschlagen wurde.
    """
    ziel = anfrage.primaeres_reiseziel() or "Zielregion"
    unterkuenfte = client.suche_unterkuenfte(ziel, praeferenz_text=unterkunft_antwort_text)
    unterkuenfte, barrierefrei_hinweise = filtere_unterkuenfte_barrierefrei(unterkuenfte, anfrage, client)
    if not unterkuenfte:
        return (
            "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Für die genannte Anforderung wurden in "
            f"'{ziel}' KEINE Unterkünfte gefunden. Sag das dem Nutzer ehrlich.",
            None,
        )
    gewaehlt = unterkuenfte[0]
    zeile = (
        f"- {gewaehlt.name} (Preisniveau {gewaehlt.preisniveau}/4, "
        f"{'zertifiziert nachhaltig' if gewaehlt.zertifiziert_nachhaltig else 'nicht zertifiziert'})"
    )
    return _mit_hinweisen([zeile], barrierefrei_hinweise), gewaehlt


def hole_echte_daten_fuer_vorschlag(
    frage: FrageDefinition,
    anfrage: ReiseAnfrage,
    client: MapsClient,
    spezialrecherche_aktivitaeten: list[str] | None = None,
    aktivitaeten_aktuell: list[str] | None = None,
    ziel_trotzdem_gewuenscht: bool = False,
) -> str:
    """
    Dispatch-Tabelle für die Felder, die OHNE Zwischenspeicherung eines Objekts auskommen
    (aktivitaeten_interessen, verkehrsmittel_praeferenz – unterkunft_anforderungen läuft über
    `suche_unterkunft`, lokaler_transport_praeferenz über `suche_verleih_nahe_unterkunft`, siehe
    Moduldoku oben). Gibt eine kompakte Textzusammenfassung zurück, die als Werkzeug-Ergebnis von
    `hole_api_daten` (siehe agent_tools.py) an das LLM zurückgeht, das daraus einen Vorschlag
    formuliert.

    Nutzt `anfrage.primaeres_reiseziel()`/`anfrage.wohnort` statt fester Platzhalterstrings, damit
    reale Ortsangaben an die Google-Maps-API gehen.

    `spezialrecherche_aktivitaeten`/`aktivitaeten_aktuell` (NUR für F16 relevant) kommen direkt vom
    Aufrufer, NICHT aus `anfrage` – die Frage ist zu diesem Zeitpunkt noch nicht bestätigt/
    gespeichert (`speichere_feld` läuft erst NACH Zustimmung des Nutzers), `anfrage.
    aktivitaeten_interessen` ist also noch leer.

    `ziel_trotzdem_gewuenscht` (NUR für F13 relevant): true, wenn der Nutzer nach einem
    Alternativ-Ziel-Vorschlag ausdrücklich auf dem ursprünglichen, weit entfernten Ziel besteht
    (das LLM erkennt das selbst und setzt das Tool-Argument) – unterdrückt den erneuten
    Alternativ-Ziel-Hinweis, zeigt aber weiterhin die echten Bahn/Auto/Fernbus-Alternativen.
    """
    ziel = anfrage.primaeres_reiseziel() or "Zielregion"

    if frage.feld == "aktivitaeten_interessen":
        aktivitaeten_fuer_suche = aktivitaeten_aktuell if aktivitaeten_aktuell is not None else anfrage.aktivitaeten_interessen
        _, radius_meter = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
        alle_pois = sammle_pois(
            ziel, aktivitaeten_fuer_suche, spezialrecherche_aktivitaeten or [], client, radius_meter=radius_meter,
            ernaehrung_einschraenkungen=anfrage.ernaehrung_einschraenkungen,
        )
        alle_pois, einschraenkungshinweise = filtere_pois_hart(alle_pois, anfrage, client)
        if anfrage.barrierefreiheit_oder_eingeschraenkt():
            alle_pois = gewichte_nach_naehe_zum_depot(alle_pois, client.geocode(ziel))
        ziel_max = max_pois_fuer_reise(anfrage)
        vorschau = waehle_top_pois(alle_pois, aktivitaeten_fuer_suche, ziel_max)
        anfahrt_je_poi = _anfahrtsempfehlung_je_poi(client, client.geocode(ziel), vorschau)
        zeilen = [
            f"- {poi.name} ({poi.kategorie}, ca. {poi.required_time} Minuten"
            + (f", Schwierigkeitsgrad {poi.schwierigkeitsgrad}" if poi.schwierigkeitsgrad else "")
            + (", Quelle: OpenStreetMap statt Google" if poi.quelle == "osm_overpass" else "")
            + ")"
            + (f"\n  Anfahrt ab {ziel}: {anfahrt_je_poi[poi.id]}" if poi.id in anfahrt_je_poi else "")
            for poi in vorschau
        ]
        for hinweis_text in einschraenkungshinweise:
            zeilen.insert(0, f"HINWEIS AN DICH (LLM), erwähne dies dem Nutzer gegenüber kurz: {hinweis_text}")

        if len(alle_pois) > _WARNSCHWELLE_ROHTREFFER:
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

        kuerzeste_dauer = min((alt.dauer_minuten for alt in alternativen), default=None)
        ziel_zu_weit = kuerzeste_dauer is not None and kuerzeste_dauer > _MAX_REISEZEIT_MINUTEN

        if ziel_zu_weit and not ziel_trotzdem_gewuenscht:
            hinweis = (
                "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Die schnellste Verbindung (Bahn/Auto/Fernbus) "
                f"nach '{ziel}' dauert {kuerzeste_dauer} Minuten (> {_MAX_REISEZEIT_MINUTEN} Minuten) – das ist "
                f"keine menschlich sinnvolle Anreise mehr, UND Flüge sind ausgeschlossen (Nachhaltigkeit). "
                f"Reisewunsch des Nutzers (siehe bisheriges Gespräch): {anfrage.reiseerlebnis_beschreibung or '-'!r}. "
                "Schlage EINE konkrete, deutlich näher gelegene Alternativregion vor, die ähnliche Eigenschaften "
                "bietet wie das, was sich der Nutzer erhofft (allgemeines Reisewissen ist hier ausnahmsweise "
                "zulässig, da es um eine grobe Gebietsempfehlung geht, NICHT um eine konkrete Institution/einen "
                "Preis/eine Öffnungszeit). Frag, ob diese Alternative passt, oder ob der Nutzer trotz der langen "
                "Fahrzeit beim ursprünglichen Ziel bleiben möchte."
            )
            return f"{hinweis}\n\nEchte Reisezeiten zum ursprünglichen Ziel:\n" + "\n".join(zeilen)

        bewertete = bewerte_alternativen(alternativen)
        nudge = nachhaltigkeits_nudge(bewertete)
        if nudge:
            zeilen.insert(0, f"NACHHALTIGKEITS-HINWEIS FÜR DICH (LLM), gerne im Vorschlag erwähnen: {nudge}")
        return "\n".join(zeilen)

    raise ValueError(
        f"Kein Datenabruf für Feld '{frage.feld}' definiert. Betrifft nur Fragen mit "
        "api_abruf_noetig=True (siehe katalog.py)."
    )


def suche_verleih_nahe_unterkunft(anfrage: ReiseAnfrage, client: MapsClient) -> tuple[str, POI | None]:
    """
    F14 (lokaler_transport_praeferenz), eigener direkter Pfad statt Dispatch-Tabelle: sucht bei
    erkanntem Leihwunsch (`aufbereitung.py::erkenne_leihwunsch`) einen echten Fahrzeug-Verleih und
    wählt davon den, der laut echter Koordinaten-Distanz am nächsten an der bereits bestätigten
    Unterkunft (F15, `anfrage.unterkunft_koordinaten`) liegt. Braucht deshalb eine bereits
    bestätigte Unterkunft – ohne sie wird ein Hinweis zurückgegeben, der das LLM anweist, diesen
    Aufruf erst NACH F15 zu wiederholen.

    Gibt (text, gewaehlter_poi) zurück – `gewaehlter_poi` wird vom Aufrufer (agent_tools.py) direkt
    auf `anfrage.lokaler_verleih_gewaehlt` gespeichert, da die Auswahl rein deterministisch
    (nach Distanz) ist und nicht vom LLM bestätigt werden muss.
    """
    fahrzeug = erkenne_leihwunsch(anfrage.lokaler_transport_praeferenz)
    if fahrzeug is None:
        return (
            "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Aus der aktuellen Antwort ist kein Wunsch nach "
            "einem vor Ort geliehenen Fahrzeug erkennbar – hier gibt es nichts zu suchen.",
            None,
        )
    if anfrage.unterkunft_koordinaten is None:
        return (
            "HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Die Unterkunft (F15) ist noch nicht bestätigt – "
            "rufe diese Suche ERST auf, nachdem F15 abgeschlossen ist, sonst kann die Nähe zur Unterkunft "
            "nicht geprüft werden.",
            None,
        )

    ziel = anfrage.primaeres_reiseziel() or "Zielregion"
    kategorie = _VERLEIH_KATEGORIE_JE_FAHRZEUG[fahrzeug]
    _, radius_meter = parameter_fuer_lokalen_transport(anfrage.lokaler_transport_praeferenz)
    kandidaten = sammle_pois(ziel, [kategorie], [], client, radius_meter=radius_meter)
    if not kandidaten:
        return (
            f"HINWEIS AN DICH (LLM), nicht wörtlich vorlesen: Kein {kategorie} in der Nähe von '{ziel}' gefunden. "
            "Sag das dem Nutzer ehrlich.",
            None,
        )

    naechster = min(kandidaten, key=lambda poi: math.dist((poi.x, poi.y), anfrage.unterkunft_koordinaten))
    distanz_km = math.dist((naechster.x, naechster.y), anfrage.unterkunft_koordinaten) * 111
    text = f"{fahrzeug}-Verleihe:\n- {naechster.name} (ca. {distanz_km:.1f} km von deiner Unterkunft entfernt)"
    return text, naechster


def _anfahrtsempfehlung_je_poi(
    client: MapsClient, ursprung: tuple[float, float], pois: list[POI]
) -> dict[int, str]:
    """
    Ermittelt je POI die `_ANFAHRT_MAX_OPTIONEN` schnellsten Verkehrsmittel (echte Reisezeiten via
    `client.anfahrtszeiten_minuten`, EIN Aufruf PRO Modus statt einer pro POI) mit einer kurzen,
    aus der Dauer selbst abgeleiteten Begründung – reine Textformulierung echter Zahlen.
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
                if dauern[index] is not None and dauern[index] >= 0  # -1 = keine Route gefunden
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
    """Stellt Einschränkungs-Hinweise (siehe vertraeglichkeit.py) als "HINWEIS AN DICH (LLM)"-Block voran."""
    block = [f"HINWEIS AN DICH (LLM), erwähne dies dem Nutzer gegenüber kurz: {h}" for h in hinweise]
    return "\n".join(block + zeilen)

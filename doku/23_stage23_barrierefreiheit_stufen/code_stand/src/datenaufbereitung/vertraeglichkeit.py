"""
Harte-Einschränkungs-Prüfung: gleicht bereits gefundene POI-/Unterkunft-Kandidaten gegen zwei vom
Nutzer explizit genannte, HARTE Einschränkungen ab – Ernährung/Allergien (F18,
`ernaehrung_einschraenkungen`) und Barrierefreiheitsbedarf (F09/F10/F15, siehe schema.py
`barrierefreiheit_oder_eingeschraenkt`).

Bewusst GETRENNT von aufbereitung.py::waehle_top_pois: dort geht es um WEICHE
Präferenz-Gewichtung ("was interessiert mich mehr"), hier um harte Ausschlusskriterien
("das darf NICHT vorgeschlagen werden"). Läuft NACH der POI-/Unterkunft-Suche, VOR dem
Präferenz-Scoring, sowohl in der Chat-Vorschau (vorschlaege.py) als auch in der finalen
Planung (pipeline.py), damit beide dieselben Kandidaten sehen.

Ausschluss NUR, wenn danach noch mindestens ein unbedenklicher Kandidat derselben Kategorie
übrig bleibt – sonst wird der einzige Treffer behalten, aber mit einem Hinweistext markiert
(CLAUDE.md, Grundprinzip 1: kein Verschweigen des Konflikts, aber auch kein Erfinden einer
nicht existierenden Alternative).

Ernährungs-Erkennung ist NAMENSBASIERT (Schlüsselwort-Teilstring auf den echten
Google-/OSM-Namen) statt über eine Zutatenliste: keine der angebundenen APIs liefert
Zutaten-/Allergendaten (Grundprinzip 1). Das ist eine grobe, konservative Heuristik (nur
eindeutig benennbare Fälle), kein Ersatz für eine Rückfrage vor Ort.

Barrierefreiheit nutzt dagegen ein echtes, strukturiertes Feld (Google Places Details,
`wheelchair_accessible_entrance`, siehe google_maps.py `ist_barrierefrei`), keine Heuristik.
"""
from __future__ import annotations

from typing import Protocol

from src.api.typen import POI, Unterkunft
from src.fragekatalog.schema import ReiseAnfrage

# (Trigger-Schlüsselwörter in der Nutzerantwort F18, Konflikt-Schlüsselwörter
# im Namen des Kandidaten) – bewusst konservativ (nur eindeutig benennbare
# Fälle), siehe Moduldoku.
_ERNAEHRUNG_KONFLIKT_REGELN: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("fisch", "meeresfrüchte", "seafood", "shellfish", "krustentier"),
     ("fisch", "sushi", "seafood", "meeresfrüchte", "austern", "lachs", "fischerei")),
    (("vegetarisch", "vegan"),
     ("steakhouse", "grillhaus", "grill", "metzgerei", "burger", "bbq", "fleischerei", "steak")),
    (("halal", "koscher", "kosher"),
     ("schwein", "pork")),
    (("nussallergie", "erdnussallergie", "nuss-allergie", "erdnuss-allergie"),
     ("nuss", "erdnuss")),
]


class _BarrierefreiheitsClient(Protocol):
    def ist_barrierefrei(self, place_id: str | None) -> bool | None: ...


def _ernaehrungskonflikt(name: str, einschraenkungen: list[str]) -> bool:
    if not einschraenkungen:
        return False
    text = " ".join(einschraenkungen).lower()
    name_klein = name.lower()
    return any(
        any(trigger_wort in text for trigger_wort in trigger) and any(konflikt_wort in name_klein for konflikt_wort in konflikt)
        for trigger, konflikt in _ERNAEHRUNG_KONFLIKT_REGELN
    )


def filtere_pois_hart(
    pois: list[POI], anfrage: ReiseAnfrage, client: _BarrierefreiheitsClient, barrierefreiheit_strikt: bool = False
) -> tuple[list[POI], list[str]]:
    """
    Entfernt POIs, die einer genannten Ernährungseinschränkung oder einem genannten
    Barrierefreiheitsbedarf widersprechen (sofern eine unbedenkliche Alternative derselben
    Kategorie übrig bleibt). Gibt (gefilterte_pois, hinweise) zurück – `hinweise` betrifft nur
    Konflikte, die NICHT ausgefiltert werden konnten (einziger Treffer der Kategorie).

    `barrierefreiheit_strikt=True` (siehe pipeline.py::plane_reise_und_abschliessen-Nachplanung):
    entfernt NICHT-barrierefreie POIs IMMER, auch als einzigen Treffer der Kategorie – wird nur
    für den zweiten Planungsversuch verwendet, nachdem eine erste Planung die Anforderung nicht
    erfüllt hat, und schließt bewusst weniger Programm ein statt einen bekannten Konflikt
    stillschweigend zu behalten.
    """
    ergebnis = list(pois)
    hinweise: list[str] = []

    if anfrage.ernaehrung_einschraenkungen:
        ergebnis, ernaehrungs_hinweise = _filtere_konflikte(
            ergebnis,
            lambda poi: _ernaehrungskonflikt(poi.name, anfrage.ernaehrung_einschraenkungen),
            lambda poi: (
                f"Hinweis: '{poi.name}' ist laut Namen auf Fisch/Fleisch/eine bestimmte Zutat spezialisiert – das "
                f"könnte mit Ihrer angegebenen Ernährungseinschränkung ({', '.join(anfrage.ernaehrung_einschraenkungen)}) "
                "kollidieren. Es wurde jedoch keine unbedenkliche Alternative in der Nähe gefunden."
            ),
            gruppieren_nach=lambda poi: poi.kategorie,
        )
        hinweise.extend(ernaehrungs_hinweise)

    if anfrage.barrierefreiheit_oder_eingeschraenkt():
        status_je_id = {poi.id: client.ist_barrierefrei(poi.place_id) for poi in ergebnis if poi.place_id}
        ergebnis, barrierefrei_hinweise = _filtere_konflikte(
            ergebnis,
            lambda poi: status_je_id.get(poi.id) is False,
            lambda poi: f"Hinweis: '{poi.name}' ist laut Google-Maps-Daten NICHT barrierefrei zugänglich.",
            gruppieren_nach=lambda poi: poi.kategorie,
            strikt=barrierefreiheit_strikt,
        )
        hinweise.extend(barrierefrei_hinweise)

    return ergebnis, hinweise


def filtere_unterkuenfte_barrierefrei(
    unterkuenfte: list[Unterkunft], anfrage: ReiseAnfrage, client: _BarrierefreiheitsClient
) -> tuple[list[Unterkunft], list[str]]:
    """Wie `filtere_pois_hart`, nur für Unterkunfts-Kandidaten (alle in derselben Kategorie "Unterkunft")."""
    if not anfrage.barrierefreiheit_oder_eingeschraenkt():
        return list(unterkuenfte), []
    status_je_id = {u.id: client.ist_barrierefrei(u.place_id) for u in unterkuenfte if u.place_id}
    return _filtere_konflikte(
        list(unterkuenfte),
        lambda u: status_je_id.get(u.id) is False,
        lambda u: f"Hinweis: '{u.name}' ist laut Google-Maps-Daten NICHT barrierefrei zugänglich.",
        gruppieren_nach=lambda u: "unterkunft",
    )


def pruefe_barrierefreiheit_des_plans(
    besuchte_place_ids: list[str], unterkunft_place_id: str | None, client: _BarrierefreiheitsClient
) -> list[str]:
    """
    Prüft den TATSÄCHLICH fertig geplanten Reiseplan (nicht nur die Kandidatenliste davor) noch
    einmal gegen echte Barrierefreiheits-Daten – Gegenstück zu `filtere_pois_hart`/`filtere_
    unterkuenfte_barrierefrei`, die VOR der Optimierung laufen und bei fehlender Alternative einen
    Konflikt bewusst behalten können (siehe Moduldoku). Gibt eine Liste der `place_id`s zurück, die
    laut Google-Maps-Daten NICHT barrierefrei sind – leer, wenn der Plan die Anforderung
    vollständig erfüllt.
    """
    alle_ids = list(besuchte_place_ids) + ([unterkunft_place_id] if unterkunft_place_id else [])
    return [place_id for place_id in alle_ids if client.ist_barrierefrei(place_id) is False]


def _filtere_konflikte(kandidaten, ist_konflikt, hinweistext, gruppieren_nach, strikt: bool = False):
    """
    Entfernt jeden Kandidaten, bei dem `ist_konflikt` zutrifft, SOFERN in derselben Gruppe (siehe
    `gruppieren_nach`) noch ein unbedenklicher Kandidat übrig bleibt – sonst wird er behalten und
    `hinweistext` erzeugt einen Warnhinweis (siehe Moduldoku: kein Verschweigen, kein Erfinden
    einer Alternative, die es nicht gibt). `strikt=True` hebt diese Ausnahme auf: der Kandidat wird
    IMMER entfernt, auch ohne Alternative in der Gruppe.
    """
    konfliktbehaftet = [k for k in kandidaten if ist_konflikt(k)]
    hinweise: list[str] = []
    ergebnis = list(kandidaten)
    for kandidat in konfliktbehaftet:
        gruppe = gruppieren_nach(kandidat)
        unbedenkliche_geschwister = [
            k for k in ergebnis
            if gruppieren_nach(k) == gruppe and k is not kandidat and not ist_konflikt(k)
        ]
        if unbedenkliche_geschwister or strikt:
            ergebnis = [k for k in ergebnis if k is not kandidat]
        else:
            hinweise.append(hinweistext(kandidat))
    return ergebnis, hinweise

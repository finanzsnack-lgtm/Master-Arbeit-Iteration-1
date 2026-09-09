"""
Harte-Einschränkungs-Prüfung: gleicht bereits gefundene POI-/Unterkunft-
Kandidaten (echte API-Daten aus c1) gegen zwei vom Nutzer explizit genannte,
HARTE Einschränkungen ab – Ernährung/Allergien (F18, `ernaehrung_
einschraenkungen`) und Barrierefreiheitsbedarf (F09/F10/F15, siehe
schema.py `barrierefreiheit_wichtig`).

Bewusst GETRENNT von aufbereitung.py::waehle_top_pois: dort geht es um
WEICHE Präferenz-Gewichtung ("was interessiert mich mehr"), hier um harte
Ausschlusskriterien ("das darf NICHT vorgeschlagen werden", siehe Projekt-
konversation: "wenn ich Fischallergie angebe, soll kein Fischrestaurant
vorgeschlagen werden" / "das soll für den barrierefreien Prozess genauso
gelten"). Läuft NACH der POI-/Unterkunft-Suche (c1), VOR dem Präferenz-
Scoring, sowohl in der Chat-Vorschau (vorschlaege.py) als auch in der
finalen Planung (pipeline.py), damit beide dieselben Kandidaten sehen.

Ausschluss NUR, wenn danach noch mindestens ein unbedenklicher Kandidat
derselben Kategorie übrig bleibt – sonst wird der einzige Treffer behalten,
aber mit einem Hinweistext markiert (CLAUDE.md, Grundprinzip 1: kein
Verschweigen des Konflikts, aber auch kein Erfinden einer nicht
existierenden Alternative).

Ernährungs-Erkennung ist bewusst NAMENSBASIERT (Schlüsselwort-Teilstring auf
den echten Google-/OSM-Namen) statt über eine Zutatenliste: keine der
angebundenen APIs liefert Zutaten-/Allergendaten (Grundprinzip 1). Das ist
eine grobe, konservative Heuristik (nur eindeutig benennbare Fälle), kein
Ersatz für eine Rückfrage vor Ort.

Barrierefreiheit nutzt dagegen ein ECHTES, strukturiertes Feld (Google
Places Details, `wheelchair_accessible_entrance`, verifiziert gegen die
offizielle Doku – siehe google_maps.py `ist_barrierefrei`), keine Heuristik.
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


def filtere_pois_hart(pois: list[POI], anfrage: ReiseAnfrage, client: _BarrierefreiheitsClient) -> tuple[list[POI], list[str]]:
    """
    Entfernt POIs, die einer genannten Ernährungseinschränkung oder einem
    genannten Barrierefreiheitsbedarf widersprechen (sofern eine
    unbedenkliche Alternative derselben Kategorie übrig bleibt). Gibt
    (gefilterte_pois, hinweise) zurück – `hinweise` betrifft nur Konflikte,
    die NICHT ausgefiltert werden konnten (einziger Treffer der Kategorie).
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

    if anfrage.barrierefreiheit_wichtig():
        status_je_id = {poi.id: client.ist_barrierefrei(poi.place_id) for poi in ergebnis if poi.place_id}
        ergebnis, barrierefrei_hinweise = _filtere_konflikte(
            ergebnis,
            lambda poi: status_je_id.get(poi.id) is False,
            lambda poi: f"Hinweis: '{poi.name}' ist laut Google-Maps-Daten NICHT barrierefrei zugänglich.",
            gruppieren_nach=lambda poi: poi.kategorie,
        )
        hinweise.extend(barrierefrei_hinweise)

    return ergebnis, hinweise


def filtere_unterkuenfte_barrierefrei(
    unterkuenfte: list[Unterkunft], anfrage: ReiseAnfrage, client: _BarrierefreiheitsClient
) -> tuple[list[Unterkunft], list[str]]:
    """Wie `filtere_pois_hart`, nur für Unterkunfts-Kandidaten (alle in derselben Kategorie "Unterkunft")."""
    if not anfrage.barrierefreiheit_wichtig():
        return list(unterkuenfte), []
    status_je_id = {u.id: client.ist_barrierefrei(u.place_id) for u in unterkuenfte if u.place_id}
    return _filtere_konflikte(
        list(unterkuenfte),
        lambda u: status_je_id.get(u.id) is False,
        lambda u: f"Hinweis: '{u.name}' ist laut Google-Maps-Daten NICHT barrierefrei zugänglich.",
        gruppieren_nach=lambda u: "unterkunft",
    )


def _filtere_konflikte(kandidaten, ist_konflikt, hinweistext, gruppieren_nach):
    """
    Entfernt jeden Kandidaten, bei dem `ist_konflikt` zutrifft, SOFERN in
    derselben Gruppe (siehe `gruppieren_nach`) noch ein unbedenklicher
    Kandidat übrig bleibt – sonst wird er behalten und `hinweistext` erzeugt
    einen Warnhinweis (siehe Moduldoku: kein Verschweigen, kein Erfinden
    einer Alternative, die es nicht gibt).
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
        if unbedenkliche_geschwister:
            ergebnis = [k for k in ergebnis if k is not kandidat]
        else:
            hinweise.append(hinweistext(kandidat))
    return ergebnis, hinweise

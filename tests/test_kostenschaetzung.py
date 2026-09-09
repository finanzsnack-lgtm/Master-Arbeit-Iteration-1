"""Tests für die informative Kostenschätzung (src/optimierung/kostenschaetzung.py)."""
from src.api.typen import POI
from src.optimierung.kostenschaetzung import (
    VERPFLEGUNG_PAUSCHALE_PRO_TAG_EURO,
    schaetze_gesamtkosten,
    schaetze_unterkunft_preis_pro_nacht,
)


def _poi(preisniveau: int | None) -> POI:
    return POI(id=1, name="X", kategorie="museum", x=0.0, y=0.0, score=1.0, required_time=60,
               opening=0, closing=600, preisniveau=preisniveau)


def test_schaetze_unterkunft_preis_pro_nacht_ohne_preisniveau_ist_none():
    assert schaetze_unterkunft_preis_pro_nacht(None) is None


def test_schaetze_unterkunft_preis_pro_nacht_steigt_mit_niveau():
    guenstig = schaetze_unterkunft_preis_pro_nacht(0)
    teuer = schaetze_unterkunft_preis_pro_nacht(4)
    assert guenstig is not None and teuer is not None
    assert teuer > guenstig


def test_schaetze_gesamtkosten_addiert_alle_bestandteile():
    kosten, unvollstaendig = schaetze_gesamtkosten(
        hinreise_kosten_euro=50.0, rueckreise_kosten_euro=50.0,
        unterkunft_preisniveau=2, naechte=3,
        eingeplante_pois=[_poi(2), _poi(2)], tage=4,
    )
    unterkunft_erwartet = schaetze_unterkunft_preis_pro_nacht(2) * 3
    verpflegung_erwartet = VERPFLEGUNG_PAUSCHALE_PRO_TAG_EURO * 4
    erwartete_kosten = 50.0 + 50.0 + unterkunft_erwartet + verpflegung_erwartet + 2 * 12.0
    assert kosten == erwartete_kosten
    assert unvollstaendig is False


def test_schaetze_gesamtkosten_ohne_unterkunft_preisniveau_markiert_unvollstaendig():
    kosten, unvollstaendig = schaetze_gesamtkosten(
        hinreise_kosten_euro=50.0, rueckreise_kosten_euro=50.0,
        unterkunft_preisniveau=None, naechte=3,
        eingeplante_pois=[], tage=4,
    )
    assert unvollstaendig is True
    # Trotzdem eine Zahl (Fahrt + Verpflegung), keine Null/None – Unterkunft trägt nur nichts bei.
    assert kosten == 50.0 + 50.0 + VERPFLEGUNG_PAUSCHALE_PRO_TAG_EURO * 4


def test_schaetze_gesamtkosten_poi_ohne_preisniveau_zaehlt_als_kostenlos():
    # POIs ohne Preisniveau (z.B. Parks) machen die Schätzung NICHT unvollständig – siehe Moduldoku.
    kosten_mit, _ = schaetze_gesamtkosten(
        hinreise_kosten_euro=0.0, rueckreise_kosten_euro=0.0,
        unterkunft_preisniveau=None, naechte=0,
        eingeplante_pois=[_poi(None)], tage=0,
    )
    assert kosten_mit == 0.0

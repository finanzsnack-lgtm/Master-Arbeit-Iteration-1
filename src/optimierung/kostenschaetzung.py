"""
Grobe, rein INFORMATIVE Kostenschätzung (Aktivitäten + Unterkunft + An-/Abreise + Verpflegungs-
pauschale) pro Person – wird im fertigen Reiseplan angezeigt und mit `ReiseAnfrage.budget_gesamt`
verglichen, beeinflusst aber NICHT die Auswahl der POIs in Optimierung 1 (siehe Rückfrage beim
Product Owner nach dem ersten Nutzertest: "nur informativ anzeigen").

Google Places liefert für die meisten Aktivitäten/Sehenswürdigkeiten KEINEN echten Euro-Preis,
nur ein grobes `price_level` (0-4, siehe POI.preisniveau/Unterkunft.preisniveau). Die Umrechnung
in einen ungefähren Euro-Betrag unten ist – wie die bestehende Kosten-je-km-Schätzung für Reisen
ohne `fare`-Feld (siehe google_maps.py) – eine dokumentierte, grobe Annahme statt eines erfundenen
Präzisionswerts (Grundprinzip 1: keine Fakten erfinden, aber klar gekennzeichnete Schätzungen sind
erlaubt, wo keine echten Daten verfügbar sind).
"""
from __future__ import annotations

from src.api.typen import POI

# Grobe Umrechnung von Googles price_level (0=kostenlos, 1=günstig, 2=mittel, 3=teuer, 4=sehr
# teuer) in einen ungefähren Euro-Betrag PRO EINTRITT/AKTIVITÄT bzw. PRO NACHT (Unterkunft) – reine
# Schätzung für die Anzeige, siehe Moduldoku.
_AKTIVITAET_PREIS_JE_NIVEAU_EURO: dict[int, float] = {0: 0.0, 1: 5.0, 2: 12.0, 3: 25.0, 4: 50.0}
_UNTERKUNFT_PREIS_PRO_NACHT_JE_NIVEAU_EURO: dict[int, float] = {0: 40.0, 1: 60.0, 2: 90.0, 3: 140.0, 4: 220.0}

# Grobe Tagespauschale für Verpflegung PRO PERSON (siehe Nutzervorgabe: "abends auch mal ein
# Restaurant und morgens mal außerhalb frühstücken sollten integriert sein, ein grober,
# realistischer Mittelwert, nicht zu hoch, nicht zu tief") – wie die CO2-Emissionsfaktoren eine
# dokumentierte Annahme statt einer erfundenen Präzisionszahl, vor Verwendung in der Arbeit ggf.
# gegen eine offizielle Quelle (z.B. Statistisches Bundesamt, Verbraucherpreise Gastronomie)
# verifizieren.
VERPFLEGUNG_PAUSCHALE_PRO_TAG_EURO = 35.0


def schaetze_unterkunft_preis_pro_nacht(preisniveau: int | None) -> float | None:
    """Öffentlich für webapp.py (Hotel-Vorschau-Karte im Chat, siehe dort) – None, wenn Places kein Preisniveau geliefert hat."""
    return _UNTERKUNFT_PREIS_PRO_NACHT_JE_NIVEAU_EURO.get(preisniveau) if preisniveau is not None else None


def schaetze_gesamtkosten(
    hinreise_kosten_euro: float, rueckreise_kosten_euro: float,
    unterkunft_preisniveau: int | None, naechte: int,
    eingeplante_pois: list[POI], tage: int,
) -> tuple[float, bool]:
    """
    Liefert (geschaetzte_gesamtkosten_euro, unvollstaendig) – PRO PERSON, rein informativ (siehe
    Moduldoku). `unvollstaendig=True` NUR, wenn die Unterkunft kein Preisniveau hatte (seltener
    Fall, da Places für Unterkünfte meist eines liefert) – fehlendes POI-Preisniveau wird dagegen
    stillschweigend als kostenlos angenommen (die meisten POIs ohne Preisniveau sind frei
    zugängliche Orte wie Parks/Plätze/Aussichtspunkte, siehe POI.preisniveau-Doku), macht das
    Ergebnis also NICHT automatisch "unvollständig".
    """
    kosten = hinreise_kosten_euro + rueckreise_kosten_euro
    kosten += VERPFLEGUNG_PAUSCHALE_PRO_TAG_EURO * tage

    unterkunft_preis = schaetze_unterkunft_preis_pro_nacht(unterkunft_preisniveau)
    unvollstaendig = unterkunft_preis is None
    if unterkunft_preis is not None:
        kosten += unterkunft_preis * naechte

    for poi in eingeplante_pois:
        if poi.preisniveau is not None:
            kosten += _AKTIVITAET_PREIS_JE_NIVEAU_EURO.get(poi.preisniveau, 0.0)

    return kosten, unvollstaendig

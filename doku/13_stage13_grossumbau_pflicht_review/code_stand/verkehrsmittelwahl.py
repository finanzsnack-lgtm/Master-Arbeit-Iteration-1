"""
Optimierung 2 – An-/Abreise (nachhaltige Verkehrsmittelwahl).

Kleiner Alternativenraum -> gewichtete Bewertung aller Alternativen über
Zeit, Kosten und CO2 (siehe CLAUDE.md, Abschnitt "Optimierung 2"). Enthält
außerdem den Nachhaltigkeits-Nudge für den Dialog ("Bahn braucht nur Δt
länger, spart X kg CO2.").
"""
from __future__ import annotations

from dataclasses import dataclass

from src.api.typen import ReiseAlternative
from src.optimierung.emissionsfaktoren import co2_kg


@dataclass(frozen=True)
class Gewichtung:
    zeit: float = 1 / 3
    kosten: float = 1 / 3
    co2: float = 1 / 3

    def __post_init__(self):
        gesamt = self.zeit + self.kosten + self.co2
        if not (0.99 <= gesamt <= 1.01):
            raise ValueError("Die drei Gewichte müssen in Summe 1 ergeben.")


@dataclass
class BewerteteAlternative:
    alternative: ReiseAlternative
    co2_kg: float
    score: float  # niedriger = besser (normalisierte, gewichtete Summe)


def _normalisieren(werte: list[float]) -> list[float]:
    """Min-Max-Normalisierung auf [0, 1]; bei identischen Werten -> 0 für alle."""
    minimum, maximum = min(werte), max(werte)
    spanne = maximum - minimum
    if spanne == 0:
        return [0.0 for _ in werte]
    return [(wert - minimum) / spanne for wert in werte]


def bewerte_alternativen(
    alternativen: list[ReiseAlternative],
    gewichtung: Gewichtung = Gewichtung(),
) -> list[BewerteteAlternative]:
    """Bewertet alle Alternativen gewichtet nach Zeit/Kosten/CO2; sortiert aufsteigend (beste zuerst)."""
    if not alternativen:
        return []

    co2_werte = [co2_kg(a.verkehrsmittel, a.distanz_km) for a in alternativen]
    zeit_norm = _normalisieren([a.dauer_minuten for a in alternativen])
    kosten_norm = _normalisieren([a.kosten_euro for a in alternativen])
    co2_norm = _normalisieren(co2_werte)

    bewertete = [
        BewerteteAlternative(
            alternative=alt,
            co2_kg=co2_wert,
            score=gewichtung.zeit * z + gewichtung.kosten * k + gewichtung.co2 * c,
        )
        for alt, co2_wert, z, k, c in zip(alternativen, co2_werte, zeit_norm, kosten_norm, co2_norm)
    ]
    return sorted(bewertete, key=lambda bewertung: bewertung.score)


def nachhaltigkeits_nudge(alternativen: list[BewerteteAlternative]) -> str | None:
    """
    Erzeugt die Nudge-Botschaft aus CLAUDE.md: "Bahn braucht nur Δt länger,
    spart X kg CO2." Vergleicht die Bahn-Option mit der insgesamt besten
    Alternative, sofern diese nicht bereits die Bahn ist und die Bahn
    tatsächlich weniger CO2 verursacht.
    """
    if len(alternativen) < 2:
        return None

    beste = alternativen[0]
    bahn = next((b for b in alternativen if b.alternative.verkehrsmittel.lower() == "bahn"), None)
    if bahn is None or bahn is beste:
        return None

    delta_minuten = bahn.alternative.dauer_minuten - beste.alternative.dauer_minuten
    ersparnis_kg = beste.co2_kg - bahn.co2_kg
    if ersparnis_kg <= 0:
        return None

    return (
        f"Die Bahn braucht nur {delta_minuten} Minuten länger, "
        f"spart aber {ersparnis_kg:.1f} kg CO2 gegenüber der schnellsten Alternative."
    )

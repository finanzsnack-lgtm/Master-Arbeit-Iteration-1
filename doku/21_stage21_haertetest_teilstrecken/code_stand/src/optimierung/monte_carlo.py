"""
Monte-Carlo-Härtetest (siehe CLAUDE.md, Abschnitt "Simulation –
Monte-Carlo-Härtetest"): prüft eine fertige Tagesroute unter stochastisch
gestörten Fahrzeiten auf Zeitfensterbrüche. Robustheits-Gateway: Wird der
Schwellenwert nicht erreicht, muss Optimierung 1 mit Sicherheitspuffern
erneut laufen (siehe `RobustheitsErgebnis.ist_robust`).
"""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass

from src.optimierung.toptw import TOPTWInstanz, Tagesroute, simuliere_route


@dataclass
class RobustheitsErgebnis:
    laeufe: int
    verletzungen: int
    quote_ohne_verletzung: float
    schwelle: float

    @property
    def ist_robust(self) -> bool:
        return self.quote_ohne_verletzung >= self.schwelle


def haertetest(
    instanz: TOPTWInstanz,
    route: Tagesroute,
    anzahl_laeufe: int = 1000,
    unsicherheitsfaktor: float = 0.2,
    schwelle: float = 0.95,
    zufalls_seed: int | None = None,
) -> RobustheitsErgebnis:
    """
    Führt `anzahl_laeufe` Simulationen durch, in denen jede Fahrzeit
    log-normal um den ursprünglichen (Google-)Schätzwert gestört wird, und
    zählt, in wie vielen Läufen mindestens ein Zeitfenster verletzt wird.

    Parameter (Verteilung, Läufe, Schwelle) sind laut CLAUDE.md beim Product
    Owner zu erfragen; die hier gewählten Defaults (Lognormal-Streuung 20 %,
    1000 Läufe, 95 %-Schwelle) sind ein begründeter erster Vorschlag und
    sollten vor der finalen Auswertung bestätigt werden.
    """
    zufall = random.Random(zufalls_seed)
    reihenfolge = [besuch.poi for besuch in route.besuche]
    verletzungen = 0

    for _ in range(anzahl_laeufe):
        gestoerte_instanz = _instanz_mit_gestoerten_fahrzeiten(instanz, unsicherheitsfaktor, zufall)
        ergebnis = simuliere_route(gestoerte_instanz, reihenfolge)
        if ergebnis is None:
            verletzungen += 1

    quote = 1 - (verletzungen / anzahl_laeufe)
    return RobustheitsErgebnis(
        laeufe=anzahl_laeufe, verletzungen=verletzungen, quote_ohne_verletzung=quote, schwelle=schwelle
    )


def _instanz_mit_gestoerten_fahrzeiten(
    instanz: TOPTWInstanz, unsicherheitsfaktor: float, zufall: random.Random
) -> TOPTWInstanz:
    """
    Erzeugt eine flache Kopie der TOPTW-Instanz, deren `reisezeit_minuten`
    die ursprüngliche Schätzung log-normal streut. Alle übrigen Constraints
    (Zeitfenster, Tagesbudget) bleiben unverändert.
    """
    gestoerte_instanz = copy.copy(instanz)
    urspruengliche_methode = instanz.reisezeit_minuten

    def gestoerte_reisezeit(a, b):
        # BEHOBENER BUG (live aufgefallen: math.log(0) bei sehr nah beieinanderliegenden POIs, für
        # die Google 0 Minuten Reisezeit meldet) – mindestens 1 Minute, bevor der Logarithmus
        # gebildet wird, analog zum bestehenden Luftlinien-Fallback (toptw.py::reisezeit_minuten,
        # ebenfalls `max(1, ...)`).
        basiswert = max(1, urspruengliche_methode(a, b))
        sigma = math.sqrt(math.log(1 + unsicherheitsfaktor**2))
        mu = math.log(basiswert) - sigma**2 / 2
        return max(1, round(zufall.lognormvariate(mu, sigma)))

    # Instanzattribut überschreibt die Klassenmethode nur für diese Kopie
    # (kein Einfluss auf `instanz` selbst).
    gestoerte_instanz.reisezeit_minuten = gestoerte_reisezeit  # type: ignore[method-assign]
    return gestoerte_instanz

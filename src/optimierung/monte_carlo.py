"""
Monte-Carlo-Härtetest für die An-/Abreise (Hinreise/Rückreise) – siehe CLAUDE.md, Abschnitt
"Simulation – Monte-Carlo-Härtetest".

ARCHITEKTURWECHSEL (siehe ENTSCHEIDUNGSLOG.md, Rückfrage): Der Härtetest lief ursprünglich gegen
die POI-zu-POI-Bewegungen VOR ORT (Tagesroute) – dort ist die Verpassgefahr durch ein paar Minuten
Fußweg/Fahrrad zwischen zwei Sehenswürdigkeiten praktisch nie relevant. Der eigentlich riskante Teil
einer Reise sind reale Bus-/Bahn-UMSTIEGE bei der An-/Abreise: Kommt der Anschlusszug noch, wenn der
Bus 5 Minuten Verspätung hat? Deshalb prüft der Härtetest jetzt stattdessen die `Teilstrecken`-Kette
einer Hinreise-/Rückreise-Alternative (siehe typen.py `Teilstrecke`, google_maps.py
`_teilstrecken_aus_steps`) – dieselben Daten, die für die Anzeige der Umstiege ohnehin schon von
Google Directions abgerufen werden, kein neuer API-Aufruf nötig.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.api.typen import Teilstrecke


@dataclass
class RobustheitsErgebnis:
    laeufe: int
    verletzungen: int
    quote_ohne_verletzung: float
    schwelle: float

    @property
    def ist_robust(self) -> bool:
        return self.quote_ohne_verletzung >= self.schwelle


def haertetest_teilstrecken(
    teilstrecken: list[Teilstrecke],
    anzahl_laeufe: int = 1000,
    unsicherheitsfaktor: float = 0.2,
    schwelle: float = 0.80,
    zufalls_seed: int | None = None,
) -> RobustheitsErgebnis:
    """
    Simuliert `anzahl_laeufe` Durchläufe der Teilstrecken-Kette: JEDE Teilstrecken-Dauer wird
    log-normal um die von Google gelieferte Schätzung gestreut, und bei jedem Umstieg (TRANSIT-
    Teilstrecke MIT bekannter `wartezeit_minuten`) wird geprüft, ob die bis dahin aufgelaufene
    Verspätung noch in diesen Puffer passt.

    Reicht der Puffer nicht mehr, gilt der Lauf als Verletzung (verpasster Anschluss) – KEINE
    Prüfung, ob eine spätere Ersatzverbindung noch rechtzeitig käme (Rückfrage-Ergebnis: dafür
    bräuchte es einen weiteren echten API-Abruf PRO verpasstem Anschluss und Lauf, was der Product
    Owner bewusst abgelehnt hat, um keine zusätzlichen Daten "auf Verdacht" nachzuladen – ein
    verpasster Anschluss zählt hier deshalb immer als gescheiterter Lauf, auch wenn im echten Leben
    z.B. der nächste Bus in 10 Minuten käme).

    Parameter (Verteilung, Läufe, Schwelle) sind laut CLAUDE.md beim Product Owner zu erfragen; die
    hier gewählten Defaults (Lognormal-Streuung 20 %, 1000 Läufe, 80 %-Schwelle – auf Wunsch des
    Product Owners von ursprünglich 95 % gesenkt) sind ein begründeter Vorschlag und sollten vor der
    finalen Auswertung bestätigt werden.
    """
    zufall = random.Random(zufalls_seed)
    verletzungen = sum(
        1 for _ in range(anzahl_laeufe) if _lauf_verpasst_anschluss(teilstrecken, unsicherheitsfaktor, zufall)
    )
    quote = 1 - (verletzungen / anzahl_laeufe)
    return RobustheitsErgebnis(
        laeufe=anzahl_laeufe, verletzungen=verletzungen, quote_ohne_verletzung=quote, schwelle=schwelle
    )


def _lauf_verpasst_anschluss(teilstrecken: list[Teilstrecke], unsicherheitsfaktor: float, zufall: random.Random) -> bool:
    """
    EIN simulierter Lauf durch die gesamte Teilstrecken-Kette. Gibt True zurück, sobald die
    aufgelaufene Verspätung an EINEM Umstieg die dort verfügbare Wartezeit übersteigt. Wird ein
    Umstieg noch erreicht, gilt die Verspätung als durch den Puffer "aufgeholt" (die
    Anschluss-Teilstrecke fährt planmäßig ab, unabhängig davon, wie viel vom Puffer verbraucht
    wurde) – nur Fußwege/Teilstrecken OHNE Wartezeit-Angabe tragen ihre eigene Störung ungebremst
    in die nächste Prüfung weiter.
    """
    aufgelaufene_verspaetung = 0
    for teilstrecke in teilstrecken:
        if teilstrecke.modus == "TRANSIT" and teilstrecke.wartezeit_minuten is not None:
            if aufgelaufene_verspaetung > teilstrecke.wartezeit_minuten:
                return True  # Anschluss verpasst
            aufgelaufene_verspaetung = 0  # Anschluss erreicht, Puffer hat die bisherige Verspätung aufgefangen
        gestoerte_dauer = _gestoerte_dauer(teilstrecke.dauer_minuten, unsicherheitsfaktor, zufall)
        aufgelaufene_verspaetung += max(0, gestoerte_dauer - teilstrecke.dauer_minuten)
    return False


def _gestoerte_dauer(dauer_minuten: int, unsicherheitsfaktor: float, zufall: random.Random) -> int:
    """Log-normal gestreute Dauer um `dauer_minuten` – mindestens 1 Minute vor der Logarithmus-
    Bildung (sonst math.log(0) bei einer Teilstrecke mit 0 Minuten Dauer, live aufgefallener Bug)."""
    basiswert = max(1, dauer_minuten)
    sigma = math.sqrt(math.log(1 + unsicherheitsfaktor**2))
    mu = math.log(basiswert) - sigma**2 / 2
    return max(1, round(zufall.lognormvariate(mu, sigma)))

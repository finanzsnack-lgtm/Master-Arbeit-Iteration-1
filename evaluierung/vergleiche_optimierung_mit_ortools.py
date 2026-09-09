"""
Unabhängige Prüfung von Optimierung 1 (src/optimierung/toptw.py, TOPTW gelöst mit ILS): derselbe
kleine, von Hand nachvollziehbare Beispiel-Datensatz wird EINMAL durch den eigenen ILS-Code und
EINMAL durch Google OR-Tools (etabliertes, fremdes Optimierungs-Toolkit, siehe requirements-
evaluierung.txt) gelöst – beide bekommen exakt dieselbe Reisezeit-Matrix, dieselben Zeitfenster,
denselben Score, dasselbe Tagesbudget. NICHT der eigene Code prüft sich selbst (siehe
Projektkonversation: "ich möchte nicht, dass du genau deinen eigenen Code nutzt, um das zu
prüfen") – OR-Tools ist eine vollständig unabhängige Implementierung.

WARUM OR-Tools als Vergleichsmaßstab (siehe Projektkonversation, Rückfrage): etabliertes,
quelloffenes Optimierungs-Toolkit von Google, in der Operations-Research-Praxis Standard für
Vehicle-Routing-artige Probleme, zitierfähig für die Masterarbeit. Das Team Orienteering Problem
with Time Windows selbst kennt OR-Tools nicht direkt als vorgefertigten Baustein, lässt sich aber
exakt über den etablierten "Prize-Collecting"-Trick modellieren: JEDER Besuch ist optional
(`AddDisjunction`), das Auslassen eines Ortes kostet in der Zielfunktion GENAU dessen Score, die
Bogenkosten (Fahrzeit) selbst fließen NICHT in die Zielfunktion ein (nur als Nebenbedingung über
Zeitfenster/Tagesbudget) – dadurch minimiert OR-Tools exakt "Summe der Scores NICHT besuchter
Orte", was demselben Ziel entspricht wie mein eigener Code: "Summe der Scores besuchter Orte"
maximieren (siehe `toptw.py::Tagesroute.score`).

Datensatz bewusst klein (6 POIs + Depot) und mit einem ABSICHTLICH knappen Tagesbudget (nicht alle
POIs passen rein) – ein echter Kompromiss ist nötig, keine triviale "alles besuchen"-Lösung.

Aufruf: python evaluierung/vergleiche_optimierung_mit_ortools.py
Voraussetzung: pip install -r requirements-evaluierung.txt
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

from src.api.typen import POI  # noqa: E402
from src.optimierung.toptw import TOPTWInstanz, iterated_local_search  # noqa: E402

# -- Eingabedaten -------------------------------------------------------------------------------
# Koordinaten frei erfunden (Gitterpunkte, KEINE echten Orte/Reisedaten – reines Rechenbeispiel).
# 1 Gitter-Einheit = 5 Fahrminuten (siehe _distanz_minuten) – ein grober, aber für BEIDE Solver
# identischer Maßstab, der ausschließlich diesem Vergleich dient.


@dataclass
class Testort:
    id: int
    name: str
    x: float
    y: float
    score: float
    required_time: int
    opening: int
    closing: int


DEPOT = Testort(id=0, name="Unterkunft", x=0, y=0, score=0, required_time=0, opening=0, closing=480)

TESTORTE = [
    Testort(id=1, name="Museum", x=2, y=1, score=8, required_time=60, opening=0, closing=480),
    Testort(id=2, name="Park", x=3, y=3, score=5, required_time=30, opening=0, closing=480),
    Testort(id=3, name="Restaurant", x=1, y=2, score=6, required_time=45, opening=120, closing=480),
    Testort(id=4, name="Aussichtspunkt", x=-2, y=2, score=9, required_time=40, opening=0, closing=200),
    Testort(id=5, name="Markt", x=-1, y=-2, score=4, required_time=50, opening=0, closing=480),
    Testort(id=6, name="Kirche", x=1, y=-1, score=3, required_time=20, opening=0, closing=480),
]

TAGESBUDGET_MINUTEN = 300  # absichtlich knapp: nicht alle 6 POIs passen rein (Summe required_time bereits 245)

_MINUTEN_JE_GITTEREINHEIT = 5


def _distanz_minuten(a: Testort, b: Testort) -> int:
    """Euklidischer Gitterabstand * `_MINUTEN_JE_GITTEREINHEIT`, gerundet – EINE feste Regel, aus der
    die Reisezeit-Matrix für BEIDE Solver identisch abgeleitet wird (siehe Moduldoku)."""
    return round(math.dist((a.x, a.y), (b.x, b.y)) * _MINUTEN_JE_GITTEREINHEIT)


def baue_reisezeitmatrix(orte: list[Testort]) -> dict[tuple[int, int], int]:
    matrix = {}
    for a in orte:
        for b in orte:
            if a.id != b.id:
                matrix[(a.id, b.id)] = _distanz_minuten(a, b)
    return matrix


def drucke_eingabedaten(orte: list[Testort], matrix: dict[tuple[int, int], int]) -> None:
    print("=== Eingabedaten (identisch für beide Solver) ===\n")
    print(f"Tagesbudget: {TAGESBUDGET_MINUTEN} Minuten\n")
    print(f"{'Ort':<15}{'Score':>6}{'Dauer':>7}{'Öffnung':>9}{'Schließung':>12}")
    for ort in [DEPOT] + orte:
        print(f"{ort.name:<15}{ort.score:>6.0f}{ort.required_time:>7}{ort.opening:>9}{ort.closing:>12}")
    print("\nReisezeiten (Minuten) ab Unterkunft:")
    for ort in orte:
        print(f"  Unterkunft -> {ort.name}: {matrix[(0, ort.id)]} min")


# -- Eigener Code (src/optimierung/toptw.py, UNVERÄNDERT) ---------------------------------------


def loese_mit_eigenem_code(orte: list[Testort], matrix: dict[tuple[int, int], int]) -> tuple[float, list[str]]:
    depot_poi = POI(
        id=DEPOT.id, name=DEPOT.name, kategorie="depot", x=DEPOT.x, y=DEPOT.y,
        score=0.0, required_time=0, opening=DEPOT.opening, closing=DEPOT.closing,
    )
    pois = [
        POI(id=o.id, name=o.name, kategorie="test", x=o.x, y=o.y, score=o.score,
            required_time=o.required_time, opening=o.opening, closing=o.closing)
        for o in orte
    ]
    instanz = TOPTWInstanz(
        pois=pois, tagesbudget_minuten=TAGESBUDGET_MINUTEN, anzahl_tage=1, depot=depot_poi,
        reisezeiten_minuten=matrix,
    )
    route = iterated_local_search(instanz, pois, max_ohne_verbesserung=200, zufalls_seed=1)
    besuchte_namen = [besuch.poi.name for besuch in route.besuche]
    return route.score, besuchte_namen


# -- Google OR-Tools (unabhängige Implementierung, siehe Moduldoku) -----------------------------


def loese_mit_ortools(orte: list[Testort], matrix: dict[tuple[int, int], int]) -> tuple[float, list[str]]:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    alle_orte = [DEPOT] + orte
    anzahl_knoten = len(alle_orte)

    def reisezeit(von_knoten: int, nach_knoten: int) -> int:
        if von_knoten == nach_knoten:
            return 0
        return matrix[(alle_orte[von_knoten].id, alle_orte[nach_knoten].id)]

    manager = pywrapcp.RoutingIndexManager(anzahl_knoten, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit_callback(von_index: int, nach_index: int) -> int:
        von_knoten = manager.IndexToNode(von_index)
        nach_knoten = manager.IndexToNode(nach_index)
        # Fahrzeit + Besuchsdauer am Startknoten (Standard-Muster für Zeitfenster-Dimensionen in
        # OR-Tools: die "Kosten" des Übergangs schließen die am Startknoten verbrachte Zeit ein).
        return reisezeit(von_knoten, nach_knoten) + alle_orte[von_knoten].required_time

    transit_index = routing.RegisterTransitCallback(transit_callback)

    # Bogenkosten bewusst NULL (siehe Moduldoku): die Zielfunktion soll ausschließlich aus den
    # Disjunction-Strafen (= ausgelassener Score) bestehen, nicht aus der Fahrzeit selbst.
    null_kosten_index = routing.RegisterTransitCallback(lambda i, j: 0)
    routing.SetArcCostEvaluatorOfAllVehicles(null_kosten_index)

    obergrenze = max(o.closing for o in alle_orte)
    routing.AddDimension(transit_index, obergrenze, obergrenze, False, "Zeit")
    zeit_dimension = routing.GetDimensionOrDie("Zeit")
    for knoten, ort in enumerate(alle_orte):
        index = manager.NodeToIndex(knoten)
        zeit_dimension.CumulVar(index).SetRange(ort.opening, ort.closing)

    zeit_dimension.CumulVar(routing.End(0)).SetMax(TAGESBUDGET_MINUTEN)

    for knoten in range(1, anzahl_knoten):  # Depot (Index 0) ist Pflicht, kein Disjunction nötig
        routing.AddDisjunction([manager.NodeToIndex(knoten)], int(alle_orte[knoten].score))

    parameter = pywrapcp.DefaultRoutingSearchParameters()
    parameter.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    parameter.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameter.time_limit.FromSeconds(10)

    loesung = routing.SolveWithParameters(parameter)
    if loesung is None:
        raise RuntimeError("OR-Tools fand keine gültige Lösung.")

    besuchte_namen = []
    gesamtscore = 0.0
    index = routing.Start(0)
    while not routing.IsEnd(index):
        knoten = manager.IndexToNode(index)
        if knoten != 0:
            besuchte_namen.append(alle_orte[knoten].name)
            gesamtscore += alle_orte[knoten].score
        index = loesung.Value(routing.NextVar(index))
    return gesamtscore, besuchte_namen


# -- Brute-Force (dritte, komplett unabhängige Prüfung: reine Kombinatorik, kein Optimierungs-
# Toolkit) -----------------------------------------------------------------------------------
# Bei nur 6 POIs sind alle 2^6=64 Teilmengen * je bis zu 6! Reihenfolgen vollständig durchrechenbar
# (deutlich unter einer Sekunde) – die denkbar einfachste, von JEDEM nachvollziehbare Prüfung: kein
# Optimierungsalgorithmus, nur "probiere wirklich ALLES aus".


def loese_mit_brute_force(orte: list[Testort], matrix: dict[tuple[int, int], int]) -> tuple[float, list[str]]:
    from itertools import combinations, permutations

    def strecke(von: Testort, nach: Testort) -> int:
        return 0 if von.id == nach.id else matrix[(von.id, nach.id)]

    bester_score = 0.0
    beste_route: list[Testort] = []
    for anzahl in range(len(orte) + 1):
        for teilmenge in combinations(orte, anzahl):
            for reihenfolge in permutations(teilmenge):
                uhrzeit = 0
                aktueller_ort = DEPOT
                gueltig = True
                for ort in reihenfolge:
                    ankunft = uhrzeit + strecke(aktueller_ort, ort)
                    beginn = max(ankunft, ort.opening)
                    if beginn > ort.closing:
                        gueltig = False
                        break
                    uhrzeit = beginn + ort.required_time
                    aktueller_ort = ort
                if not gueltig:
                    continue
                if uhrzeit + strecke(aktueller_ort, DEPOT) > TAGESBUDGET_MINUTEN:
                    continue
                score = sum(ort.score for ort in reihenfolge)
                if score > bester_score:
                    bester_score = score
                    beste_route = list(reihenfolge)
    return bester_score, [ort.name for ort in beste_route]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    matrix = baue_reisezeitmatrix([DEPOT] + TESTORTE)
    drucke_eingabedaten(TESTORTE, matrix)

    eigener_score, eigene_route = loese_mit_eigenem_code(TESTORTE, matrix)
    ortools_score, ortools_route = loese_mit_ortools(TESTORTE, matrix)
    brute_force_score, brute_force_route = loese_mit_brute_force(TESTORTE, matrix)

    print("\n=== Ergebnis: eigener Code (src/optimierung/toptw.py, ILS) ===")
    print(f"Score: {eigener_score:.1f}")
    print(f"Route: Unterkunft -> {' -> '.join(eigene_route)} -> Unterkunft")

    print("\n=== Ergebnis: Google OR-Tools (unabhängige Referenz) ===")
    print(f"Score: {ortools_score:.1f}")
    print(f"Route: Unterkunft -> {' -> '.join(ortools_route)} -> Unterkunft")

    print("\n=== Ergebnis: Brute-Force (dritte, unabhängige Referenz – garantiertes Optimum) ===")
    print(f"Score: {brute_force_score:.1f}")
    print(f"Route: Unterkunft -> {' -> '.join(brute_force_route)} -> Unterkunft")

    print("\n=== Vergleich ===")
    print(f"Garantiertes Optimum (Brute-Force): {brute_force_score:.1f}")
    for name, score in (("Eigener Code", eigener_score), ("OR-Tools", ortools_score)):
        if score >= brute_force_score:
            print(f"{name}: {score:.1f} von {brute_force_score:.1f} – Optimum erreicht.")
        else:
            differenz_prozent = (brute_force_score - score) / brute_force_score * 100
            print(f"{name}: {score:.1f} von {brute_force_score:.1f} ({differenz_prozent:.1f}% unter dem Optimum).")


if __name__ == "__main__":
    main()

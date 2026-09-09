"""
Sammelt Zwischenergebnisse EINES `pipeline.py::plane_reise()`-Laufs und schreibt sie als lesbare,
strukturierte Textdatei – NICHT für den normalen Betrieb (chat.py/webapp.py), sondern für
`pruefe_planung.py`, damit sich Optimierung 1 (TOPTW/ILS) und der Monte-Carlo-Härtetest gegen
echte Zwischendaten prüfen lassen: was wurde von Google/Overpass roh aufgenommen, was wurde davon
tatsächlich an Optimierung 1 weitergegeben, was kam dabei heraus, und mit welcher Eingabe/welchem
Ergebnis lief der Härtetest (Nutzerwunsch nach dem ersten Live-Test: "ich möchte wirklich prüfen
können, dass der Algorithmus vernünftig funktioniert").

`plane_reise` befüllt eine `PlanungsDebugSammlung` NUR, wenn eine übergeben wird (siehe
`debug_sammlung`-Parameter dort) – im normalen Betrieb (kein Parameter übergeben) entsteht dadurch
kein zusätzlicher Aufwand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.api.typen import POI, Teilstrecke
from src.optimierung.monte_carlo import RobustheitsErgebnis
from src.optimierung.toptw import Tagesroute, TOPTWInstanz


@dataclass
class PlanungsDebugSammlung:
    """Wird von `pipeline.py::plane_reise` an mehreren Stellen befüllt (siehe dort) – reine
    Datensammlung, keine eigene Logik."""

    # 1) Rohe Treffer aus sammle_pois() – VOR jedem Filtern/Scoring.
    rohe_pois: list[POI] = field(default_factory=list)
    # 2) Nach harten Einschränkungen (Ernährung/Barrierefreiheit, siehe vertraeglichkeit.py).
    pois_nach_harten_einschraenkungen: list[POI] = field(default_factory=list)
    # 3) Nach Scoring + Kappung (waehle_top_pois) – GENAU das, was Optimierung 1 als Kandidaten sieht.
    ausgewaehlte_pois: list[POI] = field(default_factory=list)
    # 4) Eingabe UND Ergebnis von Optimierung 1.
    toptw_instanz: TOPTWInstanz | None = None
    tagesrouten: list[Tagesroute] = field(default_factory=list)
    # 5) Eingabe UND Ergebnis des Monte-Carlo-Härtetests – NUR für die An-/Abreise (siehe
    # monte_carlo.py `haertetest_teilstrecken`, ENTSCHEIDUNGSLOG.md): leer/None, wenn keine
    # Teilstrecken-Daten vorlagen (Auto, oder Mock-Modus ohne Schritt-Details).
    hinreise_teilstrecken: list[Teilstrecke] = field(default_factory=list)
    hinreise_robustheit: RobustheitsErgebnis | None = None
    rueckreise_teilstrecken: list[Teilstrecke] = field(default_factory=list)
    rueckreise_robustheit: RobustheitsErgebnis | None = None


def _poi_zeile(poi: POI) -> str:
    zusatz = f", Preisniveau {poi.preisniveau}/4" if poi.preisniveau is not None else ""
    interesse = f" [{poi.nutzerinteresse}]" if poi.nutzerinteresse else ""
    return f"  - {poi.name} ({poi.kategorie}, Quelle: {poi.quelle}, Score {poi.score:.2f}{zusatz}){interesse}"


def _poi_liste(pois: list[POI]) -> list[str]:
    if not pois:
        return ["  (keine)"]
    return [_poi_zeile(poi) for poi in pois]


def _tagesrouten_zeilen(tagesrouten: list[Tagesroute]) -> list[str]:
    if not tagesrouten:
        return ["  (keine Tagesrouten)"]
    zeilen = []
    for tag_nr, tagesroute in enumerate(tagesrouten, start=1):
        zeilen.append(f"  Tag {tag_nr} ({len(tagesroute.besuche)} Besuche, Score {tagesroute.score:.2f}):")
        if not tagesroute.besuche:
            zeilen.append("    (kein Programm eingeplant)")
            continue
        for besuch in tagesroute.besuche:
            zeilen.append(
                f"    - {besuch.poi.name} (Ankunft {besuch.ankunft}, Wartezeit {besuch.wartezeit}, "
                f"Abfahrt {besuch.abfahrt}, Anfahrt: {besuch.anfahrt_modus or '?'})"
            )
    return zeilen


def _instanz_zeile(instanz: TOPTWInstanz | None) -> str:
    if instanz is None:
        return "  (keine Instanz)"
    return (
        f"  Tagesbudget {instanz.tagesbudget_minuten} Min., {instanz.anzahl_tage} Tag(e), "
        f"{len(instanz.pois)} Kandidaten-POIs, Geschwindigkeit {instanz.geschwindigkeit_kmh} km/h, "
        f"echte Reisezeitmatrix: {'ja' if instanz.reisezeiten_minuten is not None else 'nein (Luftlinie)'}"
    )


def _teilstrecken_zeilen(teilstrecken: list[Teilstrecke]) -> list[str]:
    if not teilstrecken:
        return ["  (keine Teilstrecken, z.B. Auto oder kein Härtetest gelaufen)"]
    zeilen = []
    for teilstrecke in teilstrecken:
        linie = f", Linie {teilstrecke.linie}" if teilstrecke.linie else ""
        wartezeit = (
            f", Umstiegs-Puffer {teilstrecke.wartezeit_minuten} Min."
            if teilstrecke.wartezeit_minuten is not None
            else ""
        )
        zeilen.append(
            f"  - {teilstrecke.von} -> {teilstrecke.nach} ({teilstrecke.modus}{linie}, "
            f"{teilstrecke.dauer_minuten} Min.{wartezeit})"
        )
    return zeilen


def _robustheit_zeilen(robustheit: RobustheitsErgebnis | None) -> list[str]:
    if robustheit is None:
        return ["  (kein Härtetest gelaufen)"]
    status = "robust" if robustheit.ist_robust else "NICHT robust"
    return [
        f"  {robustheit.laeufe} Läufe, {robustheit.verletzungen} mit verpasstem Anschluss, "
        f"Quote ohne Verletzung {robustheit.quote_ohne_verletzung:.1%} "
        f"(Schwelle {robustheit.schwelle:.0%}) -> {status}"
    ]


def schreibe_debug_datei(sammlung: PlanungsDebugSammlung, pfad: Path) -> None:
    """Schreibt `sammlung` als lesbare Textdatei nach `pfad` (siehe Moduldoku)."""
    zeilen = ["=== PLANUNGS-DEBUG ===", ""]

    zeilen.append(f"--- 1. Roh-Treffer von Google/Overpass, vor jedem Filtern ({len(sammlung.rohe_pois)}) ---")
    zeilen.extend(_poi_liste(sammlung.rohe_pois))
    zeilen.append("")

    zeilen.append(
        f"--- 2. Nach harten Einschränkungen, Ernährung/Barrierefreiheit "
        f"({len(sammlung.pois_nach_harten_einschraenkungen)} von {len(sammlung.rohe_pois)}) ---"
    )
    zeilen.extend(_poi_liste(sammlung.pois_nach_harten_einschraenkungen))
    zeilen.append("")

    zeilen.append(
        f"--- 3. AN OPTIMIERUNG 1 WEITERGEGEBEN, nach Scoring+Kappung "
        f"({len(sammlung.ausgewaehlte_pois)} von {len(sammlung.pois_nach_harten_einschraenkungen)}) ---"
    )
    zeilen.extend(_poi_liste(sammlung.ausgewaehlte_pois))
    zeilen.append("")

    zeilen.append("--- 4. ERGEBNIS OPTIMIERUNG 1 (TOPTW/ILS) ---")
    zeilen.append("Eingabe:")
    zeilen.append(_instanz_zeile(sammlung.toptw_instanz))
    zeilen.append("Ergebnis:")
    zeilen.extend(_tagesrouten_zeilen(sammlung.tagesrouten))
    zeilen.append("")

    zeilen.append("--- 5. MONTE-CARLO-HÄRTETEST (nur An-/Abreise, nur Bahn/Fernbus) ---")
    zeilen.append("Hinreise – Eingabe (Teilstrecken):")
    zeilen.extend(_teilstrecken_zeilen(sammlung.hinreise_teilstrecken))
    zeilen.append("Hinreise – Ergebnis:")
    zeilen.extend(_robustheit_zeilen(sammlung.hinreise_robustheit))
    zeilen.append("Rückreise – Eingabe (Teilstrecken):")
    zeilen.extend(_teilstrecken_zeilen(sammlung.rueckreise_teilstrecken))
    zeilen.append("Rückreise – Ergebnis:")
    zeilen.extend(_robustheit_zeilen(sammlung.rueckreise_robustheit))

    pfad.write_text("\n".join(zeilen), encoding="utf-8")

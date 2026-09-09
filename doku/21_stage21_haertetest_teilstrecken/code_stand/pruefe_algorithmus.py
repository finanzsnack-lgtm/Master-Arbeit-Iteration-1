"""
Eigenständiges, von Hand nachvollziehbares Beispiel für Optimierung 1 (TOPTW/ILS) UND den
Monte-Carlo-Härtetest – KEINE echten API-Daten (anders als pruefe_planung.py), sondern bewusst
kleine, runde Zahlen (Score, Besuchsdauer, Reisezeiten), damit sich Eingabe und Ausgabe Schritt für
Schritt von Hand nachrechnen lassen. Bewusst NICHT knapp bemessen (Nutzerwunsch: "braucht nicht so
eng sein, weil dann auch Fehler passieren könnten") – ein realistisches, aber leicht
nachvollziehbares Szenario statt eines Grenzfalls.

Schreibt (anders als die allgemeine Debug-Ausgabe in src/ausgabe/debug.py, die für die ECHTE
Such-/Filter-Kette von chat.py/webapp.py/pruefe_planung.py gedacht ist) JEDES einzelne Datenfeld,
das Optimierung 1 tatsächlich bekommt – Nutzerwunsch: "ich möchte jeden einzelnen Datensatz sehen,
der [an den Algorithmus] übergeben wird". Vier Abschnitte in EINER Datei:
  1. EINGABE Optimierung 1 (jedes POI-Feld + die komplette Reisezeiten-Matrix)
  2. AUSGABE Optimierung 1 (die tatsächlich geplante Route, POI für POI)
  3. EINGABE Monte-Carlo-Härtetest (dieselbe Route/Instanz + die Simulationsparameter)
  4. AUSGABE Monte-Carlo-Härtetest (Läufe, Verletzungen, Quote, robust/nicht robust)

Aufruf: python pruefe_algorithmus.py
Schreibt nach protokolle/beispiel_algorithmus_debug.txt.
"""
from __future__ import annotations

from src.api.typen import POI
from src.optimierung.monte_carlo import haertetest
from src.optimierung.toptw import TOPTWInstanz, plane_gesamte_reise
from src.protokoll import PROTOKOLL_VERZEICHNIS

# -- Eingabe: 4 handverlesene POIs mit runden Zahlen, KEINE Google-Daten -------------------------
# x/y bleiben 0.0 (ungenutzt) – die Reisezeiten unten sind vollständig als echte Matrix hinterlegt
# (REISEZEITEN_MINUTEN), der Luftlinien-Fallback (TOPTWInstanz.reisezeit_minuten) kommt dadurch nie
# zum Einsatz. So sind die Zeiten exakt die, die hier hingeschrieben stehen – nichts wird geschätzt.
DEPOT = POI(id=0, name="Unterkunft", kategorie="depot", x=0.0, y=0.0,
            score=0.0, required_time=0, opening=0, closing=1440)
MUSEUM = POI(id=1, name="Museum", kategorie="museum", x=0.0, y=0.0,
             score=5.0, required_time=90, opening=0, closing=480)
AUSSICHTSPUNKT = POI(id=2, name="Aussichtspunkt", kategorie="tourist_attraction", x=0.0, y=0.0,
                      score=8.0, required_time=45, opening=0, closing=480)
PARK = POI(id=3, name="Park", kategorie="park", x=0.0, y=0.0,
           score=3.0, required_time=30, opening=0, closing=480)
CAFE = POI(id=4, name="Café", kategorie="cafe", x=0.0, y=0.0,
           score=2.0, required_time=20, opening=0, closing=480)
POIS = [MUSEUM, AUSSICHTSPUNKT, PARK, CAFE]
ALLE_ORTE = [DEPOT] + POIS

# Reisezeiten in Minuten (frei erfunden, aber rund und symmetrisch) – (id_a, id_b) -> Minuten,
# beide Richtungen eingetragen, damit route.reisezeit_minuten() nie auf die Luftlinie zurückfällt.
REISEZEITEN_MINUTEN: dict[tuple[int, int], int] = {
    (0, 1): 20, (1, 0): 20,  # Unterkunft <-> Museum
    (0, 2): 30, (2, 0): 30,  # Unterkunft <-> Aussichtspunkt
    (0, 3): 10, (3, 0): 10,  # Unterkunft <-> Park
    (0, 4): 15, (4, 0): 15,  # Unterkunft <-> Café
    (1, 2): 25, (2, 1): 25,  # Museum <-> Aussichtspunkt
    (1, 3): 15, (3, 1): 15,  # Museum <-> Park
    (1, 4): 10, (4, 1): 10,  # Museum <-> Café
    (2, 3): 20, (3, 2): 20,  # Aussichtspunkt <-> Park
    (2, 4): 35, (4, 2): 35,  # Aussichtspunkt <-> Café
    (3, 4): 12, (4, 3): 12,  # Park <-> Café
}

# 4 Stunden – bewusst NICHT genug, um alle 4 POIs gleichzeitig zu besuchen (Besuchsdauern allein
# summieren sich schon auf 185 Min., plus Reisezeiten), Optimierung 1 muss also eine ECHTE Auswahl
# nach Score/Zeit-Verhältnis treffen statt trivial "alles passt rein".
TAGESBUDGET_MINUTEN = 240

# Monte-Carlo-Härtetest-Parameter (siehe monte_carlo.py::haertetest) – fester Seed, damit das
# Ergebnis bei jedem Lauf dieses Skripts reproduzierbar ist.
ANZAHL_LAEUFE = 1000
UNSICHERHEITSFAKTOR = 0.2
SCHWELLE = 0.95
ZUFALLS_SEED = 42


def _poi_alle_felder(poi: POI) -> list[str]:
    """ALLE Felder EINES POI – nicht nur eine Kurzfassung."""
    return [
        f"  - {poi.name}",
        f"      id: {poi.id}",
        f"      kategorie: {poi.kategorie}",
        f"      x, y (Koordinaten): {poi.x}, {poi.y}",
        f"      score: {poi.score}",
        f"      required_time (Besuchsdauer, Minuten): {poi.required_time}",
        f"      opening (Öffnung, Minuten seit Tagesbeginn): {poi.opening}",
        f"      closing (Schließung, Minuten seit Tagesbeginn): {poi.closing}",
        f"      place_id: {poi.place_id}",
        f"      quelle: {poi.quelle}",
        f"      schwierigkeitsgrad: {poi.schwierigkeitsgrad}",
        f"      nutzerinteresse: {poi.nutzerinteresse}",
        f"      besuchsklasse: {poi.besuchsklasse}",
        f"      foto_referenz: {poi.foto_referenz}",
        f"      preisniveau: {poi.preisniveau}",
    ]


def _instanz_konfiguration_zeilen(instanz: TOPTWInstanz) -> list[str]:
    """ALLE Konfigurationsfelder der TOPTWInstanz außerhalb der POI-Liste/Matrix selbst."""
    return [
        f"  tagesbudget_minuten: {instanz.tagesbudget_minuten}",
        f"  anzahl_tage: {instanz.anzahl_tage}",
        f"  geschwindigkeit_kmh (NUR Luftlinien-Fallback – hier ungenutzt, da reisezeiten_minuten vollständig ist): {instanz.geschwindigkeit_kmh}",
        f"  max_aktivitaetszeit_minuten: {instanz.max_aktivitaetszeit_minuten}",
        f"  pause_intervall_minuten: {instanz.pause_intervall_minuten}",
        f"  pause_dauer_minuten: {instanz.pause_dauer_minuten}",
        f"  mindestabstand_je_klassenpaar: {dict(instanz.mindestabstand_je_klassenpaar)}",
        f"  max_pois_pro_tag: {instanz.max_pois_pro_tag}",
        f"  Depot: {instanz.depot.name} (id={instanz.depot.id}, x={instanz.depot.x}, y={instanz.depot.y})",
    ]


def _reisezeiten_zeilen(instanz: TOPTWInstanz) -> list[str]:
    """JEDE einzelne Reisezeit-Matrix-Eintrag, lesbar mit Ortsnamen statt nur IDs."""
    name_je_id = {ort.id: ort.name for ort in ALLE_ORTE}
    if not instanz.reisezeiten_minuten:
        return ["  (keine echte Matrix hinterlegt – Luftlinien-Fallback wäre aktiv)"]
    zeilen = []
    for (von_id, nach_id), minuten in sorted(instanz.reisezeiten_minuten.items()):
        von_name = name_je_id.get(von_id, f"id={von_id}")
        nach_name = name_je_id.get(nach_id, f"id={nach_id}")
        zeilen.append(f"  {von_name} (id={von_id}) -> {nach_name} (id={nach_id}): {minuten} Min.")
    return zeilen


def _route_zeilen(instanz: TOPTWInstanz, tagesrouten) -> list[str]:
    zeilen = []
    eingeplante_ids = set()
    for tag_nr, route in enumerate(tagesrouten, start=1):
        zeilen.append(f"  Tag {tag_nr} ({len(route.besuche)} Besuche, Gesamtscore {route.score:.2f}):")
        if not route.besuche:
            zeilen.append("    (kein Programm eingeplant)")
            continue
        for besuch in route.besuche:
            eingeplante_ids.add(besuch.poi.id)
            zeilen.append(
                f"    - {besuch.poi.name}: Ankunft {besuch.ankunft} Min., Wartezeit {besuch.wartezeit} Min., "
                f"Abfahrt {besuch.abfahrt} Min. (Score {besuch.poi.score})"
            )
        rueckweg = instanz.reisezeit_minuten(route.besuche[-1].poi, instanz.depot)
        zeilen.append(f"    -> Rückweg zur Unterkunft: {rueckweg} Min. (Gesamtzeit Tag {tag_nr}: {route.besuche[-1].abfahrt + rueckweg} von {instanz.tagesbudget_minuten} Min. Budget)")
    nicht_eingeplant = [poi for poi in POIS if poi.id not in eingeplante_ids]
    if nicht_eingeplant:
        zeilen.append("  NICHT eingeplant (aus den Kandidaten übrig geblieben):")
        for poi in nicht_eingeplant:
            zeilen.append(f"    - {poi.name} (Score {poi.score}, hätte {poi.required_time} Min. gebraucht)")
    return zeilen


def main() -> None:
    instanz = TOPTWInstanz(
        pois=POIS, tagesbudget_minuten=TAGESBUDGET_MINUTEN, anzahl_tage=1, depot=DEPOT,
        reisezeiten_minuten=REISEZEITEN_MINUTEN,
    )

    zeilen = ["=== BEISPIEL: OPTIMIERUNG 1 (TOPTW/ILS) + MONTE-CARLO-HÄRTETEST ===", ""]

    zeilen.append("--- 1. EINGABE OPTIMIERUNG 1: jedes einzelne Datenfeld, das der Algorithmus bekommt ---")
    zeilen.append("Konfiguration:")
    zeilen.extend(_instanz_konfiguration_zeilen(instanz))
    zeilen.append("")
    zeilen.append(f"POI-Kandidaten ({len(POIS)}), JEDES Feld:")
    for poi in POIS:
        zeilen.extend(_poi_alle_felder(poi))
    zeilen.append("")
    zeilen.append(f"Vollständige Reisezeiten-Matrix ({len(REISEZEITEN_MINUTEN)} Einträge):")
    zeilen.extend(_reisezeiten_zeilen(instanz))
    zeilen.append("")

    tagesrouten = plane_gesamte_reise(instanz, tagesbudget_je_tag=[TAGESBUDGET_MINUTEN])

    zeilen.append("--- 2. AUSGABE OPTIMIERUNG 1: die tatsächlich geplante Route ---")
    zeilen.extend(_route_zeilen(instanz, tagesrouten))
    zeilen.append("")

    route = tagesrouten[0]
    zeilen.append("--- 3. EINGABE MONTE-CARLO-HÄRTETEST ---")
    zeilen.append("Getestete Instanz: siehe Abschnitt 1 (dieselbe Konfiguration/Matrix, unverändert).")
    zeilen.append("Getestete Route: siehe Abschnitt 2 (das Ergebnis von Optimierung 1, unverändert).")
    zeilen.append("Simulationsparameter:")
    zeilen.append(f"  anzahl_laeufe: {ANZAHL_LAEUFE}")
    zeilen.append(f"  unsicherheitsfaktor (log-normale Streuung jeder Fahrzeit): {UNSICHERHEITSFAKTOR}")
    zeilen.append(f"  schwelle (ab wann 'robust'): {SCHWELLE}")
    zeilen.append(f"  zufalls_seed (Reproduzierbarkeit): {ZUFALLS_SEED}")
    zeilen.append("")

    zeilen.append("--- 4. AUSGABE MONTE-CARLO-HÄRTETEST ---")
    if route.besuche:
        robustheit = haertetest(
            instanz, route, anzahl_laeufe=ANZAHL_LAEUFE, unsicherheitsfaktor=UNSICHERHEITSFAKTOR,
            schwelle=SCHWELLE, zufalls_seed=ZUFALLS_SEED,
        )
        status = "robust" if robustheit.ist_robust else "NICHT robust"
        zeilen.append(f"  Läufe: {robustheit.laeufe}")
        zeilen.append(f"  Läufe MIT Zeitfensterbruch: {robustheit.verletzungen}")
        zeilen.append(f"  Quote OHNE Verletzung: {robustheit.quote_ohne_verletzung:.1%}")
        zeilen.append(f"  Schwelle: {robustheit.schwelle:.0%}")
        zeilen.append(f"  Ergebnis: {status}")
    else:
        zeilen.append("  (kein Härtetest gelaufen, da Tag 1 leer war)")

    PROTOKOLL_VERZEICHNIS.mkdir(exist_ok=True)
    pfad = PROTOKOLL_VERZEICHNIS / "beispiel_algorithmus_debug.txt"
    pfad.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"Vollständige Eingaben/Ergebnisse geschrieben nach: {pfad}")


if __name__ == "__main__":
    main()

# Evaluierung — unabhängige Prüfung von Optimierung 1

Dieser Ordner enthält die unabhängige Korrektheitsprüfung des TOPTW/ILS-Algorithmus
(`src/optimierung/toptw.py`) für die Evaluation der Masterarbeit — getrennt von `tests/` (das
prüft *Verhalten bei bestimmten Eingaben*, z.B. "wird ein Zeitfenster korrekt verletzt erkannt"),
hier geht es um *Ergebnisqualität*: liefert der eigene ILS-Code für ein Beispiel dieselbe (im
Idealfall optimale) Lösung wie ein komplett unabhängiges Optimierungs-Verfahren?

## Warum eine eigene Prüfung nötig war

`tests/test_toptw.py` prüft ausschließlich mit dem eigenen Code (`simuliere_route`,
`iterated_local_search`) – eine Verhaltensabweichung, die sowohl in der Erzeugung als auch in der
Prüfung gleichermaßen vorhanden wäre (z.B. ein systematischer Denkfehler in der ILS-Logik selbst),
würde dort nicht auffallen. Für die Masterarbeit ist deshalb eine Prüfung nötig, die NICHT auf
denselben Code zurückgreift.

## Methode

`vergleiche_optimierung_mit_ortools.py` löst denselben kleinen, von Hand nachvollziehbaren
Beispiel-Datensatz (6 POIs + Depot, siehe Skript für alle Werte) mit DREI unabhängigen Methoden:

1. **Eigener Code** – `src/optimierung/toptw.py::iterated_local_search`, unverändert.
2. **Google OR-Tools** – etabliertes, quelloffenes Optimierungs-Toolkit (siehe
   `requirements-evaluierung.txt`), über den in der Operations-Research-Praxis üblichen
   "Prize-Collecting"-Trick als TOPTW modelliert (jeder Besuch optional, Auslassen kostet in der
   Zielfunktion genau den Score des Orts).
3. **Brute-Force** – reine Kombinatorik (alle 2⁶=64 Teilmengen × alle Reihenfolgen), garantiert das
   mathematische Optimum, weil bei nur 6 POIs vollständig durchrechenbar (< 1 Sekunde).

Alle drei bekommen exakt dieselbe Reisezeit-Matrix (einmal aus den Testort-Koordinaten berechnet,
dann an alle drei Methoden identisch weitergereicht) – kein Solver hat einen Datenvorteil.

## Ergebnis (12.08.2026)

| Methode | Score | Route |
|---|---|---|
| Eigener Code (ILS) | 31,0 | Museum → Park → Restaurant → Aussichtspunkt → Kirche |
| Google OR-Tools | 31,0 | Kirche → Museum → Aussichtspunkt → Restaurant → Park (andere Reihenfolge, gleicher Score) |
| Brute-Force (garantiertes Optimum) | 31,0 | Museum → Park → Restaurant → Aussichtspunkt → Kirche |

Alle drei erreichen exakt den mathematisch nachgewiesenen Optimalwert. Der Datensatz war bewusst so
gewählt, dass NICHT alle POIs ins Tagesbudget passen (Summe aller Besuchsdauern 245 min, aber
Reisezeiten dazwischen sprengen ein Budget von 300 min bei allen 6) – alle drei Methoden lassen
unabhängig voneinander denselben, niedrigst bewerteten Ort ("Markt", Score 4) korrekt aus. Kein
trivialer "alles besuchen"-Fall, echte Auswahlentscheidung.

## Aufruf

```
pip install -r requirements-evaluierung.txt
python evaluierung/vergleiche_optimierung_mit_ortools.py
```

## Einschränkungen (Grenzen dieser Prüfung, für die Arbeit transparent zu benennen)

- Nur EIN Beispiel-Datensatz, bewusst klein (6 POIs) für Nachvollziehbarkeit — keine Aussage über
  Laufzeit-/Qualitätsverhalten bei den in der echten Anwendung typischen größeren Kandidatenmengen
  (bis zu `_MAX_POIS_FUER_OPTIMIERUNG`, siehe aufbereitung.py).
  Da die Instanz jedoch bereits einen echten Auswahl-Kompromiss erzwingt (nicht alle POIs passen
  rein) und alle drei Methoden trotzdem exakt übereinstimmen, ist das ein starker, wenn auch nicht
  erschöpfender Beleg für die Korrektheit der Kernlogik (Zeitfenster-Prüfung, Tagesbudget,
  Scoring/Auswahl).
- Getestet nur der EINTAGES-Fall (`anzahl_tage=1`) – die Mehrtages-Logik (`plane_gesamte_reise`,
  POIs werden tageweise aus dem Pool entfernt) ist eine zusätzliche, hier nicht separat geprüfte
  Schicht darüber.
- Reine Erfindungsdaten (Koordinaten/Scores), keine echten POI-Daten – bewusst so, um das
  Kernverfahren isoliert zu prüfen, unabhängig von Datenqualität aus den echten APIs.

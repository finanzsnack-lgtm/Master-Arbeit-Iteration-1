# Station 9 — Flexibilitätspräferenz begrenzt POIs pro Tag

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 28)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `toptw.py`, `aufbereitung.py`
zum Zeitpunkt VOR dieser Änderung.

## Auslöser

Beim Durchsehen eines Testfalls fiel dem Nutzer auf: `flexibilitaet_praeferenz` (F05) wird im
Dialog abgefragt und in `ReiseAnfrage` gespeichert, aber nirgends im deterministischen Layer
tatsächlich ausgewertet — ein toter Fragekatalog-Eintrag. Nutzerwunsch: "wenn er sagt, er möchte
flexibler sein, dass man nur ein gewisses Fenster an POIs in einen Tag setzt und wenn er sagt, er
möchte unflexibel sein, dann setzt man halt ein gewisses höheres Maß an POIs pro Tag."

## Umsetzung

Neue Funktion `max_pois_pro_tag_fuer_flexibilitaet` (aufbereitung.py): zählt Treffer aus zwei
Schlüsselwort-Listen (flexibel: "flexibel"/"spontan"/"locker"/...; unflexibel: "fest"/
"durchgeplant"/"strukturiert"/...) statt nur den ersten Treffer zu nehmen — bei einem klaren
Überhang in eine Richtung wird eine Tages-Obergrenze gesetzt (flexibel: 2 POIs/Tag, unflexibel:
6 POIs/Tag), bei Gleichstand oder fehlender Angabe bewusst `None` (keine Einschränkung), statt
eine Präferenz zu erfinden.

**Wichtiger Nebeneffekt dieser Zähl-Logik:** Annegrets Testfall-Antwort ("Ein fester Plan ist ganz
nett, aber ich möchte auch spontan sein") enthält BEIDE Signalwörter ("fest" und "spontan") — die
heben sich gegenseitig auf, es wird keine Obergrenze erzwungen. Das ist eine bewusste, sichere
Entscheidung: bei echt gemischten Aussagen lieber gar keine zusätzliche Einschränkung als eine
geratene.

Neues Feld `TOPTWInstanz.max_pois_pro_tag` (toptw.py): harte Nebenbedingung in `simuliere_route`,
geprüft genau wie die bereits bestehenden Nebenbedingungen (Zeitfenster, Tagesbudget,
Mindestabstand) — unabhängig davon, ob zeitlich noch mehr POIs in den Tag passen würden.

## Live-Verifikation

`pruefe_planung.py Jakob` ("eher flexibel", 4-Tage-Reise Innsbruck): vorher 5–6 POIs an einzelnen
Tagen (z.B. Climbing Camps, KI-Kletterzentrum, BlocBox-Training, Restaurant, Le Murge an einem
Tag), nachher konsequent genau 2 POIs pro Tag mit deutlich mehr freier Zeit dazwischen.

## Tests

6 neue Tests (`test_aufbereitung.py`: Schlüsselwort-Erkennung inkl. gemischter Signale,
Verdrahtung in `erstelle_toptw_instanz`; `test_toptw.py`: harte Durchsetzung der Obergrenze in
`simuliere_route`, unverändertes Verhalten ohne Angabe). Komplette Suite: 207/207 grün.

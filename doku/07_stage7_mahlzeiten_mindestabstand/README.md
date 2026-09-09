# Station 7 — Mindestabstand zwischen Mahlzeiten in Optimierung 1

**Zeitraum:** 12.08.2026 (ENTSCHEIDUNGSLOG.md Phase 16)
**Code-Duplikat:** [`code_stand/`](code_stand/) — echte Kopien von `toptw.py`, `typen.py`,
`google_maps.py` zum Zeitpunkt VOR dieser Änderung.

## Auslöser

Nach dem POI-Fix aus [Station 6](../06_stage6_freitext_poi_suche/README.md): "Ich möchte nicht in
ein Restaurant um 13:13 und nach wieder in ein Restaurant um 14:07, wenn ich gerade gegessen hab,
muss ich ja nicht wieder essen." Zusätzlicher Wunsch: mehrere gewünschte Restaurantbesuche (z. B.
"jeden Abend essen gehen") sollen sich über mehrere Tage verteilen, nicht an einem Tag häufen.

## Verworfene Alternative

Der Nutzer schlug zunächst vor, die KI könnte jedem Restaurant im Dialog einen Tages-Wert (1/2/3)
zuweisen, der dann erzwingt, an welchem Tag es stattfindet. Das wurde bewusst **nicht** umgesetzt:
Die KI kennt zum Zeitpunkt der Dialogantwort weder Geografie noch Reisezeiten noch die tatsächliche
Tagesroute — nur der deterministische Optimierer hat diese Information. Eine von der KI vorab
zugewiesene Tagesnummer könnte objektiv falsch sein (z. B. ein für Tag 2 vorgesehenes Restaurant
liegt geografisch viel näher an Tag 3s Route). Das hätte außerdem die in CLAUDE.md ursprünglich als
"nicht verhandelbar" markierte Trennung verletzt: die KI führt den Dialog, baut aber nie selbst die
Route.

## Die Lösung: Mindestabstand als harte Nebenbedingung im Optimierer selbst

1. Jeder POI bekommt (automatisch, aus Googles eigenem zurückgelieferten Typ) eine grobe
   **Besuchsklasse** (`POI.besuchsklasse`, neues Feld): `"mahlzeit"` für Restaurant, `"kaffee"` für
   Café, `"bar"` für Bar. Alle anderen POIs bleiben unklassifiziert (`None`) und damit unbetroffen.
2. `TOPTWInstanz` bekommt eine neue Nebenbedingung `mindestabstand_je_klassenpaar`: ein Mindestabstand
   (Minuten) zwischen zwei Besuchen bestimmter Klassenpaare **am selben Tag**. `simuliere_route`
   prüft das genauso wie heute schon Zeitfenster/Tagesbudget — eine Route, die das verletzt, ist
   ungültig.
3. Konkrete, mit dem Nutzer abgestimmte Werte:
   - Zwei "mahlzeit"-Besuche (zwei Restaurants): **4 Stunden** Mindestabstand.
   - "kaffee" + "bar": **1 Stunde** (Startwert, keine konkrete Zahl vom Nutzer genannt).
   - "mahlzeit" + "kaffee": **kein** Mindestabstand — ausdrücklich erwünscht ("ein Kaffee darf
     natürlich auch nach dem Restaurant kommen, 30 Minuten später reicht").
   - Alle Selbst-Paare außer "mahlzeit" (z. B. zwei Cafés, zwei Bars): **kein** Mindestabstand
     ("wenn ich sage, ich geh in eine Bar oder einen Kaffee trinken, brauch ich das nicht
     separieren").
4. **Verteilungs-Effekt kommt automatisch mit**: `plane_gesamte_reise` entfernt bereits verplante
   POIs tageweise aus dem Kandidatenpool. Weil ein Tag mit 4h-Mindestabstand strukturell nur 1–2
   Mahlzeiten-Besuche zulässt, verteilen sich mehrere gewünschte Restaurantbesuche automatisch auf
   mehrere Tage — ohne dass irgendjemand explizit eine Tagesnummer zuweist.

## Dabei gefundener, vorbestehender Bug

Beim ersten Live-Test griff die neue Regel gar nicht — drei Restaurants standen weiterhin direkt
hintereinander. Ursache: `haupttyp = types[0]` (unverändert seit Phase 2) nahm blind den ERSTEN
Eintrag aus Googles `types`-Array. Live-Check zeigte: eine Restaurant-Suche liefert durchgehend
`types=['establishment', 'food', 'point_of_interest', 'restaurant', ...]` — alphabetisch sortiert,
NICHT nach Relevanz. `haupttyp` war dadurch praktisch nie `"restaurant"`/`"cafe"`/`"bar"`, wodurch
auch die schon länger bestehende Besuchsdauer-Schätzung und Tageszeit-Mindestwert-Logik
(`_BESUCHSDAUER_JE_TYP_MINUTEN`/`_MINDEST_TAGESZEIT_MINUTEN_JE_TYP`, seit Phase 2 bzw. 11) für
diese Typen nie wirklich griff — ein latenter, bis jetzt unbemerkter Fehler.

**Fix:** neue Funktion `_waehle_haupttyp` (`google_maps.py`) wählt aus `types` den ersten Eintrag,
der tatsächlich in einer unserer eigenen Typ-Tabellen vorkommt, statt blind das erste Element zu
nehmen.

## Live-Verifikation

3-Tage-Testfall (Innsbruck, Interessen Restaurants+Cafés+Bars+Klettern) über `pruefe_planung.py`:
vor dem `_waehle_haupttyp`-Fix drei Restaurants direkt hintereinander an einem Tag (10:02/11:03/
12:04), danach auf verschiedene Tage verteilt mit sinnvollem zeitlichem Abstand zu Café-Besuchen.

## Tests

5 neue Tests (`test_toptw.py`): Mindestabstand wird durchgesetzt (zwei Restaurants zu dicht),
ausreichender Abstand wird akzeptiert, Kaffee direkt nach Restaurant bleibt erlaubt, Kaffee+Bar zu
dicht wird abgelehnt, POIs ohne Besuchsklasse bleiben unbeschränkt. Komplette Suite: 183/183 grün.

## Bewusst nicht umgesetzt (siehe ENTSCHEIDUNGSLOG.md, Offene Punkte)

- Geografische Vor-Clusterung von POIs vor dem Tag-für-Tag-ILS-Lauf — eigenständiger, größerer
  Eingriff in den ILS-Kern, vom Nutzer als separates Thema zurückgestellt.
- Mehrere Unterkünfte je Reise (Etappen-/Hotelwechsel) — vom Nutzer explizit zurückgestellt.
- Café-Zeitfenster mit Obergrenze ("bevorzugt mittags") — aktuell nur eine Mindestzeit, keine echte
  Fensterung.

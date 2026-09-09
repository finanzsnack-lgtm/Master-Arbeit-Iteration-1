"""
Regelwerk-/Systemprompt-Text für die LLM-Agenten-Session (siehe CLAUDE.md,
Abschnitt "Dialogsteuerung", und src/fragekatalog/agent_tools.py).

`baue_regelwerk_text()` erzeugt den vollständigen Fragekatalog + die
Werkzeug-/Skip-Anleitung als Text, der bei der Session-Initialisierung
(chat.py::hauptablauf) einmalig in den System-Prompt eingebettet wird. Anders
als vor dem Architekturwechsel (11.08., siehe ENTSCHEIDUNGSLOG.md) steuert
das LLM den Gesprächsablauf jetzt TATSÄCHLICH selbst (welche Frage wann
gestellt/übersprungen wird) – der regelbasierte Layer bleibt nur noch für
das verantwortlich, was sich objektiv prüfen lässt (Typvalidierung,
Vollständigkeitsprüfung, die eigentliche Reiseplanung selbst), nicht mehr
für die Gesprächs-Reihenfolge.
"""
from __future__ import annotations

from src.fragekatalog.katalog import FRAGEKATALOG

_STUFEN_NAMEN = {
    0: "Meta",
    1: "Reisemotivation & Anlass",
    2: "Reisezeitraum & Planungshorizont",
    3: "Destination & Rahmenbedingungen",
    4: "Budget & finanzielle Constraints",
    5: "Verkehrsmittel & Mobilität",
    6: "Unterkunft & Komfortpräferenzen",
    7: "Aktivitäten, POI & Reisestil",
}


def _fragekatalog_uebersicht() -> str:
    zeilen = []
    stufe_aktuell = None
    for frage in FRAGEKATALOG:
        if frage.stufe != stufe_aktuell:
            stufe_aktuell = frage.stufe
            zeilen.append(f"\nStufe {frage.stufe} – {_STUFEN_NAMEN.get(frage.stufe, '?')}:")
        markierung = " [Typ C: Vorschlag+Zustimmung]" if frage.fragetyp.value == "C" else ""
        pflicht = "Pflichtfeld" if frage.pflichtfeld else "optional"
        zeilen.append(
            f"  {frage.id} (feld='{frage.feld}', Rückgabetyp={frage.rueckgabetyp.value}, {pflicht}): "
            f"{frage.botfrage}{markierung}"
        )
        if frage.kontext_hinweis:
            zeilen.append(f"      Hintergrund/Zweck: {frage.kontext_hinweis}")
    return "\n".join(zeilen)


_TOOL_ANLEITUNG = """\
=== WERKZEUGE UND ABLAUFSTEUERUNG (Architektur seit 11.08., siehe ENTSCHEIDUNGSLOG.md) ===

DU steuerst den Gesprächsablauf SELBST – es gibt keine feste Python-Reihenfolge mehr, die
dir Frage für Frage vorgibt. Dir stehen fünf Werkzeuge zur Verfügung:

  - speichere_feld(feld, wert, ...): speichert einen bestätigten Wert für EIN Feld aus dem Katalog
    unten. Rufe es auf, sobald du eine Antwort für sicher genug hältst, um sie festzuhalten.
    Ruf es auch erneut auf, wenn der Nutzer eine frühere Angabe revidiert – kein Sondermechanismus
    nötig, einfach den Wert neu speichern. Bei feld=aktivitaeten_interessen IMMER auch
    `aktivitaeten_mit_spezialrecherche` mitgeben (welche der genannten Aktivitäten über OpenStreet-
    Map/Overpass recherchiert werden sollen, siehe Katalog-Hintergrund zu F16 unten – Klettern,
    Wandern mit Schwierigkeitsgrad, Ski, Tauchen, Mountainbike u.ä.), sonst geht die Overpass-
    Recherche für die finale Planung verloren. `aktivitaeten_gewichtung`: gewichte genannte
    Interessen relativ zueinander, wenn der GESAMTE bisherige Gesprächskontext eine unterschiedliche
    Priorität erkennen lässt – nicht nur bei wörtlicher Erwähnung von "wichtig". Auch Betonung,
    Wiederholung, ein genannter Grund oder eine erkennbare Rangfolge im Gespräch zählen. Bei
    erkennbar gleichrangig/neutral genannten Interessen KEIN Gewicht setzen (Standard bleibt 1.0) –
    keine Präferenz erfinden, die der Nutzer nicht tatsächlich ausgedrückt hat.
  - hole_api_daten(feld, ...): holt ECHTE Daten für die Typ-C-Felder unterkunft_anforderungen,
    aktivitaeten_interessen, verkehrsmittel_praeferenz. Bei feld=aktivitaeten_interessen gib in
    `aktivitaeten_aktuell` IMMER die VOLLSTÄNDIGE Liste ALLER bisher genannten Interessen mit
    (nicht nur das zuletzt Genannte oder das mit Klärungsbedarf, z.B. auch "Restaurants"/"Cafés"/
    "Bars", wenn der Nutzer das nebenbei erwähnt hat) – ein vergessenes Interesse wird sonst
    schlicht NICHT gesucht, ohne dass dir ein Fehler angezeigt wird. Bei
    feld=unterkunft_anforderungen gib in `aktueller_wert` die aktuelle Antwort mit – WICHTIG: hier
    gilt eine ANDERE Regel als sonst bei Typ-C-Feldern, siehe unten.
  - fehlende_pflichtfelder(): zeigt, welche Pflichtfelder noch offen sind.
  - plane_reise_und_abschliessen(): schließt die Planung ab (nur möglich, wenn alle Pflichtfelder
    gesetzt sind – sonst schlägt es fehl und nennt dir, was noch fehlt).
  - breche_planung_ab(grund): bei erkennbarem Abbruchwunsch des Nutzers.

UNTERKUNFT (F15) MIT STILLEM API-ABRUF, OHNE VORSCHAU (siehe Projektkonversation, Station 10/12 –
"doch es soll die Hotel API abrufen, das ist falsch, es soll nur nicht nochmal im Chat erwähnt
werden"): du rufst hole_api_daten für dieses Feld GENAUSO auf wie bei jedem anderen Typ-C-Feld
(Grundprinzip 1 – nie ohne echten Datenabgleich speichern). ABER anders als sonst bei Typ-C-Feldern
nennst du dem Nutzer aus dem Ergebnis KEINE konkreten Hotelnamen/Kandidaten und holst KEINE
Zustimmung zu einem bestimmten Hotel ein. Nutze das Tool-Ergebnis nur intern als Bestätigung, dass
für die genannte Anforderung überhaupt etwas Passendes existiert, und speichere danach direkt per
speichere_feld die reine Anforderung als Text – kein Vorschlag+Zustimmung-Dialog wie sonst bei
Typ-C-Feldern. Liefert die Suche wirklich GAR NICHTS (z.B. weil das Ziel unbekannt/nicht auffindbar
ist), sag das dem Nutzer ehrlich, statt ein Hotel zu erfinden oder stillschweigend weiterzumachen.
Die tatsächlich gewählte Unterkunft entsteht ohnehin erst später automatisch bei der finalen
Planung (pipeline.py::_plane_bestes_depot, testet mehrere echte Kandidaten per vollständiger
Optimierung durch) und erscheint erst im fertigen Reiseplan/der Mail, NICHT im Chat.

AKTIVITÄTEN/POIs (F16) WEITERHIN MIT VOLLER VORSCHAU (Station 11, Rückmeldung nach Live-Test:
"macht die POIs einfach genauso, wie sie vorher waren, das war sehr sehr gut"): hier gilt die
normale Typ-C-Regel unten (erst Präferenz erfragen, dann hole_api_daten, dann Vorschlag +
Zustimmung, dann erst speichern) – NICHT wie bei F15 vereinfachen, der Nutzer sieht die
Vorschläge im Gespräch und stimmt ihnen zu.

WELCHE FRAGE WANN STELLEN – die vom Product Owner gewünschte Regel: Stelle grundsätzlich JEDE
Frage aus dem Katalog. Überspringe eine Frage NUR, wenn du aus dem bisherigen Gespräch oder einer
bereits getroffenen Planungsentscheidung SICHER weißt, dass sie bereits beantwortet oder
gegenstandslos ist (z.B. Sicherheitsfrage bei einem konkreten, unstrittig sicheren Reiseziel).
Bist du dir nicht sicher, frage IMMER – im Zweifel lieber eine Frage zu viel als eine zu wenig.
Pflichtfelder MÜSSEN am Ende ausnahmslos gesetzt sein, sonst schlägt der Abschluss fehl.

IMMER NUR EINE FRAGE PRO NACHRICHT: Stelle GENAU EINE Frage, warte die Antwort des Nutzers ab, dann erst die nächste –
egal wie kurz oder thematisch verwandt mehrere offene Fragen sind. NIEMALS mehrere eigenständige
Katalogfragen in einer Nachricht bündeln oder nummerieren (z.B. Name UND Wohnort UND
Reisebegleitung zusammen). Eine kurze, erkennbar zusammengehörige Zusatzangabe INNERHALB einer
einzigen Frage ist in Ordnung (z.B. "wie alt sind die Kinder ungefähr?" als Ergänzung zur Frage
nach der Reisebegleitung, wenn das für später relevant ist) – das ist EIN Gedanke, keine zweite
Frage.

Bei Typ-C-Feldern (siehe Katalog): erst eine erste, noch unbestätigte Präferenz vom Nutzer
erfragen, dann hole_api_daten aufrufen, dann einen Vorschlag AUSSCHLIESSLICH auf Basis der
zurückgegebenen echten Daten formulieren, dann Zustimmung einholen – erst NACH Zustimmung
speichere_feld aufrufen. Bei Ablehnung/Verfeinerungswunsch hole_api_daten erneut mit angepassten
Angaben aufrufen statt selbst neue Daten zu erfinden.

WICHTIG: Erfinde NIE Fakten (Orte, Preise, Öffnungszeiten, POIs, Verfügbarkeiten) – nenne bei
Typ-C-Feldern AUSSCHLIESSLICH, was dir hole_api_daten tatsächlich zurückgegeben hat.
"""


def baue_regelwerk_text(anfangskontext: str | None = None) -> str:
    """Baut den vollständigen Regelwerk-/Systemprompt-Text (Werkzeug-/Skip-Anleitung + kompletter
    Fragekatalog) für die Initialisierung der Agenten-Session (siehe chat.py::hauptablauf)."""
    teile = [
        "=== REGELWERK (Prozessmodell Modell_1_Reisebot_Prototyp.drawio) ===",
        "",
        _TOOL_ANLEITUNG,
        "Vollständiger Fragekatalog (Feldname, erwarteter Rückgabetyp für speichere_feld, "
        "Pflichtstatus, Hintergrund):",
        _fragekatalog_uebersicht(),
    ]
    if anfangskontext:
        teile.extend([
            "",
            "=== EINSTIEG DES NUTZERS (Knoten a1, vor Beginn des Fragekatalogs) ===",
            anfangskontext,
        ])
    return "\n".join(teile)


def api_abruf_felder() -> list[str]:
    """Feldnamen aller Typ-C-Fragen (für die Dispatch-Tabelle in vorschlaege.py)."""
    return [frage.feld for frage in FRAGEKATALOG if frage.api_abruf_noetig]

"""
Datenmodell für den befüllten Fragekatalog (siehe CLAUDE.md, Abschnitt
"Fragekatalog"). Jede Instanz von `ReiseAnfrage` entspricht dem
strukturierten JSON, das der LLM-Agent über `speichere_feld` (siehe
src/fragekatalog/agent_tools.py) Feld für Feld befüllt und das am Ende an
die regelbasierte Anwendung (pipeline.py) übergeben wird.

Die Feldnamen und Rückgabetypen stammen aus
`Fortschritte/Fragekatalog/100 Fragen.docx` (vom Product Owner als
maßgebliche Fragenbasis bestätigt). Siehe `katalog.py` für die konkreten
Frageformulierungen, die Stufen-Zuordnung und Anmerkungen zu Stellen, an
denen das Rohmaterial unklar bzw. unvollständig war.

Ergänzung `wohnort` (F08): NICHT aus dem Rohmaterial, sondern nachträglich
ergänzt (siehe Projektkonversation) – Optimierung 2 (An-/Abreise) benötigt
zwingend einen Startort, den der ursprüngliche Fragekatalog nirgends erfasst
hatte. Transparent als Ergänzung markiert statt stillschweigend so getan,
als stünde sie schon immer im Rohmaterial.

Sonderfall `reiseerlebnis_beschreibung`: KEINE eigene Katalogfrage mehr
(ursprünglich F03, wieder entfernt – überschnitt sich mit dem freien
Gesprächseinstieg a1 "Reisewunsch äußern" in chat.py). Das Feld
bleibt im Schema, wird aber direkt aus der a1-Antwort befüllt, nicht über
`speichere_feld`.

Ergänzung `altersgerechte_beduerfnisse` (F10): NICHT aus dem Rohmaterial,
sondern nachträglich ergänzt (siehe Projektkonversation) – deckt das vom
Betreuer empfohlene Kernfeld "Altersgerechter & inklusiver Tourismus" ab
(Kategorien.pdf, Feld 02), das im ursprünglichen Fragekatalog nur über
gesundheitliche Einschränkungen (F09) gestreift wurde.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from src.api.typen import POI


class Fragetyp(str, Enum):
    """Die drei Fragetypen aus dem Prozessmodell (Modell_1_Reisebot_Prototyp.drawio)."""

    KONTEXT = "A"  # nur Gesprächskontext, kein hart validiertes Feld
    WERT = "B"  # Wert wird extrahiert, validiert und im JSON gesetzt
    DIALOG = "C"  # API-gestützte Vorschläge, Schleife bis Zustimmung


class Rueckgabetyp(str, Enum):
    """Erwarteter Datentyp der Antwort, wie im Fragekatalog vermerkt."""

    STRING = "string"
    ARRAY = "array"
    ZAHL = "num"
    BOOL = "bool"


@dataclass
class ReiseAnfrage:
    """Strukturierte Ablage aller im Dialog erhobenen Angaben (19 Katalogfragen, siehe katalog.py: F01–F20 ohne F18 (in F09 integriert, siehe dort), plus `reiseerlebnis_beschreibung` aus a1)."""

    # -- Meta ---------------------------------------------------------------
    name: str | None = None
    email: str | None = None

    # -- Stufe 1: Reisemotivation & Anlass -----------------------------------
    reiseerlebnis_beschreibung: str | None = None  # aus a1 "Reisewunsch äußern", keine eigene Katalogfrage (siehe Moduldoku)
    reisebegleitung: list[str] = field(default_factory=list)
    reiseleitung_gewuenscht: bool | None = None
    # Vom LLM gesetzt (Tool-Argument bei speichere_feld, siehe agent_tools.py) – NUR bei einer
    # EXPLIZITEN Mehrtages-Aussage ("ich möchte mehrere Tage Touren machen"), sonst None (=
    # Standardfall: EIN reservierter Tour-Tag, siehe pipeline.py `plane_reise`/reiseplan.py
    # `_reservierte_sondertage`). Rückfrage-Ergebnis: bewusst NICHT proaktiv erfragt ("ganz einfach
    # halten") – ohne ausdrückliche Mehrtages-Aussage bleibt es immer bei einer Eintagestour.
    tour_tage_anzahl: int | None = None
    flexibilitaet_praeferenz: str | None = None
    # Vom LLM gesetzt (Tool-Argument bei speichere_feld, siehe agent_tools.py) – 1 (ganz
    # durchgeplant/eng) bis 3 (extrem flexibel), aus dem GESAMTEN Gesprächsverlauf abgeleitet, NICHT
    # durch direktes Abfragen einer Zahl (Rückfrage-Ergebnis: "der soll jetzt nicht genau fragen,
    # wie flexibel wollen sie sein, sondern die Konversation führen und daraus schließen"). ERSETZT
    # die frühere Schlüsselwort-Zählung über `flexibilitaet_praeferenz` (bewusst analog zu
    # `mobilitaetseinschraenkung_stufe` – überschreibbar, keine feste Einmalzuweisung). None = kein
    # Signal erkannt. Skala von ursprünglich 1-5 auf 1-3 verkleinert (Product-Owner-Entscheidung,
    # 24.08.2026, im Zuge eines Kosten-Vorfalls) – anders als vorher hat jetzt AUCH Stufe 1 einen
    # festen POI-pro-Tag-Deckel (3), nicht mehr "unbegrenzt". Steuert in Optimierung 1 sowohl den
    # POI-Anzahl-Deckel pro Tag als auch eine Pufferpause (siehe aufbereitung.py
    # `max_pois_pro_tag_fuer_flexibilitaet`/`pause_parameter_fuer_flexibilitaet`).
    flexibilitaet_stufe: int | None = None

    # -- Stufe 2: Reisezeitraum & Planungshorizont ---------------------------
    reisezeitraum_rohtext: str | None = None
    # Von der LLM beim Speichern von F07 interpretiert (Tool-Argumente bei speichere_feld, siehe
    # agent_tools.py) – ISO-Format "YYYY-JJ-TT". PRIMÄRE Quelle für die Reisedauer (siehe
    # aufbereitung.py `schaetze_reisedauer_tage`): die LLM klärt Mehrdeutigkeiten (z.B. fehlendes
    # Jahr) im Dialog, die eigentliche Tagesanzahl wird aber weiterhin rein deterministisch aus
    # diesen zwei Werten berechnet, nicht von der LLM selbst gezählt (Grundprinzip 3 – Rückfrage-
    # Ergebnis nach zwei Live-Bugs im reinen Freitext-Regex-Parser: "die LLM bringt es zu einem
    # Wert, und ich in meinem Algorithmus gucke, wie weit diese Daten auseinanderliegen"). Bleiben
    # None, wenn die LLM aus dem Gespräch kein eindeutiges Datum ableiten konnte – dann greift
    # weiterhin der alte Freitext-Parser als Fallback (u.a. für dialogfreie Testfälle ohne
    # LLM-Session, siehe pruefe_planung.py).
    reise_start_datum: str | None = None
    reise_end_datum: str | None = None

    # -- Stufe 3: Destination & Rahmenbedingungen ----------------------------
    zielregionen: list[str] = field(default_factory=list)
    wohnort: str | None = None  # Ergänzung, siehe Moduldoku oben (F08)
    gesundheitliche_einschraenkungen: str | None = None
    altersgerechte_beduerfnisse: str | None = None  # Ergänzung, siehe Moduldoku oben (F10)
    sicherheitsbeduerfnis: str | None = None
    # Vom LLM gesetzt (Tool-Argument bei speichere_feld, siehe agent_tools.py), wenn es aus dem
    # GESAMTEN Gesprächskontext eine echte Sicherheitssorge erkennt – bewusst kein Schlüsselwort-
    # Abgleich auf `sicherheitsbeduerfnis`, da eine solche Sorge sich in ganz unterschiedlichen
    # Formulierungen äußern kann. Steuert den Sicherheitshinweis im Reiseplan (siehe pipeline.py).
    sicherheit_bedenklich: bool = False
    # Vom LLM gesetzt (Tool-Argument bei speichere_feld, siehe agent_tools.py), wenn es aus dem
    # GESAMTEN Gesprächskontext eine Barrierefreiheits-/Mobilitätseinschränkung erkennt – ERSETZT
    # die frühere Schlüsselwort-Suche über F09/F10/F15 (siehe ENTSCHEIDUNGSLOG.md: die Suche konnte
    # unbemerkt leerlaufen, wenn die Antwort sinngemäß, aber nicht wörtlich mit einem der festen
    # Wörter formuliert war, z.B. "möchten es entspannt angehen, nicht hetzen"). NICHT auf ein
    # einzelnes Feld beschränkt (kann bei JEDEM speichere_feld-Aufruf gesetzt werden). Drei Stufen
    # statt eines einzelnen Bools (Rückfrage-Ergebnis: "jemand, der einfach nur ein bisschen
    # langsamer geht, [und] jemand, der im Rollstuhl ist, das sind Unterschiede") – None = keine
    # Einschränkung genannt:
    #   "leicht"  (z.B. altersbedingt langsameres Tempo): JEDER Ort bleibt nutzbar, KEIN
    #             POI-/Unterkunft-Ausschluss – nur Tempo-/Pausen-/Nähe-Anpassungen (siehe
    #             aufbereitung.py).
    #   "mittel"  (z.B. Krücken/Gehhilfe): schließt nur EXPLIZIT als nicht barrierefrei bestätigte
    #             Orte aus, unbekannte bleiben – ehrlicher Näherungswert, denn es gibt KEINE echte
    #             Steigungs-/Stufen-Datenquelle für einzelne Orte oder Fußwege (weder Places noch
    #             Directions noch eine angebundene Elevation-API); das einzige strukturierte
    #             Signal, das wir haben, ist `wheelchair_accessible_entrance` (Google Places).
    #   "stark"   (z.B. Rollstuhl): schließt alles aus, was NICHT eindeutig bestätigt barrierefrei
    #             ist – ein unbekannter Status zählt hier ebenfalls als Ausschlussgrund.
    # Siehe vertraeglichkeit.py für die konkrete Filterlogik je Stufe.
    mobilitaetseinschraenkung_stufe: str | None = None

    # -- Stufe 4: Budget & finanzielle Constraints ---------------------------
    budget_gesamt: float | None = None

    # -- Stufe 5: Verkehrsmittel & Mobilität ----------------------------------
    verkehrsmittel_praeferenz: list[str] = field(default_factory=list)
    # Bewusst Freitext statt fester Kategorie (z.B. "nur zu Fuß"/"nur Auto"):
    # im Praxistest antworten Nutzer hier oft bedingt/flexibel ("kommt drauf
    # an, je nachdem wie die Sachen erreichbar sind"). Das ist eine gültige,
    # vollständige Antwort (Fragetyp.WERT akzeptiert jeden String) und soll
    # NICHT zu einer festen Wahl gezwungen werden. Beeinflusst POI-Suchradius
    # UND die POI-zu-POI-Geschwindigkeit in Optimierung 1 (siehe aufbereitung.py
    # `parameter_fuer_lokalen_transport`) – noch als EIN globaler Modus für die
    # ganze Reise, nicht pro Etappe/POI unterschiedlich (siehe CLAUDE.md,
    # "Zentrale Anpassung": Luftlinien-Schätzung statt echter Distance-Matrix-
    # Reisezeiten zwischen den einzelnen POIs).
    lokaler_transport_praeferenz: str | None = None
    # Ergänzung (F20, siehe katalog.py) – NICHT aus dem Rohmaterial: grobe Start-/Enduhrzeit für
    # einen normalen Reisetag als Freitext (z.B. "ab 9 bis 21 Uhr"), roh zur Aufbewahrung/Anzeige
    # im Reiseplan-Kontext.
    tagesstart_praeferenz: str | None = None
    # Vom LLM aus `tagesstart_praeferenz` interpretiert (Tool-Argumente bei speichere_feld, siehe
    # agent_tools.py) – Minuten seit Mitternacht. Das LLM versteht Freitext zuverlässiger als ein
    # Regex-Parser ("ab neun bis abends um neun", "eher früh los, nicht so spät zurück" usw.) und
    # kann bei genuin vager Angabe ("eher früh") selbst eine vernünftige Zeit ableiten oder die
    # Felder unverändert lassen, wenn wirklich nichts Nutzbares gesagt wurde. Ermöglicht echte
    # Uhrzeiten in der Ausgabe (ab Tag 2, siehe reiseplan.py) UND bestimmt bei Angabe direkt das
    # tatsächliche Tagesbudget für Optimierung 1 (siehe pipeline.py) statt eines festen
    # Konfigurations-Defaults – ohne Angabe bleibt es bei diesem Default.
    tagesstart_minuten: int | None = None
    tagesende_minuten: int | None = None

    # -- Stufe 6: Unterkunft & Komfortpräferenzen -----------------------------
    unterkunft_anforderungen: str | None = None
    # Die im Dialog (F15) gefundene und dem Nutzer bestätigte Unterkunft (siehe
    # agent_tools.py::speichere_feld) – Optimierung 1 (pipeline.py) verwendet
    # GENAU diese Koordinaten als Depot, statt ein zweites Mal unabhängig zu
    # suchen, damit die im Chat bestätigte Unterkunft auch tatsächlich die
    # geplante ist.
    unterkunft_name: str | None = None
    unterkunft_koordinaten: tuple[float, float] | None = None
    unterkunft_place_id: str | None = None
    # Places-Foto-Referenz derselben Unterkunft (siehe api/typen.py `Unterkunft.foto_referenz`) –
    # für die Bild-Karte im fertigen Reiseplan der Web-UI (webapp.py). None im Mock-Modus oder wenn
    # Places kein Foto zu dieser Unterkunft hat.
    unterkunft_foto_referenz: str | None = None
    # Places-`price_level` (0-4) derselben Unterkunft (siehe api/typen.py `Unterkunft.preisniveau`)
    # – Grundlage für die informative Kostenschätzung im Reiseplan (siehe
    # src/optimierung/kostenschaetzung.py) und die Preisangabe in der Hotel-Vorschau-Karte im Chat.
    unterkunft_preisniveau: int | None = None

    # -- Stufe 7: Aktivitäten, POI & Reisestil ----------------------------------
    aktivitaeten_interessen: list[str] = field(default_factory=list)
    # Teilmenge von `aktivitaeten_interessen`, die das LLM bei der Antwort-
    # analyse (b3, siehe llm_interpreter.py `spezialrecherche_aktivitaeten`)
    # als fachlich recherchebedürftig eingestuft hat (z.B. Klettern, Wandern
    # mit Schwierigkeitsgrad) – löst zusätzlich zu Google Places eine
    # Overpass-Abfrage aus (siehe src/datenaufbereitung/poi_sammlung.py).
    # NICHT vom LLM erzwungen: bleibt leer, wenn keine genannte Aktivität
    # das aus Sicht des LLM braucht (siehe Projektkonversation).
    aktivitaeten_mit_spezialrecherche: list[str] = field(default_factory=list)
    # Relative Wichtigkeit einzelner Einträge aus `aktivitaeten_interessen`
    # (Schlüssel = exakter Präferenz-String, Wert = Gewicht, neutral/fehlend
    # = 1.0). Kommt aus einer vergleichenden Rückfrage des LLM bei zu vielen
    # Treffern (gw3, siehe llm_interpreter.py `werte_zustimmung_aus`
    # `kategorie_gewichtung`) – NICHT vom Nutzer aktiv erfragt, nur wenn die
    # Situation es nahelegt (siehe Projektkonversation: "hast du mehr Lust
    # auf X oder Y"). Fließt in aufbereitung.py::waehle_top_pois ein.
    aktivitaeten_gewichtung: dict[str, float] = field(default_factory=dict)
    lernaktivitaeten_interesse: str | None = None
    # KEINE eigene Katalogfrage mehr (früher F18, Nutzerwunsch, siehe ENTSCHEIDUNGSLOG.md) – wird
    # jetzt vom LLM als Tool-Argument bei speichere_feld(feld="gesundheitliche_einschraenkungen")
    # gesetzt (siehe agent_tools.py/katalog.py F09), analog zu mobilitaetseinschraenkung_stufe: NUR
    # wenn der Nutzer bei F09 tatsächlich eine Unverträglichkeit/Allergie erwähnt (dann gezielt
    # nachgefragt, welche genau), sonst leer. Fließt weiterhin unverändert in die Restaurant-Suche
    # (google_maps.py) und die Verträglichkeitsprüfung (vertraeglichkeit.py) ein.
    ernaehrung_einschraenkungen: list[str] = field(default_factory=list)
    lokaler_kontakt_wichtig: bool | None = None
    # Der von der KI gefundene und dem Nutzer bestätigte Fahrzeug-Verleih (F14,
    # siehe agent_tools.py::speichere_feld) – None, solange kein Leihwunsch
    # erkannt wurde ODER die Suche noch nicht gelaufen ist (z.B. weil die
    # Unterkunft zum Zeitpunkt der F14-Antwort noch nicht bekannt war).
    lokaler_verleih_gewaehlt: POI | None = None

    def als_dict(self) -> dict[str, Any]:
        """Serialisiert die Anfrage in ein reines, JSON-taugliches dict."""
        return asdict(self)

    def primaeres_reiseziel(self) -> str | None:
        """
        Erster genannter Zielname aus `zielregionen`, für API-Anfragen, die
        EINEN Ortsnamen brauchen (Places/Geocoding/Directions – siehe
        src/pipeline.py und src/fragekatalog/vorschlaege.py). Zentral an
        einer Stelle definiert, weil an genau dieser Umwandlung schon einmal
        ein Bug entstand (hartcodierter Platzhalterstring statt echter
        Nutzerangabe, siehe Projektkonversation) – soll nicht ein zweites
        Mal passieren.
        """
        return self.zielregionen[0] if self.zielregionen else None

    def barrierefreiheit_oder_eingeschraenkt(self) -> bool:
        """
        Grobe Ja/Nein-Einschätzung, ob die Reise auf Barrierefreiheit/eingeschränkte Mobilität
        überhaupt Rücksicht nehmen muss (JEDE Stufe von `mobilitaetseinschraenkung_stufe`, siehe
        Feld oben, löst mindestens die Tempo-/Pausen-/Nähe-Anpassungen aus, siehe aufbereitung.py)
        – für die tatsächliche, nach Stufe gestaffelte POI-/Unterkunft-Filterstrenge siehe
        `mobilitaetseinschraenkung_stufe` direkt (vertraeglichkeit.py).

        `mobilitaetseinschraenkung_stufe` ist ein vom LLM aus dem GESAMTEN Gesprächskontext
        gesetztes Urteil (Tool-Argument bei speichere_feld), analog zu `sicherheit_bedenklich`
        (CLAUDE.md Grundprinzip 1: Ablaufsteuerung/Beurteilung darf beim LLM liegen) – ERSETZT die
        frühere, rein schlüsselwort-basierte Prüfung über F09/F10/F15-Texte (siehe
        ENTSCHEIDUNGSLOG.md). Die eigentlichen, daraus folgenden Anpassungen bleiben unverändert
        vollständig deterministisch (CLAUDE.md Grundprinzip 3), nur die Erkennung selbst liegt
        jetzt beim LLM statt bei einer festen Wortliste.
        """
        return self.mobilitaetseinschraenkung_stufe is not None

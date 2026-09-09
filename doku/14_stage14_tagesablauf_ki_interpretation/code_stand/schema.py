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
    """Strukturierte Ablage aller im Dialog erhobenen Angaben (19 Katalogfragen, siehe katalog.py: F01–F19, plus `reiseerlebnis_beschreibung` aus a1)."""

    # -- Meta ---------------------------------------------------------------
    name: str | None = None
    email: str | None = None

    # -- Stufe 1: Reisemotivation & Anlass -----------------------------------
    reiseerlebnis_beschreibung: str | None = None  # aus a1 "Reisewunsch äußern", keine eigene Katalogfrage (siehe Moduldoku)
    reisebegleitung: list[str] = field(default_factory=list)
    reiseleitung_gewuenscht: bool | None = None
    flexibilitaet_praeferenz: str | None = None

    # -- Stufe 2: Reisezeitraum & Planungshorizont ---------------------------
    reisezeitraum_rohtext: str | None = None

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
    # Ergänzung (F20, siehe katalog.py) – NICHT aus dem Rohmaterial: grobe
    # Start-/Enduhrzeit für einen normalen Reisetag als Freitext (z.B. "ab 9
    # bis 21 Uhr"). Ermöglicht echte Uhrzeiten in der Ausgabe (ab Tag 2, siehe
    # reiseplan.py) UND kategorieabhängige Tageszeitfenster in Optimierung 1
    # (siehe aufbereitung.py `parameter_fuer_tagesablauf`/
    # `wende_tageszeitfenster_an`) – ohne Angabe bleibt beides bei den
    # bisherigen, vorsichtigen Standardannahmen.
    tagesstart_praeferenz: str | None = None

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
        Einheitliche Einschätzung, ob die Reise auf Barrierefreiheit/eingeschränkte Mobilität
        Rücksicht nehmen muss – vereint die frühere Unterscheidung zwischen "Barrierefreiheit
        wichtig" (harter Ausschluss nicht-barrierefreier Orte/Unterkünfte, siehe
        vertraeglichkeit.py) und "eingeschränkte Gehfähigkeit" (langsamere Gehzeiten, Pausen,
        Nähe-Gewichtung, siehe aufbereitung.py) zu EINER Einschätzung: beide Konsequenzen treten
        immer gemeinsam auf, sobald einer der Texte (F09 gesundheitliche_einschraenkungen, F10
        altersgerechte_beduerfnisse, F15 unterkunft_anforderungen) ein passendes Schlüsselwort
        enthält. Bewusst NUR Schlüsselwort-basiert, kein LLM-Aufruf außerhalb der Dialogschicht
        (CLAUDE.md Grundprinzip 3).
        """
        schluesselwoerter = (
            "barrierefrei", "rollstuhl", "gehbehind", "rollator", "mobilitätseinschränkung",
            "schwierigkeiten zu gehen", "schwierigkeiten beim gehen", "gehschwierigkeit",
            "schwer zu laufen", "schwer laufen", "eingeschränkt gehfähig",
            "kann nicht lange gehen", "kann nicht lange laufen",
        )
        texte = (self.gesundheitliche_einschraenkungen, self.altersgerechte_beduerfnisse, self.unterkunft_anforderungen)
        return any(text and any(wort in text.lower() for wort in schluesselwoerter) for text in texte)

"""
Konsolidierter Fragekatalog des Reisebot-Prototyps.

Quelle: `Fortschritte/Fragekatalog/100 Fragen.docx` (vom Product Owner als
maßgebliche Fragenbasis bestätigt). Die Reihenfolge folgt dem Stufenmodell
aus `Fortschritte/Fragekatalog/Kategorien.pdf` (7 sequenzielle
Entscheidungsstufen nach Choi et al. 2012 / Gavalas et al. 2014); die
Cluster-Zuordnung (K1, K2, K3, K4, K5, K6) übernimmt die Kategorien aus dem
Kodierleitfaden. K2 (Nachhaltigkeit) ist laut Kodierleitfaden ein
Querschnittsprinzip und wird nicht als eigene Stufe geführt, taucht aber bei
F18 inhaltlich noch auf (das Rohmaterial ordnete diese Frage K2 zu).

Fünf Anmerkungen zum Rohmaterial, transparent dokumentiert statt still-
schweigend "repariert":
- F06 (`reisezeitraum_rohtext`) ist im Rohdokument als "Return: Date"
  vermerkt, fragt inhaltlich aber nach Dauer UND Zeitraum zugleich. Hier
  daher als Freitext (String) modelliert; die Umrechnung in eine konkrete
  Tagesanzahl übernimmt die Datenaufbereitung (siehe
  `src/datenaufbereitung/aufbereitung.py::schaetze_reisedauer_tage`).
- Für F11 (`sicherheitsbeduerfnis`) und F14 (`lokaler_transport_praeferenz`)
  war im Rohdokument kein Rückgabetyp vermerkt; hier pragmatisch als String
  angenommen.
- F08 (`wohnort`) stammt NICHT aus dem Rohmaterial, sondern wurde nachträglich
  ergänzt: Optimierung 2 (An-/Abreise) braucht zwingend einen Startort, den
  der ursprüngliche Fragekatalog nirgends erfasst hatte (siehe
  Projektkonversation; sichtbar geworden beim ersten Live-Test gegen die
  echte Google-Maps-API).
- Die ursprüngliche Frage "Welche Art von Reiseerlebnis streben Sie an?"
  (`reiseerlebnis_beschreibung`) wurde WIEDER ENTFERNT: sie überschnitt sich
  inhaltlich mit dem freien Einstieg a1 "Reisewunsch äußern" (chat.py) – im
  Praxistest musste der Nutzer dieselbe Antwort zweimal geben. Das Feld
  bleibt im Schema (schema.py) erhalten, wird aber jetzt direkt aus der
  a1-Antwort befüllt statt erneut per Katalogfrage erhoben (siehe chat.py::hauptablauf).
- F10 (`altersgerechte_beduerfnisse`) stammt ebenfalls NICHT aus dem
  Rohmaterial, sondern wurde nachträglich ergänzt (siehe Projektkonversation).
  Grund: "Altersgerechter & inklusiver Tourismus" ist eines der beiden vom
  Betreuer empfohlenen Kernfelder (siehe Fortschritte/Fragekatalog/
  Kategorien.pdf, Feld 02) – der ursprüngliche Fragekatalog deckte davon nur
  gesundheitliche Einschränkungen (F09) ab, nicht aber altersbedingte
  Bedürfnisse wie Gehstrecken/Ruhephasen/Barrierefreiheit unabhängig von einer
  medizinischen Einschränkung. Direkt nach F09 platziert, da beide Fragen
  "besondere Bedürfnisse" für dieselbe Stufe (3) erheben.

Bei Rückfragen zu einzelnen Fragen/Feldern: bitte beim Product Owner
nachfragen, bevor an dieser Datei größere Änderungen vorgenommen werden.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.fragekatalog.schema import Fragetyp, Rueckgabetyp


@dataclass(frozen=True)
class FrageDefinition:
    """Eine Frage des Katalogs samt Steuerinformationen für den LLM-Agenten (siehe agent_tools.py)."""

    id: str
    stufe: int
    cluster: str
    feld: str  # Feldname in ReiseAnfrage (schema.py)
    fragetyp: Fragetyp
    rueckgabetyp: Rueckgabetyp
    botfrage: str  # Formulierung, die dem Nutzer gestellt wird
    kontext_hinweis: str | None = None  # Begründung/Zusatzinfo aus dem Rohmaterial, für die LLM-Formulierung
    pflichtfeld: bool = True
    api_abruf_noetig: bool = False  # löst im Prozessmodell das Gateway "API-Abruf nötig?" aus
    # Nur für ausgewählte optionale (pflichtfeld=False) Fragen gesetzt (siehe
    # Projektkonversation): erlaubt dem LLM, die Frage
    # ganz zu überspringen, wenn sie angesichts der bisherigen Angaben
    # offensichtlich keinen Mehrwert hätte (siehe regelwerk.py
    # `_TOOL_ANLEITUNG`) – z.B. eine Sicherheitsfrage bei einem konkreten,
    # allgemein bekannten sicheren Reiseziel wie "Innsbruck", aber NICHT bei
    # einem breiten, unklaren Ziel wie "Mexiko" (Sicherheitslage variiert je
    # nach Region stark). KEIN Grundprinzip-1-Verstoß: es wird kein Fakt
    # erfunden, nur die Relevanz einer bereits vorgegebenen Frage beurteilt.
    ueberspringbar: bool = False


FRAGEKATALOG: list[FrageDefinition] = [
    FrageDefinition(
        id="F01", stufe=0, cluster="Meta", feld="name",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie lautet Ihr Name?",
        kontext_hinweis="Wird für die persönliche Ansprache und den Versand des Reisevorschlags benötigt.",
    ),
    FrageDefinition(
        id="F02", stufe=0, cluster="Meta", feld="email",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Und wie lautet Ihre E-Mail-Adresse?",
        kontext_hinweis="An diese Adresse wird am Ende der Reisevorschlag gesendet.",
    ),
    FrageDefinition(
        id="F03", stufe=1, cluster="K1", feld="reisebegleitung",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.ARRAY,
        botfrage="Mit wem möchten Sie reisen?",
        kontext_hinweis="Erklären Sie, warum Sie sich für diese Art der Reise entschieden haben.",
    ),
    FrageDefinition(
        id="F04", stufe=1, cluster="K1", feld="reiseleitung_gewuenscht",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.BOOL,
        botfrage="Möchten Sie einen Reiseleiter oder eine Reiseleitung vor Ort haben?",
        kontext_hinweis="Erklären Sie, warum Sie eine Reiseleitung bevorzugen oder lieber auf eigene Faust erkunden möchten.",
    ),
    FrageDefinition(
        id="F05", stufe=1, cluster="K1", feld="flexibilitaet_praeferenz",
        fragetyp=Fragetyp.KONTEXT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie wichtig ist Ihnen die Flexibilität in Ihrem Reiseplan?",
        kontext_hinweis="Erklären Sie, warum Ihnen Flexibilität wichtig ist oder warum Sie eine strukturierte Reiseroute bevorzugen.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F06", stufe=2, cluster="K1", feld="reisezeitraum_rohtext",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie lange möchten Sie verreisen? Gibt es einen bestimmten Reisezeitraum, den Sie bevorzugen?",
        kontext_hinweis="Geben Sie Ihren bevorzugten Reisezeitraum an und erklären Sie, warum dieser Zeitraum ideal für Sie ist.",
    ),
    FrageDefinition(
        id="F07", stufe=3, cluster="K1", feld="zielregionen",
        # Ursprünglich als Fragetyp.DIALOG (Typ C) markiert, weil Kategorien.pdf
        # optionale Ziel-EMPFEHLUNGEN vorsieht ("...oder wünschen Sie
        # Empfehlungen?"). Der Mock-API-Layer (src/api/google_maps.py) hat
        # aber keine Methode für Zielregion-Empfehlungen (nur suche_pois,
        # suche_unterkuenfte, reisealternativen, geocode – alle setzen ein
        # bereits gewähltes Ziel voraus). Um KEINE Vorschläge ohne echte
        # Datengrundlage zu erfinden (CLAUDE.md, Grundprinzip 1), bleibt
        # diese Frage bis zur echten Places-Anbindung Fragetyp.WERT.
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.ARRAY,
        botfrage="Welche Länder oder Regionen möchten Sie bereisen?",
        kontext_hinweis="Beschreiben Sie Ihre Interessen in Bezug auf verschiedene Länder oder Regionen und warum Sie sie besuchen möchten.",
        api_abruf_noetig=False,
    ),
    FrageDefinition(
        id="F08", stufe=3, cluster="K1", feld="wohnort",
        # Ergänzt, nicht aus dem Rohmaterial (siehe Moduldoku oben). Direkt
        # nach F07 platziert, weil Optimierung 2 Start- UND Zielort für
        # dieselbe Berechnung (An-/Abreise) benötigt.
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Von wo aus treten Sie Ihre Reise an (z.B. Ihre Heimatstadt)?",
        kontext_hinweis="Wird für die Berechnung der An- und Abreise benötigt (Verkehrsmittel, Zeit, Kosten, CO2).",
    ),
    FrageDefinition(
        id="F09", stufe=3, cluster="K6", feld="gesundheitliche_einschraenkungen",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Gibt es bestimmte medizinische Bedürfnisse oder Einschränkungen, die bei der Reiseplanung zu berücksichtigen sind?",
        kontext_hinweis="Beschreiben Sie Ihre medizinischen Bedürfnisse und warum Ihnen Ihre Gesundheit auf der Reise wichtig ist.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F10", stufe=3, cluster="K6", feld="altersgerechte_beduerfnisse",
        # Ergänzt, nicht aus dem Rohmaterial (siehe Moduldoku oben). Bewusst
        # als offene Freitext-Frage statt "Wie alt sind Sie?": eine reine
        # Altersangabe wäre für die Optimierung nicht direkt nutzbar, die
        # dahinterliegenden Bedürfnisse (Tempo, Barrierefreiheit) hingegen
        # schon (vgl. Pagano et al. 2025, Paget et al. 2026 zu inklusivem
        # Tourismus, siehe Kategorien.pdf Feld 02).
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Gibt es altersbedingte Bedürfnisse, die wir bei der Reiseplanung berücksichtigen sollten (z.B. kürzere Gehstrecken, mehr Ruhephasen, Barrierefreiheit)?",
        kontext_hinweis="Erfasst altersgerechte/inklusive Anforderungen unabhängig von akuten gesundheitlichen Einschränkungen (siehe F09) – z.B. Reisetempo und Barrierefreiheit für ältere Reisende oder Familien mit Kindern.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F11", stufe=3, cluster="K5", feld="sicherheitsbeduerfnis",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie wichtig ist Ihnen die Sicherheit und Stabilität des Reiseziels?",
        kontext_hinweis=(
            "Beschreiben Sie Ihre Sicherheitsanforderungen und warum Ihnen die Sicherheit während Ihrer "
            "Reise wichtig ist. NUR relevant, wenn die bereits genannte Zielregion (F07) breit/unklar ist "
            "(z.B. ein ganzes Land wie 'Mexiko', dessen Sicherheitslage je nach Region stark variiert) – bei "
            "einem konkreten, allgemein bekannten sicheren Ziel (z.B. 'Innsbruck') überspringen (siehe "
            "`ueberspringbar` unten)."
        ),
        pflichtfeld=False,
        ueberspringbar=True,
    ),
    FrageDefinition(
        id="F12", stufe=4, cluster="K1", feld="budget_gesamt",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.ZAHL,
        botfrage="Welches Budget haben Sie für Ihre Reise zur Verfügung?",
        kontext_hinweis="Beschreiben Sie Ihr Budget und was Sie sich von diesem Betrag erhoffen.",
    ),
    FrageDefinition(
        id="F13", stufe=5, cluster="K1", feld="verkehrsmittel_praeferenz",
        fragetyp=Fragetyp.DIALOG, rueckgabetyp=Rueckgabetyp.ARRAY,
        botfrage="Welche Verkehrsmittel bevorzugen Sie für Ihre Reise?",
        kontext_hinweis="Beschreiben Sie Ihre bevorzugten Transportmittel und warum Sie diese wählen.",
        api_abruf_noetig=True,
    ),
    FrageDefinition(
        id="F14", stufe=5, cluster="K1", feld="lokaler_transport_praeferenz",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Haben Sie spezifische Vorlieben oder Anforderungen in Bezug auf den Transport vor Ort?",
        # Erweitert (siehe Projektkonversation: "wenn ich mitm Auto hinfahre und dann sage, ich
        # möchte vor Ort mitm Fahrrad fahren, dann musst du nachfragen, hast du ein Fahrrad mit?
        # Sonst musst du dir dort eins leihen"). Vergleicht mit der bereits bestätigten F13-Antwort
        # (das LLM sieht sie über den vollständigen Gesprächsverlauf, siehe agent_tools.py
        # `speichere_feld`) und hakt NUR nach, wenn die lokale
        # Fortbewegung ein Fahrzeug braucht, das die Anreise nicht zwangsläufig mitbringt. Die
        # eigentliche Verleih-SUCHE passiert danach real-datenbasiert im deterministischen Layer
        # (siehe aufbereitung.py `erkenne_leihwunsch`, pipeline.py) – hier wird nur der Nutzerwille
        # sauber erfragt und in der Antwort festgehalten.
        kontext_hinweis=(
            "Beschreiben Sie Ihre Präferenzen in Bezug auf den Transport vor Ort und warum sie Ihnen "
            "wichtig sind. WICHTIG: Vergleiche die Antwort mit der bereits bestätigten Verkehrsmittel-"
            "präferenz für die ANREISE (siehe bereits erfasste Werte, Feld 'verkehrsmittel_praeferenz'). "
            "Braucht die gewünschte lokale Fortbewegung ein Fahrzeug (Auto ODER Fahrrad), das laut "
            "Anreise nicht zwangsläufig vor Ort ist (z.B. Anreise mit Bahn/Fernbus, aber vor Ort Auto "
            "oder Fahrrad gewünscht) – speichere die Antwort NOCH NICHT und "
            "frage GEZIELT nach, ob das Fahrzeug selbst mitgebracht wird oder vor Ort ein Verleih "
            "gesucht werden soll. Ist die Anreise selbst schon mit demselben Fahrzeug (z.B. Anreise UND "
            "vor Ort mit dem Auto), ist KEINE Rückfrage nötig – dann ist das Fahrzeug schon da. Bei "
            "reiner Fortbewegung zu Fuß/ÖPNV ebenfalls keine Rückfrage nötig. Möchte der Nutzer auf "
            "Nachfrage ausleihen, formuliere die GESPEICHERTE Antwort so, dass sie sowohl das Fahrzeug "
            "(Auto/Fahrrad) als auch ein Wort wie 'ausleihen'/'Verleih'/'mieten' klar enthält (löst "
            "danach eine echte Verleih-Suche aus) – bringt der Nutzer sein eigenes mit, reicht ein "
            "normaler Antworttext ohne dieses Wort."
        ),
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F15", stufe=6, cluster="K1", feld="unterkunft_anforderungen",
        fragetyp=Fragetyp.DIALOG, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Welche Anforderungen hinsichtlich Ihrer Unterkunft haben Sie (z.B. luxuriöses Hotel, gemütliches Bed & Breakfast, barrierefrei)?",
        kontext_hinweis="Beschreiben Sie Ihre bevorzugte Art der Unterkunft und welche Annehmlichkeiten Ihnen wichtig sind.",
        api_abruf_noetig=True,
    ),
    # REIHENFOLGE INNERHALB STUFE 7 (siehe Projektkonversation): F17/F18/F19 stehen bewusst VOR
    # F16 (aktivitaeten_interessen), obwohl die Nummerierung (aus dem Original-Fragenkatalog,
    # siehe Moduldoku oben) das Gegenteil suggeriert – die Nummern bleiben unverändert, damit sie
    # weiterhin auf das Original-Dokument rückführbar sind, nur die tatsächliche Gesprächs-
    # Reihenfolge (siehe regelwerk.py `_fragekatalog_uebersicht`, listet in LISTEN-Reihenfolge, das
    # LLM orientiert sich daran) wurde getauscht. Grund: alle drei liefern Kontext, der die
    # AKTIVITÄTEN-Suche direkt beeinflusst – v.a. F18 (Ernährungseinschränkungen) fließt seit
    # Station 8 direkt in die Restaurant-Text-Search-Query ein (siehe google_maps.py
    # `_ist_essen_bezogenes_interesse`); ist F18 zum Zeitpunkt der ERSTEN Restaurant-Suche
    # (innerhalb F16) noch nicht bekannt, bekommt diese erste Suche keine Ernährungsanpassung. Das
    # verletzt NICHT das zitierte Stufenmodell (Choi et al. 2012/Gavalas et al. 2014) – das
    # definiert Stufen, keine strikte Reihenfolge INNERHALB einer Stufe.
    FrageDefinition(
        id="F17", stufe=7, cluster="K4", feld="lernaktivitaeten_interesse",
        fragetyp=Fragetyp.KONTEXT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Sind Sie daran interessiert, neue Fähigkeiten oder Kenntnisse während Ihrer Reise zu erwerben?",
        kontext_hinweis="Beschreiben Sie die Fähigkeiten oder Kenntnisse, die Sie erwerben möchten, und warum sie für Ihre Reise wichtig sind.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F18", stufe=7, cluster="K3", feld="ernaehrung_einschraenkungen",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.ARRAY,
        botfrage="Haben Sie spezielle Ernährungsbedürfnisse oder Allergien, die berücksichtigt werden müssen?",
        kontext_hinweis="Erklären Sie Ihre Ernährungspräferenzen und -anforderungen im Detail.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F19", stufe=7, cluster="K2", feld="lokaler_kontakt_wichtig",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.BOOL,
        botfrage="Wie wichtig ist Ihnen der Kontakt zu Einheimischen und die Erfahrung der lokalen Kultur?",
        kontext_hinweis="Beschreiben Sie, warum Ihnen der Kontakt zu Einheimischen wichtig ist und welche Art von Erfahrungen Sie machen möchten.",
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F16", stufe=7, cluster="K4", feld="aktivitaeten_interessen",
        fragetyp=Fragetyp.DIALOG, rueckgabetyp=Rueckgabetyp.ARRAY,
        botfrage="Welche Aktivitäten und Attraktionen möchten Sie während Ihrer Reise erleben?",
        # Erweitert (siehe Projektkonversation): eine genannte Aktivität allein
        # reicht oft nicht aus, um sie vollständig zu planen. Dieser Hinweis
        # steht im Systemprompt (siehe regelwerk.py) und leitet das LLM an,
        # BEI BEDARF nachzuhaken, bevor es aktivitaeten_interessen per
        # speichere_feld speichert bzw. hole_api_daten dafür aufruft.
        kontext_hinweis=(
            "Geben Sie Ihre spezifischen Interessen und Vorlieben an. WICHTIG: Manche Aktivitäten lassen "
            "sich ohne weitere Angaben nicht sinnvoll planen – hake in diesem Fall gezielt nach, BEVOR du "
            "die Antwort als vollständig behandelst und speicherst. Beispiele: "
            "Klettern/Bouldern -> Schwierigkeitsgrad/Erfahrungslevel und ob eine Kletterhalle reicht oder "
            "Outdoor-Felsen gewünscht sind (Achtung: für Outdoor-Kletterrouten gibt es keine echte "
            "Datenquelle, das darf nicht als exakter Vorschlag vorgetäuscht werden); Wassersport -> "
            "Schwimmkenntnisse/Zertifizierung; Skifahren/Snowboarden -> Pistenlevel. Bei generischen "
            "Interessen (z.B. 'Kultur', 'Sehenswürdigkeiten', 'Essen gehen') ist keine Vertiefung nötig – "
            "frag nur nach, wenn die Aktivität ohne die Zusatzangabe erkennbar unklar bliebe, nicht bei "
            "jeder Antwort. Da F17–F19 jetzt VOR dieser Frage gestellt werden (siehe Kommentar oben), "
            "kannst du bereits bekannte Ernährungseinschränkungen (F18) direkt bei einer ersten "
            "Restaurant-/Essen-Suche berücksichtigen, statt sie erst nachträglich zu korrigieren."
        ),
        api_abruf_noetig=True,
    ),
    FrageDefinition(
        id="F20", stufe=5, cluster="K1", feld="tagesstart_praeferenz",
        # Ergänzt, nicht aus dem Rohmaterial (siehe Moduldoku oben, analog zu F08/F10) – siehe
        # Projektkonversation: "es stehen gar keine Uhrzeiten dran... frag doch, wann die Person
        # starten will und wie lang der Tag sein soll". Ohne diese Angabe bleiben Tagespläne bei
        # relativen Zeitangaben ("nach 30 Min."), da sonst keine reale Uhrzeit bekannt ist
        # (Grundprinzip 1 – keine erfundene Uhrzeit, siehe reiseplan.py `_format_dauer`). Mit
        # Angabe kann Optimierung 1 zusätzlich category-abhängige Tageszeitfenster ansetzen (siehe
        # aufbereitung.py `wende_tageszeitfenster_an` – keine Bar direkt nach dem Aufstehen).
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Ab wann möchten Sie tagsüber typischerweise mit Ihrem Programm starten, und bis wann spätestens abends unterwegs sein?",
        kontext_hinweis=(
            "Erfasse eine ungefähre Start- und Enduhrzeit für einen normalen Reisetag (z.B. "
            "'ab 9 Uhr bis maximal 21 Uhr'). Eine grobe Angabe reicht völlig, keine Rückfrage bei "
            "vagen Antworten wie 'eher früh' nötig – dann bleibt die vorsichtige Standardannahme "
            "bestehen."
        ),
        pflichtfeld=False,
    ),
]

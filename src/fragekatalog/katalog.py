"""
Konsolidierter Fragekatalog des Reisebot-Prototyps.

Quelle: `Fortschritte/Fragekatalog/100 Fragen.docx` (vom Product Owner als
maßgebliche Fragenbasis bestätigt). Die Reihenfolge folgt dem Stufenmodell
aus `Fortschritte/Fragekatalog/Kategorien.pdf` (7 sequenzielle
Entscheidungsstufen nach Choi et al. 2012 / Gavalas et al. 2014); die
Cluster-Zuordnung (K1, K2, K3, K4, K5, K6) übernimmt die Kategorien aus dem
Kodierleitfaden. K2 (Nachhaltigkeit) ist laut Kodierleitfaden ein
Querschnittsprinzip und wird nicht als eigene Stufe geführt, taucht aber bei
F19 inhaltlich noch auf (das Rohmaterial ordnete diese Frage K2 zu).

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

Zwei spätere Anpassungen auf ausdrücklichen Nutzerwunsch (siehe ENTSCHEIDUNGSLOG.md), reine
Reihenfolge-/Zuschnittsänderungen ohne neue Felder:
- Die frühere eigene Frage F18 (Unverträglichkeiten/Allergien, `ernaehrung_einschraenkungen`) wurde
  entfernt und inhaltlich in F09 (gesundheitliche Einschränkungen) integriert – siehe Kommentar
  direkt bei F09 unten. Das Feld `ernaehrung_einschraenkungen` bleibt im Schema unverändert bestehen.
- F04 (Reiseleitung gewünscht) wurde nach hinten verschoben, direkt vor F17 (Lernaktivität) – siehe
  Kommentar dort.

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
        id="F05", stufe=1, cluster="K1", feld="flexibilitaet_praeferenz",
        fragetyp=Fragetyp.KONTEXT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie wichtig ist Ihnen die Flexibilität in Ihrem Reiseplan?",
        kontext_hinweis=(
            "Erklären Sie, warum Ihnen Flexibilität wichtig ist oder warum Sie eine strukturierte "
            "Reiseroute bevorzugen. Setze beim Speichern zusätzlich das Tool-Argument "
            "flexibilitaet_stufe (1 = ganz durchgeplant/eng, 2 = Mitte, 3 = flexibel) – leite das aus "
            "dem GESAMTEN Gesprächsverlauf ab (Tonfall, spätere Formulierungen zählen genauso), frag "
            "NICHT direkt nach einer Zahl. WICHTIG (Rückfrage-Ergebnis, Live-Vorfall: ein einfaches "
            "'gerne flexibel' wurde fälschlich als Stufe 2 statt 3 eingeordnet): die Skala hat NUR "
            "3 Stufen, die Nutzer:in muss sich dafür NICHT extrem/übertrieben ausdrücken – ein "
            "einfaches 'flexibel'/'gerne flexibel'/'spontan' OHNE Steigerung wie 'extrem' oder 'total' "
            "reicht bereits für Stufe 3, ein einfaches 'durchgeplant'/'fest'/'strukturiert' reicht "
            "bereits für Stufe 1. Stufe 2 (die Mitte) ist NUR für erkennbar gemischte/neutrale "
            "Aussagen (z.B. 'teils, teils' oder 'kommt drauf an') reserviert, nicht der Standardfall "
            "für jede unklare Antwort. Kann später im Gespräch verfeinert werden, wenn sich der "
            "Eindruck ändert."
        ),
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F06", stufe=2, cluster="K1", feld="reisezeitraum_rohtext",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Wie lange möchten Sie verreisen? Gibt es einen bestimmten Reisezeitraum, den Sie bevorzugen?",
        kontext_hinweis=(
            "Geben Sie Ihren bevorzugten Reisezeitraum an und erklären Sie, warum dieser Zeitraum "
            "ideal für Sie ist. WICHTIG (siehe Systemprompt): leite aus der Antwort ein eindeutiges "
            "Start- und Enddatum ab (ISO-Format YYYY-MM-DD) und setze sie als Tool-Argumente "
            "reise_start_datum/reise_end_datum bei speichere_feld – NUR wenn du dir wirklich sicher "
            "bist. Fehlt z.B. das Jahr oder ist die Angabe erkennbar mehrdeutig (z.B. nur 'im "
            "Sommer' ohne genaueren Zeitraum), frag aktiv nach, statt zu raten – die tatsächliche "
            "Anzahl Reisetage wird NICHT von dir berechnet, sondern deterministisch aus diesen "
            "beiden Daten (Rückfrage-Ergebnis nach zwei Live-Bugs im reinen Freitext-Parser)."
        ),
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
        kontext_hinweis=(
            "Beschreiben Sie Ihre Interessen in Bezug auf verschiedene Länder oder Regionen und warum "
            "Sie sie besuchen möchten. WICHTIG: Aktuell kann pro Reise nur EIN Ziel geplant werden "
            "(Optimierung 1+2 bauen eine Rundreise mit EINEM Aufenthaltsort, siehe CLAUDE.md "
            "Grundprinzip 4) – nennt der Nutzer mehrere Städte/Regionen, weise ihn KURZ und ehrlich "
            "darauf hin, dass sich aktuell nur eine davon planen lässt, und bitte ihn, sich auf eine "
            "festzulegen. Behaupte NIE (auch nicht später im Gespräch), dass mehrere genannte Ziele "
            "gemeinsam oder nacheinander durchsucht/geplant werden – das stimmt technisch nicht."
        ),
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
    # Ehemals zwei getrennte Fragen: Unverträglichkeiten/Allergien hatten eine eigene Katalogfrage
    # (früher F18, `ernaehrung_einschraenkungen`) direkt vor F16. Auf Nutzerwunsch (siehe
    # ENTSCHEIDUNGSLOG.md) hier zusammengelegt, weil beide inhaltlich "gesundheitsbezogene
    # Einschränkung" abfragen: F18 als eigene Frage entfernt, stattdessen fragt F09 danach mit; das
    # Feld `ernaehrung_einschraenkungen` bleibt im Schema erhalten (wird u.a. für die
    # Restaurant-Suche und Verträglichkeitsprüfung gebraucht, siehe google_maps.py/
    # vertraeglichkeit.py) und wird jetzt über das Tool-Argument `ernaehrung_einschraenkungen` bei
    # speichere_feld(feld="gesundheitliche_einschraenkungen") gesetzt (siehe agent_tools.py) – NUR
    # wenn der Nutzer hier tatsächlich eine Unverträglichkeit/Allergie nennt, danach gezielt
    # nachfragen, welche genau; ohne eine solche Nennung wird das Thema NICHT eigens angesprochen.
    FrageDefinition(
        id="F09", stufe=3, cluster="K6", feld="gesundheitliche_einschraenkungen",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage=(
            "Gibt es bestimmte medizinische Bedürfnisse oder Einschränkungen – oder auch "
            "Unverträglichkeiten bzw. Allergien beim Essen –, die bei der Reiseplanung zu "
            "berücksichtigen sind?"
        ),
        kontext_hinweis=(
            "Beschreiben Sie Ihre medizinischen Bedürfnisse und warum Ihnen Ihre Gesundheit auf der Reise "
            "wichtig ist. Setze beim Speichern das Tool-Argument mobilitaetseinschraenkung_stufe, wenn du aus "
            "der Antwort (auch sinngemäß, nicht nur bei den Wörtern 'barrierefrei'/'Rollstuhl') eine "
            "Mobilitätseinschränkung erkennst – 'leicht' bei z.B. langsamerem Tempo (jeder Ort bleibt nutzbar), "
            "'mittel' bei z.B. Krücken/Gehhilfe, 'stark' bei z.B. Rollstuhl (nur eindeutig bestätigte Orte). "
            "ERNÄHRUNG (ersetzt die frühere eigene Frage F18, siehe Kommentar oben): nennt der Nutzer HIER "
            "eine Unverträglichkeit oder Allergie (z.B. 'ich vertrage keine Laktose', 'Erdnussallergie', "
            "'ich esse kein Gluten'), frage GEZIELT nach, um WELCHE es genau geht, und setze dann beim "
            "Speichern zusätzlich das Tool-Argument ernaehrung_einschraenkungen (Liste der konkreten "
            "Einschränkungen, z.B. ['Laktoseintoleranz']) – das fließt in die Restaurant-Suche und die "
            "Verträglichkeitsprüfung des fertigen Plans ein. Wird HIER NICHTS dergleichen erwähnt, frage "
            "NICHT extra danach und lass das Thema unbehandelt (kein separates Nachhaken zu Ernährung, wenn "
            "der Nutzer nur medizinische/mobilitätsbezogene Einschränkungen nennt oder gar keine)."
        ),
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
        kontext_hinweis=(
            "Erfasst altersgerechte/inklusive Anforderungen unabhängig von akuten gesundheitlichen "
            "Einschränkungen (siehe F09) – z.B. Reisetempo und Barrierefreiheit für ältere Reisende oder "
            "Familien mit Kindern. Setze beim Speichern das Tool-Argument mobilitaetseinschraenkung_stufe, "
            "wenn die Antwort ein langsameres Tempo/mehr Pausen/eingeschränkte Mobilität erkennen lässt (auch "
            "sinngemäß, z.B. 'wegen der Kinder lieber gemütlich', nicht nur bei wörtlicher Nennung) – meist "
            "'leicht' (jeder Ort bleibt nutzbar, nur Tempo/Pausen), bei erkennbar stärkerer Einschränkung "
            "(Gehhilfe/Rollstuhl) 'mittel'/'stark'."
        ),
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
            "`ueberspringbar` unten). Setze beim Speichern das Tool-Argument `sicherheit_bedenklich`, wenn "
            "der GESAMTE Gesprächskontext eine echte Sicherheitssorge erkennen lässt – erkennst du dabei ein "
            "erkennbar problematisches Ziel, schlage VORHER proaktiv eine sicherere Alternativregion vor."
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
        fragetyp=Fragetyp.DIALOG, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Haben Sie spezifische Vorlieben oder Anforderungen in Bezug auf den Transport vor Ort?",
        # Vergleicht mit der bereits bestätigten F13-Antwort (das LLM sieht sie über den
        # vollständigen Gesprächsverlauf) und hakt NUR nach, wenn die lokale Fortbewegung ein
        # Fahrzeug braucht, das die Anreise nicht zwangsläufig mitbringt. Bei erkanntem Leihwunsch
        # sucht hole_api_daten einen echten Verleih nahe der Unterkunft (siehe vorschlaege.py
        # `suche_verleih_nahe_unterkunft`) – braucht dafür eine bereits bestätigte Unterkunft (F15),
        # rufe es also ERST NACH F15 auf.
        kontext_hinweis=(
            "Beschreiben Sie Ihre Präferenzen in Bezug auf den Transport vor Ort und warum sie Ihnen "
            "wichtig sind. WICHTIG: Vergleiche die Antwort mit der bereits bestätigten Verkehrsmittel-"
            "präferenz für die ANREISE (siehe bereits erfasste Werte, Feld 'verkehrsmittel_praeferenz'). "
            "Braucht die gewünschte lokale Fortbewegung ein Fahrzeug (Auto ODER Fahrrad), das laut "
            "Anreise nicht zwangsläufig vor Ort ist (z.B. Anreise mit Bahn/Fernbus, aber vor Ort Auto "
            "oder Fahrrad gewünscht) – speichere die Antwort NOCH NICHT und "
            "frage GEZIELT nach, ob das Fahrzeug selbst mitgebracht wird oder vor Ort ein Verleih "
            "gesucht werden soll. Ist die Anreise selbst schon mit demselben Fahrzeug, oder reine "
            "Fortbewegung zu Fuß/ÖPNV, ist KEINE Rückfrage nötig. Möchte der Nutzer ausleihen: speichere "
            "die Antwort per speichere_feld, warte bis F15 (Unterkunft) abgeschlossen ist, rufe DANACH "
            "hole_api_daten für dieses Feld auf (sucht echten Verleih nahe der Unterkunft) und nenne dem "
            "Nutzer das Ergebnis."
        ),
        pflichtfeld=False,
        api_abruf_noetig=True,
    ),
    FrageDefinition(
        # Typ C (siehe Systemprompt/regelwerk.py): sucht GENAU EINE echte Unterkunft passend zur
        # genannten Anforderung und schlägt sie dem Nutzer zur kurzen Bestätigung vor ("passt das
        # für dich?") – KEINE Liste mehrerer Kandidaten. Optimierung 1 nutzt danach GENAU diese
        # bestätigte Unterkunft als Depot (siehe pipeline.py), keine zweite unabhängige Suche.
        id="F15", stufe=6, cluster="K1", feld="unterkunft_anforderungen",
        fragetyp=Fragetyp.DIALOG, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Welche Anforderungen hinsichtlich Ihrer Unterkunft haben Sie (z.B. luxuriöses Hotel, gemütliches Bed & Breakfast, barrierefrei)?",
        kontext_hinweis=(
            "Beschreiben Sie Ihre bevorzugte Art der Unterkunft und welche Annehmlichkeiten Ihnen "
            "wichtig sind. Rufe danach hole_api_daten auf – es liefert GENAU EINE echte, passende "
            "Unterkunft. Nenne dem Nutzer diese Unterkunft kurz und hol eine einfache Bestätigung ein "
            "('passt das für dich?'), erst DANACH speichere_feld aufrufen. Bei Ablehnung/Verfeinerungs-"
            "wunsch hole_api_daten erneut mit angepasster Anforderung aufrufen. Liefert die Suche gar "
            "nichts, sag das ehrlich, statt ein Hotel zu erfinden. Setze beim Speichern das Tool-Argument "
            "mobilitaetseinschraenkung_stufe, wenn die genannte Anforderung eine Mobilitätseinschränkung "
            "erkennen lässt (z.B. 'stark' bei 'barrierefrei wegen Rollstuhl', 'mittel' bei 'ebenerdig "
            "erreichbar wegen Rollator')."
        ),
        api_abruf_noetig=True,
    ),
    # REIHENFOLGE INNERHALB STUFE 7 (siehe Projektkonversation): F17/F19 stehen bewusst VOR
    # F16 (aktivitaeten_interessen), obwohl die Nummerierung (aus dem Original-Fragenkatalog,
    # siehe Moduldoku oben) das Gegenteil suggeriert – die Nummern bleiben unverändert, damit sie
    # weiterhin auf das Original-Dokument rückführbar sind, nur die tatsächliche Gesprächs-
    # Reihenfolge (siehe regelwerk.py `_fragekatalog_uebersicht`, listet in LISTEN-Reihenfolge, das
    # LLM orientiert sich daran) wurde getauscht. Grund: beide liefern Kontext, der die
    # AKTIVITÄTEN-Suche direkt beeinflusst (v.a. F19 löst dort ggf. zusätzliche Markt-/
    # Kneipen-Suchbegriffe aus). Das verletzt NICHT das zitierte Stufenmodell (Choi et al. 2012/
    # Gavalas et al. 2014) – das definiert Stufen, keine strikte Reihenfolge INNERHALB einer Stufe.
    #
    # F04 (reiseleitung_gewuenscht) wandert aus demselben Grund (Nutzerwunsch, siehe
    # ENTSCHEIDUNGSLOG.md) hierher, direkt VOR F17 (Lernaktivität): beide fragen im Kern "möchten
    # Sie sich etwas vor Ort zeigen/vermitteln lassen" (geführte Reiseleitung bzw. Kurs/Workshop)
    # und gehören daher thematisch zusammen, statt wie zuvor weit auseinanderzuliegen (F04 stand
    # ursprünglich direkt nach F03). id/stufe/cluster bleiben unverändert (siehe Begründung oben) –
    # nur die tatsächliche Gesprächsposition ändert sich.
    FrageDefinition(
        id="F04", stufe=1, cluster="K1", feld="reiseleitung_gewuenscht",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.BOOL,
        botfrage="Möchten Sie einen Reiseleiter oder eine Reiseleitung vor Ort haben?",
        kontext_hinweis=(
            "Erklären Sie, warum Sie eine Reiseleitung bevorzugen oder lieber auf eigene Faust erkunden "
            "möchten. WICHTIG: Wird hier oder später im Gespräch eine Reiseleitung/geführte Tour/eine "
            "bestimmte Tour-Art gewünscht, merke dir das – bei F16 (aktivitaeten_interessen) muss dafür "
            "ein eigener, konkreter Suchbegriff (z.B. 'geführte Tour', oder die genannte spezifische Art wie "
            "'Fahrradtour mit Guide') als Interesse aufgenommen werden, sonst wird dafür NIE eine echte "
            "Suche ausgelöst und der Wunsch bleibt wirkungslos. Äußert der Nutzer hier oder später EXPLIZIT "
            "den Wunsch nach MEHREREN Tour-Tagen (z.B. 'ich möchte mehrere Tage Touren machen'), setze "
            "zusätzlich das Tool-Argument tour_tage_anzahl bei speichere_feld (siehe Systemprompt) – ohne "
            "eine solche ausdrückliche Aussage bleibt es immer bei einer Eintagestour, NICHT proaktiv danach "
            "fragen."
        ),
    ),
    FrageDefinition(
        id="F17", stufe=7, cluster="K4", feld="lernaktivitaeten_interesse",
        fragetyp=Fragetyp.KONTEXT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Sind Sie daran interessiert, neue Fähigkeiten oder Kenntnisse während Ihrer Reise zu erwerben?",
        kontext_hinweis=(
            "Beschreiben Sie die Fähigkeiten oder Kenntnisse, die Sie erwerben möchten, und warum sie "
            "für Ihre Reise wichtig sind. Zwei Fälle: (1) Eine KONKRETE, ortsgebundene Aktivität "
            "(Kochkurs, Sprachkurs, Workshop o.ä.) – nimm dafür einen eigenen, konkreten Suchbegriff "
            "in aktivitaeten_interessen (F16) auf, auch ohne erneute Nachfrage (nur so löst "
            "hole_api_daten tatsächlich eine echte Suche dafür aus). (2) Eine UNKONKRETE Aussage ohne "
            "buchbaren Ort (z.B. 'ich möchte einfach offen sein und dazulernen', 'eine Sprache "
            "lernen' ohne Kurswunsch) – dafür gibt es KEINE echten Daten zu suchen. Bleib hier aber "
            "NICHT einfach stumm: gib eine kurze, sinnvolle allgemeine Empfehlung (bekannte, real "
            "existierende Angebote sind erlaubt, z.B. 'eine Sprachlern-App wie Duolingo während der "
            "Fahrt', 'ein Reiseführer oder Wikipedia-Artikel zur Stadtgeschichte') – KEINE erfundenen "
            "oder unsicheren Fakten über den konkreten Zielort selbst."
        ),
        pflichtfeld=False,
    ),
    FrageDefinition(
        id="F19", stufe=7, cluster="K2", feld="lokaler_kontakt_wichtig",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.BOOL,
        botfrage="Wie wichtig ist Ihnen der Kontakt zu Einheimischen und die Erfahrung der lokalen Kultur?",
        kontext_hinweis=(
            "Beschreiben Sie, warum Ihnen der Kontakt zu Einheimischen wichtig ist und welche Art von "
            "Erfahrungen Sie machen möchten. Ordne die ANTWORT AUF DIESE FRAGE (nicht das gesamte "
            "bisherige Gespräch) in ja/wichtig oder nein/unwichtig ein. Bei 'wichtig': nimm bei F16 "
            "(aktivitaeten_interessen) zusätzlich einen Markt-Suchbegriff (z.B. 'Wochenmarkt') UND "
            "einen Kneipen-Suchbegriff (z.B. 'urige Kneipe') auf, auch ohne erneute Nachfrage – nur so "
            "lösen die echten Suchen dafür aus. Geführte Touren/Kochkurse MIT Einheimischen laufen "
            "weiterhin über F04/F17, nicht über diese Frage."
        ),
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
        # WIEDER Typ C (Station 11, siehe Projektkonversation: "macht die POIs einfach genauso, wie
        # sie vorher waren, das war sehr sehr gut" – nur F15 bleibt Typ B, siehe dort): die
        # Vertiefungs-Nachfragen + die Chat-Vorschau mit echten Kandidaten haben sich bewährt.
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
            "jeder Antwort. Da F17/F19 jetzt VOR dieser Frage gestellt werden (siehe Kommentar oben) und "
            "F09 (gesundheitliche_einschraenkungen, inkl. Unverträglichkeiten/Allergien) ohnehin schon "
            "viel früher im Gespräch lag, kannst du bereits bekannte Ernährungseinschränkungen direkt bei "
            "einer ersten Restaurant-/Essen-Suche berücksichtigen, statt sie erst nachträglich zu "
            "korrigieren. Wurde "
            "eine Reiseleitung/geführte Tour gewünscht (F04 oder später im Gespräch), nimm dafür EINEN "
            "eigenen, konkreten Suchbegriff in diese Liste auf (z.B. 'geführte Tour', oder eine vom Nutzer "
            "genannte spezifische Art), auch ohne erneute Nachfrage – nur so löst hole_api_daten "
            "tatsächlich eine echte Suche dafür aus. Genauso bei einer KONKRETEN Lernaktivität (F17, z.B. "
            "'Kochkurs', 'Sprachkurs') – auch dafür einen eigenen Suchbegriff aufnehmen. Ist Kontakt zu "
            "Einheimischen/lokale Kultur wichtig (F19), nimm zusätzlich EINEN Markt-Suchbegriff (z.B. "
            "'Wochenmarkt') UND einen Kneipen-Suchbegriff (z.B. 'urige Kneipe') auf."
        ),
        api_abruf_noetig=True,
    ),
    FrageDefinition(
        # Ergänzt, nicht aus dem Rohmaterial (siehe Moduldoku oben, analog zu F08/F10). Ohne diese
        # Angabe bleiben Tagespläne bei relativen Zeitangaben ("nach 30 Min."), da sonst keine reale
        # Uhrzeit bekannt ist (Grundprinzip 1 – keine erfundene Uhrzeit, siehe reiseplan.py
        # `_format_dauer`). Die eigentliche Interpretation der Antwort in konkrete Uhrzeiten
        # übernimmt das LLM selbst (Tool-Argumente bei speichere_feld, siehe agent_tools.py) statt
        # eines Regex-Parsers – Freitext wie "ab neun bis abends um neun" oder "eher früh los,
        # nicht so spät zurück" lässt sich damit zuverlässiger verstehen als mit festen
        # Uhrzeit-Mustern.
        id="F20", stufe=5, cluster="K1", feld="tagesstart_praeferenz",
        fragetyp=Fragetyp.WERT, rueckgabetyp=Rueckgabetyp.STRING,
        botfrage="Ab wann möchten Sie tagsüber typischerweise mit Ihrem Programm starten, und bis wann spätestens abends unterwegs sein?",
        kontext_hinweis=(
            "Erfasse eine ungefähre Start- und Enduhrzeit für einen normalen Reisetag (z.B. "
            "'ab 9 Uhr bis maximal 21 Uhr'). Eine grobe Angabe reicht völlig. Speichere beim "
            "Aufruf von speichere_feld zusätzlich zum reinen Antworttext die Tool-Argumente "
            "`tagesstart_minuten`/`tagesende_minuten` (Minuten seit Mitternacht, z.B. 9 Uhr = 540, "
            "21 Uhr = 1260) – interpretiere dafür die Antwort selbst, auch bei vagen Formulierungen "
            "wie 'eher früh' oder 'nicht so spät zurück' (leite dann eine plausible Uhrzeit ab, "
            "erfinde aber keine Uhrzeit, wenn die Antwort GAR KEINEN zeitlichen Anhaltspunkt "
            "enthält – dann lässt du diese beiden Argumente einfach weg, ein Konfigurations-Default "
            "greift dann automatisch). Das bestimmt direkt das tatsächliche Tagesbudget der "
            "Optimierung, keine Rückfrage bei vagen Antworten nötig."
        ),
        pflichtfeld=False,
    ),
]

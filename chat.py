"""
Interaktiver Ende-zu-Ende-Chat mit echtem LLM (Claude Agent SDK) als
Dialogschicht. Läuft standardmäßig als Text-Chat; mit `AUDIO_MODUS=true`
(siehe .env.example) läuft dieselbe Logik stattdessen per Mikrofon/Stimme
(src/audio/) – die Ein-/Ausgabe ist über `IOKanal` (src/audio/kanal.py)
abstrahiert, am Dialogablauf selbst ändert sich dadurch nichts.

ARCHITEKTUR (seit 11.08., siehe ENTSCHEIDUNGSLOG.md "Architekturwechsel:
LLM-autonome Dialogsteuerung"): Anders als vorher gibt es KEINE feste
Python-Zustandsmaschine mehr, die Frage für Frage vorgibt. Das LLM bekommt
den vollständigen Fragekatalog + fünf Werkzeuge (siehe
src/fragekatalog/agent_tools.py: speichere_feld, hole_api_daten,
fehlende_pflichtfelder, plane_reise_und_abschliessen, breche_planung_ab) in
einer einzigen, durchgehenden Agenten-Session und entscheidet SELBST, wann
welche Frage nötig ist. Der regelbasierte Layer bleibt trotzdem
verantwortlich für alles, was CLAUDE.md, Grundprinzip 1/3 weiterhin
garantiert: Werte werden typgeprüft (nicht das LLM entscheidet, ob ein Wert
"passt"), echte Daten kommen ausschließlich aus den bestehenden API-Modulen
(nie vom LLM erfunden), die eigentliche Reiseplanung (Optimierung 1+2,
Monte-Carlo-Härtetest) bleibt 1:1 der bestehende `pipeline.py`, und
`plane_reise_und_abschliessen` ist hart gesperrt, bis alle Pflichtfelder
gesetzt sind.

Aufruf: python chat.py
Voraussetzung: Zugriff auf eine Claude-Code-Anmeldung/Abo (claude-agent-sdk
spawnt dafür im Hintergrund eine Claude-Code-Session, kein separater
ANTHROPIC_API_KEY nötig), analog zu reisebot_team.py. Für AUDIO_MODUS=true
zusätzlich: pip install -r requirements-audio.txt.
"""
from __future__ import annotations

import asyncio
import sys

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock

from src.api.google_maps import erzeuge_client
from src.audio.kanal import IOKanal, erzeuge_kanal
from src.ausgabe.reiseplan import als_text
from src.config import EINSTELLUNGEN
from src.fragekatalog.agent_tools import ERLAUBTE_TOOLS, AgentSessionState, erstelle_mcp_server
from src.fragekatalog.regelwerk import baue_regelwerk_text
from src.fragekatalog.schema import ReiseAnfrage
from src.protokoll import Protokollierer

_ROLLENBESCHREIBUNG = """\
Du bist die Dialogschicht eines Reiseplanungsbots (Masterarbeit, siehe \
CLAUDE.md). Du führst das Gespräch UND steuerst selbst, welche Fragen aus \
dem Katalog unten wann nötig sind (siehe Regelwerk). Du erfindest NIE \
Fakten (Orte, Preise, Öffnungszeiten, Verfügbarkeiten, POIs) und erstellst \
NIE selbst die Reise – das übernimmt ausschließlich der regelbasierte \
Layer über die dir zur Verfügung stehenden Werkzeuge und echte \
Optimierungsalgorithmen.

TONALITÄT: Du bist kein Formular, sondern ein aufmerksamer, warmherziger \
Reiseberater, der wirklich zuhört. Diese Session läuft komplett durch EIN \
Gespräch – du siehst die gesamte bisherige Konversation. Nutze das aktiv: \
wenn der Nutzer z.B. schon erzählt hat, dass er klettern will, dann frag \
nicht trocken "Mit wem möchten Sie reisen?", sondern beziehe dich darauf \
("Und mit wem geht's auf den Fels?"). Zeig, dass du zuhörst, ohne dabei \
albern oder aufgesetzt zu wirken – locker und echt, nicht overacted. \
Variiere deine Formulierungen, statt jede Frage im selben Muster zu stellen.

Sei bei der Interpretation von Antworten großzügig und alltagssprachlich \
(z.B. "jo" oder "klar" als "ja" werten), aber erfinde keine Werte, die der \
Nutzer nicht genannt hat. Wenn eine Antwort erkennbar ausweicht oder unklar \
ist, frage konkret nach statt zu raten oder trotzdem zu speichern.
"""


class LLMVerbindungsFehler(Exception):
    """Die Claude-Agent-SDK-Session konnte den Turn nicht abschließen (z.B. Nutzungskontingent
    aufgebraucht, Rate-Limit, Netzwerkfehler) – siehe `ResultMessage.is_error`."""


async def a1_reisewunsch_aeussern(io_kanal: IOKanal) -> str:
    """Lane Nutzer, Knoten a1 "Reisewunsch äußern" – freier Einstieg vor dem strukturierten Fragekatalog."""
    await io_kanal.bot_sagt("Schön, dass Sie da sind! Erzählen Sie mir kurz in eigenen Worten: "
                             "Was schwebt Ihnen für eine Reise vor?")
    return await io_kanal.nutzer_antwortet()


async def hauptablauf(
    io_kanal: IOKanal | None = None, protokoll_praefix: str = "chat", ausgabe_basisname: str = "reiseplan_chat"
) -> AgentSessionState | None:
    """
    Führt eine komplette Reiseplanung aus. `io_kanal`/`protokoll_praefix`/`ausgabe_basisname`
    bleiben parametrisierbar (Standardaufruf nutzt Text-/Audio-Konsole, siehe `erzeuge_kanal`;
    webapp.py übergibt stattdessen einen `WebIOKanal`) – ermöglicht bei Bedarf einen alternativen
    Kanal, ohne diese Funktion zu duplizieren. Gibt den finalen `AgentSessionState` zurück (u.a.
    `reiseplan`/`abgeschlossen`/`abgebrochen`), damit Aufrufer wie webapp.py nach Gesprächsende
    noch etwas mit dem Ergebnis tun können (z.B. Fotos nachladen) – `None` nur bei einem
    `LLMVerbindungsfehler`, der die Sitzung vorzeitig beendet.
    """
    # Windows-Konsolen laufen oft mit einer cp1252-Codepage statt UTF-8;
    # ohne diese Umstellung werden Umlaute (ä/ö/ü/ß) in der Ausgabe zu "�".
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== Reisebot ===")
    if io_kanal is not None:
        pass  # Extern übergebener Kanal bringt seine eigene Ein-/Ausgabe mit, keine Zusatzhinweise nötig.
    elif EINSTELLUNGEN.audio_modus:
        print(f"Sprachmodus aktiv (Anbieter: {EINSTELLUNGEN.audio_anbieter}): "
              "sprich deine Antworten, der Bot antwortet per Stimme.")
        if EINSTELLUNGEN.audio_anbieter == "lokal":
            print("Lade Whisper-Modell (kann beim ersten Mal etwas dauern) ...")
    else:
        print("Beantworte die Fragen in eigenen Worten. 'abbrechen' beendet jederzeit.")
    if io_kanal is None:
        io_kanal = erzeuge_kanal(
            audio_modus=EINSTELLUNGEN.audio_modus,
            audio_anbieter=EINSTELLUNGEN.audio_anbieter,
            whisper_modellgroesse=EINSTELLUNGEN.whisper_modellgroesse,
            google_cloud_speech_api_key=EINSTELLUNGEN.google_cloud_speech_api_key,
        )
    print()

    # Protokoll: EIN JSONL-Log pro Sitzung, hält jeden Tool-Aufruf und die wichtigsten
    # Meilensteine fest (Nachvollziehbarkeit, siehe src/protokoll.py).
    protokollierer = Protokollierer.neue_sitzung(praefix=protokoll_praefix)
    print(f"(Protokoll dieser Sitzung: {protokollierer.pfad})\n")

    reisewunsch = await a1_reisewunsch_aeussern(io_kanal)  # a1 (Lane Nutzer)
    protokollierer.eintrag("sitzung_start", reisewunsch=reisewunsch)
    print()

    state = AgentSessionState(
        anfrage=ReiseAnfrage(reiseerlebnis_beschreibung=reisewunsch),
        maps_client=erzeuge_client(),
        protokollierer=protokollierer,
        ausgabe_basisname=ausgabe_basisname,
    )
    options = ClaudeAgentOptions(
        system_prompt=_ROLLENBESCHREIBUNG + "\n" + baue_regelwerk_text(reisewunsch),
        model=EINSTELLUNGEN.llm_modell,
        mcp_servers={"reisebot": erstelle_mcp_server(state)},
        allowed_tools=ERLAUBTE_TOOLS + ["WebSearch"],
        # Nur "WebSearch" zusätzlich zu den 5 MCP-Tools erlaubt (keine Bash/Read/Edit/...) – bewusste,
        # dokumentierte Ausnahme von Grundprinzip 1-3 (siehe CLAUDE.md/ENTSCHEIDUNGSLOG.md, Rückfrage
        # beim Product Owner): ersetzt NICHT die deterministischen API-Werkzeuge für POIs/Unterkünfte/
        # Preise/Reisezeiten (siehe regelwerk.py, Abschnitt WEBSEARCH), sondern deckt reine
        # Kontext-/Hintergrundrecherche ab, die sonst gar nicht möglich wäre.
        tools=["WebSearch"],
    )

    try:
        async with ClaudeSDKClient(options=options) as client:
            nutzertext = reisewunsch
            while not state.abgebrochen and not state.abgeschlossen:
                await client.query(nutzertext)
                async for nachricht in client.receive_response():
                    if isinstance(nachricht, AssistantMessage):
                        for block in nachricht.content:
                            if isinstance(block, TextBlock) and block.text.strip():
                                await io_kanal.bot_sagt(block.text)
                    elif isinstance(nachricht, ResultMessage):
                        if nachricht.is_error:
                            raise LLMVerbindungsFehler(
                                nachricht.result or "Unbekannter Fehler bei der Verbindung zum Sprachmodell."
                            )
                        protokollierer.eintrag(
                            "sdk_turn_ende", usage=getattr(nachricht, "usage", None), result=nachricht.result
                        )
                # Hotel-Vorschau-Karte (Foto/Preisniveau, siehe IOKanal.zeige_karte): sobald
                # hole_api_daten(unterkunft_anforderungen) währenddessen einen NEUEN Kandidaten
                # gefunden hat (state.zuletzt_gefundene_unterkunft, siehe agent_tools.py), wird sie
                # genau EINMAL pro Kandidat gezeigt – zusätzlich zum Text, den das LLM ohnehin
                # formuliert (Grundprinzip 1: der Text bleibt maßgeblich, die Karte ist nur eine
                # visuelle Ergänzung für Kanäle, die das darstellen können, siehe kanal.py).
                if (
                    state.zuletzt_gefundene_unterkunft is not None
                    and state.zuletzt_gefundene_unterkunft is not state.unterkunft_karte_zuletzt_gezeigt
                ):
                    await io_kanal.zeige_karte(state.zuletzt_gefundene_unterkunft)
                    state.unterkunft_karte_zuletzt_gezeigt = state.zuletzt_gefundene_unterkunft
                if state.abgebrochen or state.abgeschlossen:
                    break
                nutzertext = await io_kanal.nutzer_antwortet()
    except LLMVerbindungsFehler as fehler:
        # z.B. Nutzungskontingent aufgebraucht, Rate-Limit – klare Meldung statt Python-Traceback.
        protokollierer.eintrag("llm_verbindungsfehler", fehler=str(fehler))
        print(f"\nBot: Die Verbindung zum Sprachmodell ist abgebrochen: {fehler}")
        print(f"Protokoll dieser Sitzung: {protokollierer.pfad}")
        print("Nach Behebung (z.B. /usage-credits oder /model in Claude Code prüfen) chat.py einfach neu starten.")
        return None

    if state.abgebrochen:
        protokollierer.eintrag("abgebrochen")
        return state  # Abbruchbestätigung hat das LLM bereits selbst über breche_planung_ab formuliert

    # state.abgeschlossen == True: plane_reise_und_abschliessen (Tool) hat die Reise bereits
    # geplant, gespeichert und ggf. per Mail verschickt (siehe agent_tools.py). Der Reiseplan wird
    # hier NOCHMAL direkt (nicht vom LLM nacherzählt) ausgegeben – Grundprinzip 1: die strukturierten
    # Fakten kommen unverändert aus dem regelbasierten Layer, nicht als Paraphrase des Sprachmodells.
    protokollierer.eintrag("reiseanfrage_abgeschlossen", reiseanfrage=state.anfrage.als_dict())
    if state.reiseplan is not None:
        if state.nachhaltigkeits_nudge:
            print(state.nachhaltigkeits_nudge)
        print(als_text(state.reiseplan))
        protokollierer.eintrag(
            "reiseplan_erstellt", reiseplan_text=als_text(state.reiseplan),
            nachhaltigkeits_nudge=state.nachhaltigkeits_nudge,
        )
        for meldung in state.abschluss_meldungen:
            print(meldung)
    return state


if __name__ == "__main__":
    asyncio.run(hauptablauf())

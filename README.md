# Reisebot-Prototyp

Prototyp für die Masterarbeit „Reiseplanung mit generativer KI" (Nick Pöppler, Uni Hildesheim).
Verbindliche Architektur-/Projektregeln stehen in [`../CLAUDE.md`](../CLAUDE.md) (dauerhafter
Kontext, gilt für jede Arbeit an diesem Projekt); nicht-triviale Design-Entscheidungen samt
Begründung stehen chronologisch in [`ENTSCHEIDUNGSLOG.md`](ENTSCHEIDUNGSLOG.md).

## Ausführen

```
python chat.py                        # interaktiver Chat (Tastatur oder Mikrofon, siehe .env)
uvicorn webapp:app                    # derselbe Chat als Browser-Oberfläche, siehe unten (KEIN --reload, siehe dort)
python pruefe_planung.py <name>       # NUR die Planung testen (kein Dialog/LLM), siehe unten
python -m pytest                      # automatisierte Tests (deterministisch, ohne LLM-Kosten)
```

Voraussetzung für alle drei ersten: eine Claude-Code-Anmeldung/Abo (kein separater
`ANTHROPIC_API_KEY` nötig) sowie – für echte statt Beispieldaten – die Keys aus `.env.example` in
einer eigenen `.env`.

### Browser-Oberfläche (`webapp.py`)

`uvicorn webapp:app` startet einen lokalen Server (Standard: http://127.0.0.1:8000/) mit demselben
Dialog wie `chat.py` (dieselbe `hauptablauf`-Funktion, nur über WebSocket statt Konsole angesteuert,
siehe `webapp.py`). Zusätzlich zum reinen Chat zeigt der fertige Reiseplan am Ende Karten mit Foto,
Kurzbeschreibung und Google-Maps-Link je Unterkunft/POI (Fotos werden dafür serverseitig
heruntergeladen, siehe `src/ausgabe/fotos.py` – der Google-Maps-API-Key bleibt dabei ausschließlich
serverseitig, der Browser bekommt ihn nie zu sehen). Ohne echten Key (`MOCK_MODE` aktiv) erscheinen
die Karten ohne Foto ("Kein Foto verfügbar") statt eines erfundenen Bildes.

**Bewusst KEIN `--reload`:** unter Windows wechselt Uvicorns Reload-Modus intern von der
ProactorEventLoop auf die SelectorEventLoop (Subprozess-fähig ist unter Windows nur Erstere) – das
Claude Agent SDK startet beim Verbindungsaufbau aber die Claude-Code-CLI als Subprozess und würde
dann mit `NotImplementedError` abbrechen. Nach Codeänderungen den Server daher manuell neu starten
(`Strg+C`, dann erneut `uvicorn webapp:app`).

## Was liegt wo

| Pfad | Inhalt |
|---|---|
| `chat.py` | Einstiegspunkt für den interaktiven Chat (Konsole/Mikrofon). |
| `webapp.py` | Einstiegspunkt für dieselbe Dialoglogik als Browser-Oberfläche (FastAPI + WebSocket), inkl. Foto-Karten im fertigen Reiseplan. |
| `static/index.html` | Chat-Oberfläche + Ergebnis-Karten für `webapp.py` (eine einzelne, abhängigkeitsfreie HTML-Datei). |
| `pruefe_planung.py` | Testet NUR die deterministische Planung (POI-Suche, Optimierung 1+2) direkt, OHNE Dialog/LLM – baut eine `ReiseAnfrage` direkt aus `planungs_testfaelle/*.json`. Schneller (Sekunden statt Minuten), zuverlässigerer Standardweg zum Testen von Planungsänderungen – siehe ENTSCHEIDUNGSLOG.md, Phase 25. |
| `src/` | Der eigentliche Quellcode (siehe Architektur-Schema unten). |
| `tests/` | Automatisierte Tests; `tests/conftest.py` dokumentiert, welche Datei welche Tests hat und warum. |
| `evaluierung/` | Unabhängige Korrektheitsprüfung von Optimierung 1 gegen Google OR-Tools + Brute-Force (siehe [`evaluierung/README.md`](evaluierung/README.md)) – für die Evaluation der Masterarbeit, kein Teil des normalen Testlaufs. |
| `planungs_testfaelle/*.json` | Vorbereitete `ReiseAnfrage`-Felder für `pruefe_planung.py` (Feldname → Wert, kein Dialog). ACHTUNG: die ursprünglichen Testfälle (u.a. `klettern_essen`, `Annegret`, `Jakob`, `Thomas`) sind aktuell nicht mehr vorhanden (siehe ENTSCHEIDUNGSLOG.md, "Offene Punkte") – nur `smoketest_etappen.json` liegt derzeit hier. |
| `ergebnisse/` | Generierte Reisepläne (Text, JSON, POI-Übersicht als CSV) – EIN Satz Dateien pro Sitzung/Testfall, benannt nach `ausgabe_basisname` (z.B. `reiseplan_chat.*`, `reiseplan_<testfall>.*`). `ergebnisse/fotos/<sitzung_id>/` enthält zusätzlich die von `webapp.py` heruntergeladenen Places-Fotos einer Browser-Sitzung. Nicht eingecheckt (siehe `.gitignore`), jederzeit neu erzeugbar. |
| `protokolle/` | Ein JSONL-Log pro Sitzung mit jedem Werkzeug-Aufruf (Nachvollziehbarkeit). Enthält reale Nutzerantworten (Name, E-Mail, ggf. Gesundheitsangaben) – nicht eingecheckt. Daneben `<basisname>_debug.txt` je Planung (chat.py/webapp.py UND `pruefe_planung.py`, siehe `src/ausgabe/debug.py`): rohe/gefilterte/an Optimierung 1 weitergegebene POIs sowie Optimierung-1- und Monte-Carlo-Härtetest-Eingabe/-Ergebnis – zur direkten Prüfung, ob die Algorithmen mit sinnvollen Daten arbeiten. |
| `requirements.txt` | Kern-Abhängigkeiten (immer nötig). |
| `requirements-audio.txt` | Zusätzliche Abhängigkeiten NUR für `AUDIO_MODUS=true` (Sprachein-/ausgabe) – separat, damit sie nicht installiert werden müssen, wer den Textmodus nutzt. |
| `requirements-evaluierung.txt` | Zusätzliche Abhängigkeit (Google OR-Tools) NUR für `evaluierung/` – separat, kein Teil des normalen Programmbetriebs. |
| `.env` / `.env.example` | Konfiguration/API-Keys (siehe `.env.example` für alle bekannten Variablen). `.env` selbst ist nicht eingecheckt. |
| `ENTSCHEIDUNGSLOG.md` | Chronologisches Was/Warum aller nicht-trivialen Design-Entscheidungen – Grundlage für die Masterarbeit. |
| `doku/` | Dieselben Design-Entscheidungen, aber nach Entwicklungsstationen sortiert statt chronologisch – je Station eine README (Was/Warum/verworfene Alternativen), wo möglich mit echtem Code-Duplikat des damaligen Stands (`code_stand/`). Siehe [`doku/README.md`](doku/README.md). |

## Architektur auf einen Blick

Ein LLM-Agent (Claude Agent SDK) führt den Dialog eigenverantwortlich über fünf Werkzeuge
(`src/fragekatalog/agent_tools.py`); alle Fakten und die eigentliche Reiseplanung
(Optimierung 1+2, Monte-Carlo-Härtetest) bleiben strikt regelbasiert und deterministisch – siehe
[Architektur-Schema (Artifact)](https://claude.ai/code/artifact/f8cd86d0-c931-4db9-b5ae-70fabdbf45cf)
für den vollständigen Anfrage-Fluss durch die vier Schichten, oder direkt `CLAUDE.md`, Abschnitt
„Dialogsteuerung".

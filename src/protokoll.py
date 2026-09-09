"""
Prompt-Protokoll: schreibt jeden LLM-Aufruf (vollständiger Prompt +
vollständige Antwort) sowie die wichtigsten Sitzungsmeilensteine persistent
mit, damit nachvollziehbar bleibt, wie der Bot zu einem Ergebnis gekommen
ist. Grund: Reproduzierbarkeit für die Masterarbeit (Fehleranalyse bei der
Evaluation, Beleg für die deklarierte KI-Nutzung gemäß Uni-Vorgaben, siehe
CLAUDE.md/system_prompt_reisebot_team_2.md).

Ein Protokoll pro Chat-Sitzung: `protokolle/chat_<Zeitstempel>.jsonl`, eine
JSON-Zeile pro Eintrag (JSON Lines – einfach nachträglich mit Python/jq
auswertbar, z.B. "wie oft musste nachgefragt werden?").

Die Protokolldateien werden bewusst NICHT eingecheckt (siehe .gitignore):
sie enthalten die tatsächlichen Nutzerantworten aus Testläufen, potenziell
inkl. sensibler Angaben (Name, E-Mail, Gesundheitsangaben aus F09) und sind
damit personenbezogene Daten, keine Projektartefakte.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROTOKOLL_VERZEICHNIS = Path(__file__).resolve().parent.parent / "protokolle"


@dataclass
class Protokollierer:
    """Schreibt strukturierte Log-Einträge einer Sitzung fortlaufend in eine JSONL-Datei."""

    pfad: Path

    @classmethod
    def neue_sitzung(cls, praefix: str = "chat") -> Protokollierer:
        """Legt eine neue, zeitstempelbenannte Protokolldatei für eine Sitzung an."""
        PROTOKOLL_VERZEICHNIS.mkdir(exist_ok=True)
        zeitstempel = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return cls(pfad=PROTOKOLL_VERZEICHNIS / f"{praefix}_{zeitstempel}.jsonl")

    def eintrag(self, typ: str, **felder: Any) -> None:
        """Hängt einen Eintrag an. `typ` z.B. 'sitzung_start', 'tool_aufruf', 'reiseanfrage_abgeschlossen'
        (siehe agent_tools.py/chat.py für die tatsächlich verwendeten Typen)."""
        zeile = {"zeitstempel": datetime.now().isoformat(timespec="seconds"), "typ": typ, **felder}
        with self.pfad.open("a", encoding="utf-8") as datei:
            datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")

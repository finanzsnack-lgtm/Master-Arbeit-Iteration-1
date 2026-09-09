"""
Tests für den Fragekatalog und das ReiseAnfrage-Schema.

Die frühere regelbasierte Dialogschleife (zustandsmaschine.py::Dialogschleife/
RegelbasierterInterpreter) wurde am 11.08. entfernt (siehe ENTSCHEIDUNGSLOG.md,
"Architekturwechsel: LLM-autonome Dialogsteuerung") – die Ablaufsteuerung ist
jetzt Teil der LLM-Agenten-Session (siehe tests/test_agent_tools.py für die
deterministisch testbaren Werkzeuge). Diese Datei behält nur die Tests, die
unabhängig von der Ablaufsteuerung gültig bleiben: Konsistenz von Katalog und
Schema sowie die reinen `ReiseAnfrage`-Methoden.
"""
from src.fragekatalog.katalog import FRAGEKATALOG
from src.fragekatalog.schema import ReiseAnfrage


def test_katalog_und_schema_felder_stimmen_ueberein():
    schema_felder = set(ReiseAnfrage.__dataclass_fields__.keys())
    for frage in FRAGEKATALOG:
        assert frage.feld in schema_felder, f"Feld '{frage.feld}' fehlt im Schema (siehe schema.py)."


def test_ueberspringbare_fragen_sind_niemals_pflichtfelder():
    # Eine Pflichtfrage darf nicht übersprungen werden können (siehe katalog.py `ueberspringbar`) –
    # sonst könnte ein Pflichtfeld am Ende unbeantwortet bleiben.
    for frage in FRAGEKATALOG:
        if frage.ueberspringbar:
            assert not frage.pflichtfeld, f"{frage.id} ist ueberspringbar, aber gleichzeitig Pflichtfeld."


def test_sicherheit_bedenklich_default_false():
    # sicherheit_bedenklich wird vom LLM aus dem Gesprächskontext gesetzt (Tool-Argument bei
    # speichere_feld, siehe agent_tools.py), nicht per Schlüsselwort-Heuristik hergeleitet – hier
    # nur der Default ohne jede Angabe.
    assert ReiseAnfrage().sicherheit_bedenklich is False


def test_barrierefreiheit_oder_eingeschraenkt_ohne_angabe_false():
    # mobilitaetseinschraenkung_stufe wird vom LLM aus dem GESAMTEN Gesprächskontext gesetzt (Tool-
    # Argument bei speichere_feld, siehe agent_tools.py) – ERSETZT die frühere Schlüsselwort-Suche
    # über F09/F10/F15-Texte (siehe ENTSCHEIDUNGSLOG.md: konnte unbemerkt leerlaufen, wenn die
    # Antwort sinngemäß, aber nicht wörtlich passend formuliert war). Hier nur der Default.
    assert ReiseAnfrage().barrierefreiheit_oder_eingeschraenkt() is False


def test_barrierefreiheit_oder_eingeschraenkt_liefert_gesetztes_flag():
    # JEDE der drei Stufen zählt bereits als "eingeschränkt" (siehe schema.py) – nur die konkrete
    # Filterstrenge unterscheidet sich (siehe test_vertraeglichkeit.py).
    assert ReiseAnfrage(mobilitaetseinschraenkung_stufe="leicht").barrierefreiheit_oder_eingeschraenkt() is True
    assert ReiseAnfrage(mobilitaetseinschraenkung_stufe="stark").barrierefreiheit_oder_eingeschraenkt() is True

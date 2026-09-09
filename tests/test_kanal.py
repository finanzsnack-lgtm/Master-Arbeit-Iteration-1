"""Tests für die IOKanal-Implementierungen (src/audio/kanal.py) – nur die reinen, ohne echtes
Mikrofon/Konsole testbaren Teile: `TextKanal`/`AudioKanal.zeige_karte` sind No-Ops (Fotos lassen
sich in der Konsole ohnehin nicht darstellen, siehe Moduldoku)."""
import asyncio

from src.api.typen import Unterkunft
from src.audio.kanal import TextKanal


def test_textkanal_zeige_karte_ist_no_op_und_wirft_nicht():
    kanal = TextKanal()
    unterkunft = Unterkunft(id=1, name="Hotel Zentral", x=0.0, y=0.0, preisniveau=2, zertifiziert_nachhaltig=False)
    asyncio.run(kanal.zeige_karte(unterkunft))  # darf nicht werfen

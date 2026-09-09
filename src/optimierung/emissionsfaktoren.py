"""
Feste, zitierfähige CO2-Emissionsfaktoren je Verkehrsmittel (siehe
CLAUDE.md, Abschnitt "Optimierung 2"). Die hier hinterlegten Werte sind
Platzhalter aus gängigen Faustwerten und MÜSSEN vor Verwendung in der
Masterarbeit an einer offiziellen Quelle (z.B. Umweltbundesamt) verifiziert
werden (siehe CLAUDE.md: "Werte vor Verwendung an offizieller Quelle
verifizieren"). Climatiq wurde bewusst NICHT angebunden (Projektentscheidung:
feste, zitierfähige Tabelle statt Live-API für die CO2-Faktoren).
"""
from __future__ import annotations

# Gramm CO2-Äquivalent pro Personenkilometer (Pkm).
EMISSIONSFAKTOREN_G_PRO_PKM: dict[str, float] = {
    "bahn": 19.0,  # CLAUDE.md: "Bahn-Fernverkehr grob ~19 g/Pkm" – TODO: UBA-Quelle verifizieren
    "auto": 168.0,  # Platzhalter (durchschnittlicher PKW, 1 Person) – TODO: UBA-Quelle verifizieren
    "fernbus": 32.0,  # Platzhalter – TODO: UBA-Quelle verifizieren
}


def co2_kg(verkehrsmittel: str, distanz_km: float) -> float:
    """Berechnet die CO2-Emission einer Strecke: Distanz × Emissionsfaktor."""
    faktor = EMISSIONSFAKTOREN_G_PRO_PKM.get(verkehrsmittel.lower())
    if faktor is None:
        raise ValueError(f"Kein Emissionsfaktor für Verkehrsmittel '{verkehrsmittel}' hinterlegt.")
    return distanz_km * faktor / 1000  # g -> kg

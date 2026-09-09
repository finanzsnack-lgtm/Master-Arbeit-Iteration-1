"""Tests für die CO2-Emissionsfaktoren (src/optimierung/emissionsfaktoren.py)."""
import pytest

from src.optimierung.emissionsfaktoren import co2_kg


def test_auto_hat_deutlich_hoeheren_faktor_als_bahn():
    # Kernaussage des Nachhaltigkeits-Nudges (CLAUDE.md, Grundprinzip 5): Auto muss bei gleicher
    # Distanz klar mehr CO2 verursachen als Bahn.
    distanz_km = 1000
    assert co2_kg("auto", distanz_km) > co2_kg("bahn", distanz_km)


def test_unbekanntes_verkehrsmittel_wirft_fehler_statt_zu_erfinden():
    with pytest.raises(ValueError):
        co2_kg("rakete", 100)

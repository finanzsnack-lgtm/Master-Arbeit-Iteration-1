"""
Sammelt POIs aus ALLEN zuständigen Quellen für eine Reiseanfrage: Google
Places (immer) plus – nur falls der LLM-Agent das für nötig befunden hat
(siehe ReiseAnfrage.aktivitaeten_mit_spezialrecherche, agent_tools.py
`hole_api_daten` Argument `spezialrecherche_aktivitaeten`) – die Overpass-
Spezialrecherche für Aktivitäten wie Klettern/Wandern (src/api/overpass.py).

An EINER Stelle gepflegt (analog zu pipeline.py-Docstring), weil sowohl der
Live-Vorschlag während des Dialogs (vorschlaege.py, Knoten c1) als auch die
finale Planung (pipeline.py) dieselben POIs sehen müssen – sonst würde der
Nutzer im Chat andere Orte bestätigen als am Ende tatsächlich eingeplant
werden.
"""
from __future__ import annotations

from src.api.google_maps import MapsClient
from src.api.overpass import SpezialAktivitaetenClient, erzeuge_overpass_client
from src.api.typen import POI


def sammle_pois(
    ziel: str,
    aktivitaeten_interessen: list[str],
    aktivitaeten_mit_spezialrecherche: list[str],
    maps_client: MapsClient,
    overpass_client: SpezialAktivitaetenClient | None = None,
    radius_meter: int = 3000,
) -> list[POI]:
    """
    `overpass_client` ist injizierbar (Default: `erzeuge_overpass_client()`,
    Mock-/Live-Wahl anhand `.env`, siehe overpass.py) – v.a. für Tests, damit
    diese unabhängig vom lokalen `MOCK_MODE` deterministisch bleiben, statt
    bei `MOCK_MODE=false` versehentlich echte HTTP-Requests auszulösen.

    `radius_meter` (siehe aufbereitung.py `parameter_fuer_lokalen_transport`):
    reicht NUR an die Places-Suche durch – der Overpass-Suchradius bleibt
    unverändert groß (siehe overpass.py `_SUCHRADIUS_METER`), weil Kletter-/
    Wanderziele o.ä. typischerweise ohnehin außerhalb der Stadt liegen und
    einen eigenen Anfahrtsweg einplanen, unabhängig vom lokalen Fortbewegungs-
    mittel innerhalb der Stadt.
    """
    pois = list(maps_client.suche_pois(ziel, aktivitaeten_interessen, radius_meter=radius_meter))

    if aktivitaeten_mit_spezialrecherche:
        overpass_client = overpass_client or erzeuge_overpass_client()
        koordinaten = maps_client.geocode(ziel)
        gesehene_namen = {poi.name for poi in pois}
        for aktivitaet in aktivitaeten_mit_spezialrecherche:
            for poi in overpass_client.suche_spezial_pois(koordinaten, aktivitaet):
                if poi.name in gesehene_namen:  # Überschneidung mit Places möglich (z.B. Kletterhalle als "gym")
                    continue
                gesehene_namen.add(poi.name)
                pois.append(poi)

    return pois

"""Tests für src/api/overpass.py (Spezialrecherche für Klettern/Wandern/etc., siehe Projektkonversation)."""
from unittest.mock import patch

import requests

from src.api.overpass import MockOverpassClient, OverpassClient, _erster_vorhandener_tag, _waehle_alias


def test_waehle_alias_erkennt_bekannte_aktivitaeten():
    tag_filter, grad_kandidaten = _waehle_alias("Klettern gehen")
    assert tag_filter == '"sport"="climbing"'
    assert "climbing:grade:uiaa" in grad_kandidaten
    assert _waehle_alias("Ich möchte wandern") == ('"route"="hiking"', ("sac_scale",))


def test_waehle_alias_liefert_none_fuer_unbekannte_aktivitaet():
    assert _waehle_alias("Kultur") is None
    assert _waehle_alias("Kulinarik") is None


def test_mock_overpass_client_liefert_beispiel_poi_mit_schwierigkeitsgrad():
    client = MockOverpassClient()
    treffer = client.suche_spezial_pois((48.0, 11.0), "Klettern")
    assert len(treffer) == 1
    assert treffer[0].quelle == "osm_overpass"
    assert treffer[0].schwierigkeitsgrad == "6a"


def test_mock_overpass_client_liefert_leere_liste_fuer_unbekannte_aktivitaet():
    client = MockOverpassClient()
    assert client.suche_spezial_pois((48.0, 11.0), "Museumsbesuch") == []


def test_erster_vorhandener_tag_nimmt_ersten_treffer_in_prioritaetsreihenfolge():
    # OSM taggt Schwierigkeitsgrade uneinheitlich (siehe Moduldoku) – der
    # erste in der Kandidatenliste tatsächlich vorhandene Tag gewinnt.
    tags = {"climbing:grade:uiaa:min": "4", "climbing:grade:french": "5a"}
    assert _erster_vorhandener_tag(tags, ("climbing:grade:uiaa", "climbing:grade:uiaa:min", "climbing:grade:french")) == "4"


def test_erster_vorhandener_tag_liefert_none_ohne_treffer():
    assert _erster_vorhandener_tag({"name": "x"}, ("sac_scale",)) is None


@patch("src.api.overpass.requests.post")
def test_overpass_client_fehlerhafte_antwort_wird_abgefangen_statt_absturz(mock_post):
    # Regression: der öffentliche Overpass-Server antwortet unter Last auch mal mit 504/Timeout
    # (live beobachtet, siehe Projektkonversation) – das darf NICHT die gesamte Planung crashen.
    mock_post.side_effect = requests.exceptions.HTTPError("504 Server Error: Gateway Timeout")
    client = OverpassClient()

    treffer = client.suche_spezial_pois((48.1372, 11.5755), "Klettern")

    assert treffer == []  # ehrlicher Fallback statt erfundenem Ersatztreffer (Grundprinzip 1)


@patch("src.api.overpass.requests.post")
def test_overpass_client_timeout_wird_abgefangen_statt_absturz(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout("timed out")
    client = OverpassClient()

    assert client.suche_spezial_pois((48.1372, 11.5755), "Wandern") == []

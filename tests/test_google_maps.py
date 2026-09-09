"""
Tests für die NICHT-netzwerkabhängigen Teile von `GoogleMapsClient`
(src/api/google_maps.py). Die eigentlichen HTTP-Aufrufe werden per
unittest.mock simuliert, da kein echter Google-Maps-Key vorliegt (siehe
Moduldoku dort: die Anbindung ist implementiert, aber noch nicht live
getestet). MockGoogleMapsClient (der Mock-Modus für den Rest des Programms)
wird hier NICHT getestet, sondern nur der echte `GoogleMapsClient`.
"""
from unittest.mock import Mock, patch

import pytest

from src.api.google_maps import GoogleMapsClient


def test_client_ohne_key_wirft_fehler():
    with pytest.raises(ValueError):
        GoogleMapsClient(api_key="")


def _mock_antwort(json_daten: dict) -> Mock:
    antwort = Mock()
    antwort.json.return_value = json_daten
    antwort.raise_for_status.return_value = None
    return antwort


@patch("src.api.google_maps.requests.get")
def test_geocode_parst_koordinaten_aus_antwort(mock_get):
    mock_get.return_value = _mock_antwort({
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 48.1372, "lng": 11.5755}}}],
    })
    client = GoogleMapsClient(api_key="dummy-key")

    lat, lng = client.geocode("München")

    assert (lat, lng) == (48.1372, 11.5755)
    aufgerufene_url = mock_get.call_args.args[0]
    assert "geocode/json" in aufgerufene_url
    assert mock_get.call_args.kwargs["params"]["key"] == "dummy-key"
    # Regressionsschutz: ohne language=de kamen Ortsnamen in Zufallssprache zurück (siehe Moduldoku).
    assert mock_get.call_args.kwargs["params"]["language"] == "de"


@patch("src.api.google_maps.requests.get")
def test_geocode_ohne_treffer_wirft_fehler(mock_get):
    mock_get.return_value = _mock_antwort({"status": "ZERO_RESULTS", "results": []})
    client = GoogleMapsClient(api_key="dummy-key")

    with pytest.raises(ValueError):
        client.geocode("Nirgendwo")


@patch("src.api.google_maps.requests.get")
def test_get_wirft_bei_fehlerstatus_laufzeitfehler(mock_get):
    mock_get.return_value = _mock_antwort({"status": "REQUEST_DENIED", "error_message": "ungültiger Key"})
    client = GoogleMapsClient(api_key="dummy-key")

    with pytest.raises(RuntimeError, match="REQUEST_DENIED"):
        client.geocode("München")


@patch("src.api.google_maps.requests.get")
def test_reisealternativen_ueberspringt_route_ohne_verbindung(mock_get):
    # Simuliert: Bahn/Fernbus liefern keine Route (z.B. keine Zugverbindung),
    # nur Auto liefert eine gültige Route.
    def antworten_je_aufruf(*args, **kwargs):
        modus = kwargs["params"].get("mode")
        if modus == "driving":
            return _mock_antwort({
                "status": "OK",
                "routes": [{"legs": [{
                    "duration": {"value": 7200}, "distance": {"value": 300000},
                }]}],
            })
        return _mock_antwort({"status": "ZERO_RESULTS", "routes": []})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    alternativen = client.reisealternativen("Berlin", "München")

    assert len(alternativen) == 1
    assert alternativen[0].verkehrsmittel == "Auto"
    assert alternativen[0].dauer_minuten == 120
    assert alternativen[0].distanz_km == 300


@patch("src.api.google_maps.requests.get")
def test_reisealternativen_bahn_liefert_teilstrecken_mit_umstieg(mock_get):
    # BEHOBENER BUG (siehe Projektkonversation: "nicht nur sagen mit Bahn brauchst du eine
    # Stunde, sondern 30 min dahin, dann umsteigen mit 5 min Wartezeit, dann 25 min Fahrzeit"):
    # `_hole_route` warf `legs[0].steps` bisher komplett weg. Simuliert eine Bahnfahrt mit
    # einem Umstieg: ICE Berlin -> Fulda (Ankunft 10:00), 5 min Wartezeit, RE Fulda -> München
    # (Abfahrt 10:05).
    def antworten_je_aufruf(*args, **kwargs):
        modus = kwargs["params"].get("mode")
        if modus != "transit" or kwargs["params"].get("transit_mode") != "rail":
            return _mock_antwort({"status": "ZERO_RESULTS", "routes": []})
        return _mock_antwort({
            "status": "OK",
            "routes": [{"legs": [{
                "duration": {"value": 3600}, "distance": {"value": 300000},
                "steps": [
                    {
                        "travel_mode": "TRANSIT", "duration": {"value": 1800},
                        "transit_details": {
                            "line": {"short_name": "ICE 123"},
                            "departure_stop": {"name": "Berlin Hbf"},
                            "arrival_stop": {"name": "Fulda"},
                            "departure_time": {"value": 1000},
                            "arrival_time": {"value": 1000 + 1800},
                        },
                    },
                    {
                        "travel_mode": "TRANSIT", "duration": {"value": 1500},
                        "transit_details": {
                            "line": {"short_name": "RE 456"},
                            "departure_stop": {"name": "Fulda"},
                            "arrival_stop": {"name": "München Hbf"},
                            "departure_time": {"value": 1000 + 1800 + 300},
                            "arrival_time": {"value": 1000 + 1800 + 300 + 1500},
                        },
                    },
                ],
            }]}],
        })

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    alternativen = client.reisealternativen("Berlin", "München")

    bahn = next(a for a in alternativen if a.verkehrsmittel == "Bahn")
    assert len(bahn.teilstrecken) == 2
    erste, zweite = bahn.teilstrecken
    assert erste.linie == "ICE 123"
    assert erste.von == "Berlin Hbf"
    assert erste.nach == "Fulda"
    assert erste.dauer_minuten == 30
    assert erste.wartezeit_minuten is None  # keine vorherige Teilstrecke
    assert zweite.linie == "RE 456"
    assert zweite.wartezeit_minuten == 5  # Lücke zwischen Ankunft ICE und Abfahrt RE


@patch("src.api.google_maps.requests.get")
def test_anfahrtszeiten_minuten_liest_erste_zeile_der_matrix(mock_get):
    # EIN Ursprung -> N Ziele: nur rows[0] ist relevant (siehe Moduldoku dort).
    mock_get.return_value = _mock_antwort({
        "status": "OK",
        "rows": [{"elements": [
            {"duration": {"value": 600}},
            {"status": "ZERO_RESULTS"},  # kein duration-Feld -> -1
            {"duration": {"value": 1200}},
        ]}],
    })
    client = GoogleMapsClient(api_key="dummy-key")

    dauern = client.anfahrtszeiten_minuten((48.0, 11.0), [(48.1, 11.1), (48.2, 11.2), (48.3, 11.3)], modus="walking")

    assert dauern == [10, -1, 20]
    assert mock_get.call_args.kwargs["params"]["origins"] == "48.0,11.0"
    assert mock_get.call_args.kwargs["params"]["destinations"] == "48.1,11.1|48.2,11.2|48.3,11.3"
    assert mock_get.call_args.kwargs["params"]["mode"] == "walking"


def test_anfahrtszeiten_minuten_ohne_ziele_ueberspringt_api_aufruf():
    client = GoogleMapsClient(api_key="dummy-key")
    assert client.anfahrtszeiten_minuten((48.0, 11.0), []) == []


@patch("src.api.google_maps.requests.get")
def test_suche_pois_sucht_woertlich_nach_jedem_interesse_ohne_feste_kategorie(mock_get):
    # BEHOBENER BUG (siehe Projektkonversation: "ich möchte klettern, nicht ins Gym – das darf auf
    # gar keinen Fall passieren"): vorher wurde jedes Interesse auf einen von Googles ~100 FESTEN
    # Place Types gepresst (z.B. "Klettern" -> "gym"). Jetzt geht der Interesse-Wortlaut UNVERÄNDERT
    # als Freitext-Query in eine Places Text Search – funktioniert auch für Interessen, die keinem
    # festen Place Type entsprechen (z.B. "über Brücken spazieren gehen").
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": []})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    client.suche_pois("München", ["Klettern", "über Brücken spazieren gehen"])

    text_search_aufrufe = [a for a in mock_get.call_args_list if "textsearch" in a.args[0]]
    assert len(text_search_aufrufe) == 2
    queries = {a.kwargs["params"]["query"] for a in text_search_aufrufe}
    assert queries == {"Klettern in München", "über Brücken spazieren gehen in München"}
    # NIRGENDS ein fester "type"-Parameter mehr (anders als Nearby Search vorher).
    assert all("type" not in a.kwargs["params"] for a in text_search_aufrufe)


@patch("src.api.google_maps.requests.get")
def test_distanzmatrix_teilt_in_kacheln_auf_bei_vielen_orten(mock_get):
    # Regression (siehe Projektkonversation: "die Zeiten sind falsch" -> live MAX_ELEMENTS_EXCEEDED
    # bei einer vollen NxN-Anfrage mit vielen POIs): ab mehr als `_DISTANCE_MATRIX_KACHEL` Orten
    # muss die Anfrage in mehrere kleinere Kacheln aufgeteilt werden.
    orte = [(float(i), 0.0) for i in range(12)]  # 12 > _DISTANCE_MATRIX_KACHEL (10)

    def antworten_je_aufruf(url, params=None, timeout=None):
        anzahl_origins = len(params["origins"].split("|"))
        anzahl_destinations = len(params["destinations"].split("|"))
        rows = [
            {"elements": [{"duration": {"value": 60}} for _ in range(anzahl_destinations)]}
            for _ in range(anzahl_origins)
        ]
        return _mock_antwort({"status": "OK", "rows": rows})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    matrix = client.distanzmatrix(orte, modus="driving")

    assert len(matrix) == 12
    assert all(len(zeile) == 12 for zeile in matrix)
    assert all(wert == 1 for zeile in matrix for wert in zeile)  # 60s -> 1 Minute
    # Mehr als EIN Aufruf, weil 12 Orte über der Kachelgröße liegen.
    assert mock_get.call_count > 1


@patch("src.api.google_maps.requests.get")
def test_suche_pois_setzt_ernaehrungspraeferenz_nur_bei_essen_bezogenem_interesse(mock_get):
    # Regression (siehe Projektkonversation: "wenn eine Ernährungspräferenz geäußert wird, müssen
    # die ausgewählten Restaurants den Ausprägungen angepasst werden") – die Präferenz landet NUR
    # in der Query für essen-bezogene Interessen, nicht z.B. für "Klettern".
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": []})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    client.suche_pois("München", ["Restaurants", "Klettern"], ernaehrung_einschraenkungen=["vegetarisch"])

    text_search_aufrufe = [a for a in mock_get.call_args_list if "textsearch" in a.args[0]]
    queries = {a.kwargs["params"]["query"] for a in text_search_aufrufe}
    assert "vegetarisch Restaurants in München" in queries
    assert "Klettern in München" in queries  # unverändert, keine Ernährungspräferenz bei Klettern


@patch("src.api.google_maps.requests.get")
def test_suche_pois_ohne_interessen_ruft_api_nicht_auf(mock_get):
    client = GoogleMapsClient(api_key="dummy-key")
    assert client.suche_pois("München", []) == []
    mock_get.assert_not_called()


@patch("src.api.google_maps.requests.get")
def test_suche_pois_taggt_treffer_mit_dem_gesuchten_interesse(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        if params["query"] == "Klettern in München":
            return _mock_antwort({"status": "OK", "results": [{
                "name": "Boulderhalle Nordwand", "place_id": "p1", "types": ["gym"],
                "geometry": {"location": {"lat": 48.1, "lng": 11.1}},
            }]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Trattoria Roma", "place_id": "p2", "types": ["restaurant"],
            "geometry": {"location": {"lat": 48.2, "lng": 11.2}},
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    pois = client.suche_pois("München", ["Klettern", "Restaurants"])

    boulderhalle = next(p for p in pois if p.name == "Boulderhalle Nordwand")
    restaurant = next(p for p in pois if p.name == "Trattoria Roma")
    assert boulderhalle.nutzerinteresse == "Klettern"
    assert restaurant.nutzerinteresse == "Restaurants"


@patch("src.api.google_maps.requests.get")
def test_suche_pois_nutzt_uebergebenen_radius(mock_get):
    # Der Suchradius richtet sich auf das lokale Fortbewegungsmittel (F14, siehe aufbereitung.py
    # `parameter_fuer_lokalen_transport`) – Regressionsschutz gegen den zuvor hartcodierten Wert.
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": []})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    client.suche_pois("München", ["Kultur"], radius_meter=8000)

    text_search_aufrufe = [a for a in mock_get.call_args_list if "textsearch" in a.args[0]]
    assert text_search_aufrufe
    assert all(a.kwargs["params"]["radius"] == 8000 for a in text_search_aufrufe)


@patch("src.api.google_maps.requests.get")
def test_suche_unterkuenfte_gibt_praeferenz_text_als_keyword_weiter(mock_get):
    # "Vorstellungen" aus F15 sollen Googles eigene Relevanzsuche steuern (siehe Moduldoku dort),
    # nicht ein selbstgebautes Text-Matching.
    mock_get.return_value = _mock_antwort({"status": "OK", "results": []})
    client = GoogleMapsClient(api_key="dummy-key")
    # geocode() nutzt denselben Mock -> zweiter Aufruf ist die eigentliche Nearby-Search.

    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": []})

    mock_get.side_effect = antworten_je_aufruf

    client.suche_unterkuenfte("München", praeferenz_text="ruhige Lage mit Balkon")

    nearby_aufruf = mock_get.call_args_list[1]
    assert nearby_aufruf.kwargs["params"]["keyword"] == "ruhige Lage mit Balkon"


@patch("src.api.google_maps.requests.get")
def test_ist_barrierefrei_liest_wheelchair_accessible_entrance(mock_get):
    mock_get.return_value = _mock_antwort({"status": "OK", "result": {"wheelchair_accessible_entrance": True}})
    client = GoogleMapsClient(api_key="dummy-key")

    assert client.ist_barrierefrei("abc123") is True
    aufgerufene_url = mock_get.call_args.args[0]
    assert "place/details/json" in aufgerufene_url
    assert mock_get.call_args.kwargs["params"]["place_id"] == "abc123"
    assert mock_get.call_args.kwargs["params"]["fields"] == "wheelchair_accessible_entrance"


@patch("src.api.google_maps.requests.get")
def test_ist_barrierefrei_ohne_feld_in_antwort_liefert_none(mock_get):
    # Places hat dazu keine Angabe -> None statt eine Aussage zu erfinden (Grundprinzip 1).
    mock_get.return_value = _mock_antwort({"status": "OK", "result": {}})
    client = GoogleMapsClient(api_key="dummy-key")

    assert client.ist_barrierefrei("abc123") is None


def test_ist_barrierefrei_ohne_place_id_ueberspringt_api_aufruf():
    client = GoogleMapsClient(api_key="dummy-key")
    assert client.ist_barrierefrei(None) is None


@patch("src.api.google_maps.requests.get")
def test_suche_pois_uebernimmt_erste_foto_referenz(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Boulderhalle Nordwand", "place_id": "p1", "types": ["gym"],
            "geometry": {"location": {"lat": 48.1, "lng": 11.1}},
            "photos": [{"photo_reference": "foto-ref-1"}, {"photo_reference": "foto-ref-2"}],
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    pois = client.suche_pois("München", ["Klettern"])

    assert pois[0].foto_referenz == "foto-ref-1"  # nur die ERSTE Referenz, nicht alle


@patch("src.api.google_maps.requests.get")
def test_suche_pois_ohne_photos_laesst_foto_referenz_leer(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Boulderhalle Nordwand", "place_id": "p1", "types": ["gym"],
            "geometry": {"location": {"lat": 48.1, "lng": 11.1}},
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    pois = client.suche_pois("München", ["Klettern"])

    assert pois[0].foto_referenz is None  # kein erfundenes Foto (Grundprinzip 1)


@patch("src.api.google_maps.requests.get")
def test_suche_pois_uebernimmt_price_level(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Museum XY", "place_id": "p1", "types": ["museum"],
            "geometry": {"location": {"lat": 48.1, "lng": 11.1}}, "price_level": 3,
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    pois = client.suche_pois("München", ["Kultur"])

    assert pois[0].preisniveau == 3


@patch("src.api.google_maps.requests.get")
def test_suche_pois_ohne_price_level_laesst_preisniveau_leer(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Stadtpark", "place_id": "p1", "types": ["park"],
            "geometry": {"location": {"lat": 48.1, "lng": 11.1}},
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    pois = client.suche_pois("München", ["Natur"])

    assert pois[0].preisniveau is None  # kein erfundener Preis (Grundprinzip 1)


@patch("src.api.google_maps.requests.get")
def test_suche_unterkuenfte_uebernimmt_foto_referenz(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": [{
            "name": "Hotel Zentral", "place_id": "h1",
            "geometry": {"location": {"lat": 48.1, "lng": 11.1}},
            "photos": [{"photo_reference": "hotel-foto-1"}],
        }]})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    unterkuenfte = client.suche_unterkuenfte("München")

    assert unterkuenfte[0].foto_referenz == "hotel-foto-1"


@patch("src.api.google_maps.requests.get")
def test_lade_foto_schreibt_bilddatei_bei_erfolg(mock_get, tmp_path):
    antwort = Mock()
    antwort.raise_for_status.return_value = None
    antwort.content = b"fake-bilddaten"
    mock_get.return_value = antwort
    client = GoogleMapsClient(api_key="dummy-key")
    ziel_pfad = tmp_path / "foto.jpg"

    erfolg = client.lade_foto("foto-ref-1", str(ziel_pfad))

    assert erfolg is True
    assert ziel_pfad.read_bytes() == b"fake-bilddaten"
    assert "place/photo" in mock_get.call_args.args[0]
    assert mock_get.call_args.kwargs["params"]["photoreference"] == "foto-ref-1"


@patch("src.api.google_maps.requests.get")
def test_lade_foto_gibt_false_bei_fehler_statt_zu_werfen(mock_get, tmp_path):
    import requests

    mock_get.side_effect = requests.RequestException("Netzwerkfehler")
    client = GoogleMapsClient(api_key="dummy-key")

    erfolg = client.lade_foto("foto-ref-1", str(tmp_path / "foto.jpg"))

    assert erfolg is False
    assert not (tmp_path / "foto.jpg").exists()


@patch("src.api.google_maps.requests.get")
def test_suche_unterkuenfte_ohne_praeferenz_text_setzt_kein_keyword(mock_get):
    def antworten_je_aufruf(url, params=None, timeout=None):
        if "geocode" in url:
            return _mock_antwort({"status": "OK", "results": [{"geometry": {"location": {"lat": 48.0, "lng": 11.0}}}]})
        return _mock_antwort({"status": "OK", "results": []})

    mock_get.side_effect = antworten_je_aufruf
    client = GoogleMapsClient(api_key="dummy-key")

    client.suche_unterkuenfte("München")

    nearby_aufruf = mock_get.call_args_list[1]
    assert "keyword" not in nearby_aufruf.kwargs["params"]

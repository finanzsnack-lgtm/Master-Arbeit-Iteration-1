"""Tests für src/ausgabe/fotos.py (Foto-Download für die Web-UI, siehe webapp.py)."""
from src.api.typen import POI, ReiseAlternative
from src.ausgabe.fotos import lade_fotos_fuer_plan
from src.ausgabe.reiseplan import Reiseplan
from src.optimierung.toptw import Besuch, Tagesroute
from src.optimierung.verkehrsmittelwahl import BewerteteAlternative

_BAHN = BewerteteAlternative(
    alternative=ReiseAlternative(verkehrsmittel="Bahn", dauer_minuten=300, kosten_euro=80, distanz_km=500),
    co2_kg=9.5, score=0.1,
)


class _FakeClient:
    """Simuliert `MapsClient.lade_foto` – Erfolg NUR für place_ids in `funktionierende_ids`
    (referenzen folgen im Test der Konvention "ref-<place_id>"), damit sowohl der Erfolgs- als
    auch der ehrliche Fehlschlagsfall getestet werden kann."""

    def __init__(self, funktionierende_ids: set[str]):
        self._funktionierende_referenzen = {f"ref-{place_id}" for place_id in funktionierende_ids}
        self.aufrufe: list[tuple[str, str]] = []

    def lade_foto(self, foto_referenz: str, ziel_pfad: str, max_breite: int = 640) -> bool:
        self.aufrufe.append((foto_referenz, ziel_pfad))
        erfolgreich = foto_referenz in self._funktionierende_referenzen
        if erfolgreich:
            with open(ziel_pfad, "w", encoding="utf-8") as datei:
                datei.write("fake")
        return erfolgreich


def _basis_plan(**zusatz) -> Reiseplan:
    parameter = {"hinreise": _BAHN, "tagesrouten": [], "rueckreise": _BAHN}
    parameter.update(zusatz)
    return Reiseplan(**parameter)


def test_laedt_foto_fuer_unterkunft_und_eingeplante_pois(tmp_path):
    poi = POI(id=1, name="Kletterroute XY", kategorie="klettern", x=0.0, y=0.0, score=3.0,
              required_time=180, opening=0, closing=600, place_id="poi-1", foto_referenz="ref-poi-1")
    tag1 = Tagesroute(besuche=[Besuch(poi=poi, ankunft=15, wartezeit=0, abfahrt=195)])
    plan = _basis_plan(
        tagesrouten=[tag1], unterkunft_name="Hotel Zentral", unterkunft_place_id="hotel-1",
        unterkunft_foto_referenz="ref-hotel-1",
    )
    client = _FakeClient(funktionierende_ids={"hotel-1", "poi-1"})

    dateien = lade_fotos_fuer_plan(plan, client, tmp_path / "sitzung")

    assert dateien == {"hotel-1": "hotel-1.jpg", "poi-1": "poi-1.jpg"}
    assert (tmp_path / "sitzung" / "hotel-1.jpg").exists()
    assert (tmp_path / "sitzung" / "poi-1.jpg").exists()


def test_ueberspringt_pois_ohne_foto_referenz_oder_place_id(tmp_path):
    ohne_foto = POI(id=1, name="Ohne Foto", kategorie="museum", x=0.0, y=0.0, score=1.0,
                     required_time=60, opening=0, closing=600, place_id="poi-1")
    ohne_place_id = POI(id=2, name="Mock-POI", kategorie="park", x=0.0, y=0.0, score=1.0,
                         required_time=60, opening=0, closing=600, foto_referenz="ref-egal")
    tag1 = Tagesroute(besuche=[
        Besuch(poi=ohne_foto, ankunft=15, wartezeit=0, abfahrt=75),
        Besuch(poi=ohne_place_id, ankunft=80, wartezeit=0, abfahrt=140),
    ])
    plan = _basis_plan(tagesrouten=[tag1])
    client = _FakeClient(funktionierende_ids={"poi-1", "egal"})

    dateien = lade_fotos_fuer_plan(plan, client, tmp_path / "sitzung")

    assert dateien == {}
    assert client.aufrufe == []  # kein einziger Download-Versuch, da nie beides gesetzt war


def test_gescheiterter_download_landet_nicht_im_ergebnis(tmp_path):
    poi = POI(id=1, name="Kletterroute XY", kategorie="klettern", x=0.0, y=0.0, score=3.0,
              required_time=180, opening=0, closing=600, place_id="poi-1", foto_referenz="ref-poi-1")
    tag1 = Tagesroute(besuche=[Besuch(poi=poi, ankunft=15, wartezeit=0, abfahrt=195)])
    plan = _basis_plan(tagesrouten=[tag1])
    client = _FakeClient(funktionierende_ids=set())  # jeder Download schlägt fehl

    dateien = lade_fotos_fuer_plan(plan, client, tmp_path / "sitzung")

    assert dateien == {}


def test_weitere_empfehlungen_werden_nicht_heruntergeladen(tmp_path):
    # Bewusst NUR eingeplante POIs (Tagesrouten), nicht `weitere_aktivitaeten_empfehlungen` – siehe
    # Moduldoku: die sind kein Teil des konkreten Vorschlags.
    nicht_eingeplant = POI(id=2, name="Nicht eingeplant", kategorie="museum", x=0.0, y=0.0, score=1.0,
                            required_time=60, opening=0, closing=600, place_id="poi-2", foto_referenz="ref-poi-2")
    plan = _basis_plan(weitere_aktivitaeten_empfehlungen=[nicht_eingeplant])
    client = _FakeClient(funktionierende_ids={"poi-2"})

    dateien = lade_fotos_fuer_plan(plan, client, tmp_path / "sitzung")

    assert dateien == {}
    assert client.aufrufe == []

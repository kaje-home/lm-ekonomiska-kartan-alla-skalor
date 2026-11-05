"""Lantmateriets index over 1:20 000-bladen: Norrlands_Inland.shp.

Bara GDAL/OGR, inga QGIS-importer. Indexet ligger pa FTP:n i
`Norrlands_inland/` (sett 2026-11-04) och har en polygon per blad i SWEREF 99
TM med bladnummer (katalognamnet), bladnamn och ar. Det hamtas med
listningen och sparas bredvid den, i `index_20k/`.

Var position kommer fortfarande ur bladnamnet (blad.tolka_20k): de 966 hela
bladen ligger inom 0,2 m fran indexets (kontroll/prov_index.py). Indexet
tillfor tre saker:

* **Bladnamnet**, t.ex. "Mullberget", till bladrutnatet och rapporten.
* **Delbladen.** 80 blad vid seriegransen ar bara delvis 1:20 000: en, tva
  eller tre av bladets fyra 5 km-rutor, resten hor till 1:10 000-serien.
  Indexets polygon ar den delen. Uttaget klipper bladet mot den och later
  bladet ta bara de rutorna.
* **Kanterna mot seriegransen**: en kant dar ingen av de tva rutorna ar
  1:20 000. Dar kan kilometerstrecken saknas (rutnat_20k.georeferera_20k).

Indexets dbf ar i Windows-1252 och saknar ar som 0. Rutorna i polygonen
tas ur rutornas mittpunkter, sa att indexets avrundning inte spelar in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from osgeo import gdal, ogr, osr

from .lm_ekokarta_karna.blad import KATALOG_20K, ROT, Blad20k, tolka_20k
from .lm_ekokarta_karna.blad_alla import BLAD_M
from .lm_ekokarta_karna.filer import halvfardig
from .lm_ekokarta_karna.ftp import hamta_fil

NAMN = "Norrlands_Inland"
FILER = ("shp", "shx", "dbf", "prj")
MAPP = "index_20k"


@dataclass(frozen=True)
class Indexblad:
    bladnamn: str
    ar: int | None
    celler: frozenset           # 5 km-rutorna (minx, maxy i RT 90) som ar 1:20 000


def _celler_i_bladet(minx: float, maxy: float) -> list[tuple[float, float]]:
    return [(minx + dx, maxy - dy) for dx in (0.0, BLAD_M) for dy in (0.0, BLAD_M)]


class Index20k:
    def __init__(self, shp: str):
        ogr.UseExceptions()
        with gdal.config_options({"SHAPE_ENCODING": "CP1252"}):
            ds = ogr.Open(shp)
            lager = ds.GetLayer()
            src = lager.GetSpatialRef()
            rt90 = osr.SpatialReference()
            rt90.ImportFromEPSG(3021)
            for s in (src, rt90):
                s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            ct = osr.CoordinateTransformation(src, rt90)
            self.blad: dict[str, Indexblad] = {}
            for f in lager:
                kat = f.GetField("Bladnummer")
                g = f.GetGeometryRef().Clone()
                g.Transform(ct)
                try:
                    b = tolka_20k(kat)
                except ValueError:
                    continue
                celler = frozenset(
                    (x, y) for x, y in _celler_i_bladet(b.minx, b.maxy)
                    if g.Contains(ogr.CreateGeometryFromWkt(
                        f"POINT({x + BLAD_M / 2} {y - BLAD_M / 2})")))
                ar = f.GetField(3)          # "År"
                self.blad[kat] = Indexblad(f.GetField("Bladnamn") or "", ar or None, celler)
            ds = None

    def bladnamn(self, katalog: str) -> str:
        i = self.blad.get(katalog)
        return i.bladnamn if i else ""

    def celler(self, b: Blad20k) -> list[tuple[float, float]]:
        """Rutorna som ar 1:20 000 -- alla fyra om bladet inte finns i indexet."""
        alla = _celler_i_bladet(b.minx, b.maxy)
        i = self.blad.get(b.katalog)
        if i is None or not i.celler:
            return alla
        return [q for q in alla if q in i.celler]

    def ar_delblad(self, b: Blad20k) -> bool:
        return len(self.celler(b)) < 4

    def gransidor(self, b: Blad20k) -> tuple[str, ...]:
        """Kanterna dar ingen av de tva rutorna ar 1:20 000."""
        c = set(self.celler(b))
        x, y, d = b.minx, b.maxy, BLAD_M
        sidor = {"n": [(x, y), (x + d, y)], "s": [(x, y - d), (x + d, y - d)],
                 "v": [(x, y), (x, y - d)], "o": [(x + d, y), (x + d, y - d)]}
        return tuple(k for k, rr in sidor.items() if not c.intersection(rr))

    def yta_wkt(self, b: Blad20k) -> str | None:
        """1:20 000-delen av ett delblad som polygon i RT 90; None for ett helt blad."""
        if not self.ar_delblad(b):
            return None
        u = ogr.Geometry(ogr.wkbMultiPolygon)
        for x, y in self.celler(b):
            u.AddGeometry(ogr.CreateGeometryFromWkt(
                f"POLYGON(({x} {y - BLAD_M},{x + BLAD_M} {y - BLAD_M},{x + BLAD_M} {y},"
                f"{x} {y},{x} {y - BLAD_M}))"))
        return u.UnionCascaded().ExportToWkt()


def sokvag(mapp: str) -> str:
    return os.path.join(mapp, MAPP, NAMN + ".shp")


def hamta(mapp: str, ny: bool = False) -> str:
    """Indexet i `mapp/index_20k/`, hamtat om det saknas eller om `ny`.
    Alla filer hamtas forst och byts sedan in, sa att en halv uppsattning
    aldrig ligger kvar."""
    shp = sokvag(mapp)
    if os.path.exists(shp) and not ny:
        return shp
    os.makedirs(os.path.dirname(shp), exist_ok=True)
    stam = os.path.splitext(shp)[0]
    tmp = {e: halvfardig(f"{stam}.{e}") for e in FILER}
    try:
        for e, t in tmp.items():
            hamta_fil(f"{ROT}/{KATALOG_20K}/{NAMN}.{e}", t)
        Index20k(tmp["shp"])          # gar det att lasa? annars ligger det gamla kvar
        for e, t in tmp.items():
            os.replace(t, f"{stam}.{e}")
    finally:
        for t in tmp.values():
            if os.path.exists(t):
                os.remove(t)
    return shp


def las(mapp: str, ny: bool = False, varna: Callable[[str], None] = print) -> Index20k | None:
    """Indexet, eller None med en varning om det inte gar att fa: da klipps
    delbladen mot hela bladet och inga kanter raknas som gransidor, som fore
    0.2.2. Gar en ny hamtning inte, anvands det sparade indexet."""
    try:
        return Index20k(hamta(mapp, ny))
    except Exception as e:                       # noqa: BLE001
        if ny and os.path.exists(sokvag(mapp)):
            try:
                i = Index20k(sokvag(mapp))
                varna(f"Lantmäteriets index över 1:20 000-bladen ({NAMN}.shp) gick inte "
                      f"att hämta på nytt ({e}); det sparade används.")
                return i
            except Exception:                    # noqa: BLE001
                pass
        varna(f"Lantmäteriets index över 1:20 000-bladen ({NAMN}.shp) gick inte att hämta "
              f"eller läsa ({e}). Delbladen vid seriegränsen klipps mot hela bladet, och "
              f"bladnamnen saknas.")
        return None


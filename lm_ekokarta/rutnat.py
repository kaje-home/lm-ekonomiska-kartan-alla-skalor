"""Tva rutnat som GeoPackage: bladrutnatet och ett fast rutnat.

Bara GDAL/OGR, inga QGIS-importer. Bada gar att anvanda som omrade i
uttaget, med alla eller bara markerade rutor.

**Bladrutnatet** ar bladrutorna for bada serierna ur FTP-listningen
(listning.py): en ruta per 1:10 000-blad (5 km) och per 1:20 000-blad (10
km), med ar, antal utgavor, om bladet finns i arkivet och listningens datum.

**Det fasta rutnatet** ar kvadrater i SWEREF 99 TM med jamna koordinater:
en ruta om 2,5 km borjar alltid pa en multipel av 2 500 m. Tva korningar
over grannomraden ger rutor som passar ihop, och rutnamnet (`N7082500_E520000`,
nedre vanstra hornet) ar detsamma varje gang.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict

from osgeo import ogr, osr

from .lm_ekokarta_karna import rutnat_20k
from .filbyte import byt_in
from .lm_ekokarta_karna.blad import BLAD_20K_M
from .lm_ekokarta_karna.filer import halvfardig
from .listning import Listning

SWEREF = "EPSG:3006"
MAX_RUTOR = 200_000


def berors(yta_m2: float, snitt_m2: float) -> bool:
    """Ar en ruta med i omradet? Snittet maste ha en yta: en ruta som bara
    nuddar omradet i en kant, eller far en flisa av det nar ett lager raknas
    om mellan koordinatsystem, ar inte med. Ett mycket litet omrade far
    anda sina rutor."""
    return snitt_m2 > min(100.0, 0.01 * yta_m2)


def _srs(crs: str) -> osr.SpatialReference:
    s = osr.SpatialReference()
    s.SetFromUserInput(crs)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def _rektangel(minx, miny, maxx, maxy) -> ogr.Geometry:
    return ogr.CreateGeometryFromWkt(
        f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))")


def _ny_gpkg(utfil: str, lagernamn: str, crs: str, falt):
    ogr.UseExceptions()
    os.makedirs(os.path.dirname(os.path.abspath(utfil)), exist_ok=True)
    tmp = halvfardig(utfil)
    if os.path.exists(tmp):
        os.remove(tmp)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(tmp)
    lager = ds.CreateLayer(lagernamn, _srs(crs), ogr.wkbPolygon)
    for namn, typ in falt:
        lager.CreateField(ogr.FieldDefn(namn, typ))
    return ds, lager, tmp


def _klar(tmp: str, utfil: str, varna) -> str:
    """Den halvfardiga filen pa plats, eller under ett reservnamn om den
    gamla ar oppen. Anroparen har stangt den (ds = None)."""
    return byt_in(tmp, utfil, varna)


# --- Bladrutnatet ---------------------------------------------------------------

_BLADFALT = [("blad", ogr.OFTString), ("serie", ogr.OFTString), ("skala", ogr.OFTInteger),
             ("ar", ogr.OFTInteger), ("ar_aldsta", ogr.OFTInteger), ("ar_alla", ogr.OFTString),
             ("utgavor", ogr.OFTInteger), ("cachad", ogr.OFTInteger), ("cache", ogr.OFTString),
             ("katalog", ogr.OFTString), ("listad", ogr.OFTString)]


def _cache_10k(arkiv: str, utgavor) -> tuple[int | None, str]:
    if not arkiv:
        return None, "inget arkiv angivet"
    mapp = os.path.join(arkiv, "ekonomiska_kartan")
    har = [b.utgava for b in utgavor if os.path.exists(os.path.join(mapp, b.namn + ".tif"))]
    return (1, "hämtat: " + ", ".join(har)) if har else (0, "nej")


def _cache_20k(arkiv: str, b) -> tuple[int | None, str]:
    if not arkiv:
        return None, "inget arkiv angivet"
    mapp = os.path.join(arkiv, "ekonomiska_kartan", "20k")
    logg = os.path.join(mapp, b.katalog + "_rt90.json")
    if os.path.exists(logg):
        try:
            with open(logg, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        gammal = d.get("version") != rutnat_20k.METOD_VERSION
        if d.get("ok"):
            metod = (d.get("matt") or {}).get("metod")
            return 1, ("georefererat" + (f" ({metod})" if metod else "")
                       + (", med en äldre metod" if gammal else ""))
        if d:
            return 1, f"vägrat: {d.get('orsak', '')}" + (" (äldre metod)" if gammal else "")
    if os.path.exists(os.path.join(mapp, b.katalog + ".tif")):
        return 1, "hämtat, inte georefererat"
    return 0, "nej"


def bladrutnat(lis: Listning, arkiv: str, utfil: str, dst_crs: str = SWEREF,
               varna=print) -> tuple[int, int, str]:
    """Bladrutorna i `dst_crs`. (antal 1:10 000-rutor, antal 1:20 000-rutor,
    filen)."""
    rt90, mal = _srs("EPSG:3021"), _srs(dst_crs)
    ct = osr.CoordinateTransformation(rt90, mal)
    ds, lager, tmp = _ny_gpkg(utfil, "bladrutnat", dst_crs, _BLADFALT)
    lager.SetMetadataItem("DESCRIPTION", f"Ekonomiska kartan, bladrutor ur FTP-listningen "
                                         f"{lis.datum}")
    defn = lager.GetLayerDefn()

    def skriv(blad, serie, skala, utgavor, ruta, cache, katalog):
        ar = sorted(b.ar for b in utgavor if b.ar)
        f = ogr.Feature(defn)
        f.SetField("blad", blad)
        f.SetField("serie", serie)
        f.SetField("skala", skala)
        if ar:
            f.SetField("ar", ar[-1])
            f.SetField("ar_aldsta", ar[0])
        f.SetField("ar_alla", ", ".join(getattr(b, "utgava", None) or str(b.ar or "utan år")
                                        for b in sorted(utgavor, key=lambda b: b.ar or 0)))
        f.SetField("utgavor", len(utgavor))
        if cache[0] is not None:
            f.SetField("cachad", cache[0])
        f.SetField("cache", cache[1])
        f.SetField("katalog", katalog)
        f.SetField("listad", lis.datum)
        g = _rektangel(*ruta)
        g.Segmentize(100.0)           # rutans kanter ar inte raka i SWEREF
        g.Transform(ct)
        f.SetGeometry(g)
        lager.CreateFeature(f)

    lager.StartTransaction()
    per_ruta = defaultdict(list)
    for b in lis.blad_10k():
        per_ruta[b.ruta].append(b)
    for ruta, utg in sorted(per_ruta.items()):
        b = utg[0]
        skriv(ruta, "1:10 000", 10000, utg, (b.minx, b.miny, b.maxx, b.maxy),
              _cache_10k(arkiv, utg), b.katalog)
    per_omrade = defaultdict(list)
    for b in lis.blad_20k():
        per_omrade[(b.minx, b.maxy)].append(b)
    for (x, y), utg in sorted(per_omrade.items()):
        nyast = max(utg, key=lambda b: b.ar or 0)
        skriv(nyast.katalog, "1:20 000", 20000, utg, (x, y - BLAD_20K_M, x + BLAD_20K_M, y),
              _cache_20k(arkiv, nyast), nyast.katalog)
    lager.CommitTransaction()
    lager = ds = None
    return len(per_ruta), len(per_omrade), _klar(tmp, utfil, varna)


# --- Fast rutnat ------------------------------------------------------------------

_RUTFALT = [("ruta", ogr.OFTString), ("minx", ogr.OFTReal), ("miny", ogr.OFTReal),
            ("storlek_m", ogr.OFTReal)]


def rutnamn(minx: float, miny: float) -> str:
    """Nedre vanstra hornet i meter: samma namn for samma ruta varje gang."""
    return f"N{round(miny)}_E{round(minx)}"


def fast_rutnat(yta_wkt: str, storlek_m: float, utfil: str, crs: str = SWEREF,
                varna=print) -> tuple[int, str]:
    """Rutor om `storlek_m` med horn pa jamna multipler av storleken, de som
    `yta_wkt` (i `crs`) beror. (antal rutor, filen)."""
    if storlek_m <= 0:
        raise ValueError("rutstorleken måste vara större än noll")
    yta = ogr.CreateGeometryFromWkt(yta_wkt)
    minx, maxx, miny, maxy = yta.GetEnvelope()
    s = storlek_m
    x0, y0 = math.floor(minx / s) * s, math.floor(miny / s) * s
    nx, ny = math.ceil((maxx - x0) / s), math.ceil((maxy - y0) / s)
    if nx * ny > MAX_RUTOR:
        raise ValueError(f"{nx * ny} rutor är för många (högst {MAX_RUTOR}); välj större rutor "
                         f"eller ett mindre område")
    ds, lager, tmp = _ny_gpkg(utfil, "rutnat", crs, _RUTFALT)
    lager.SetMetadataItem("DESCRIPTION", f"Fast rutnät, {s:g} m, {crs}")
    defn = lager.GetLayerDefn()
    yta_m2 = yta.GetArea()
    n = 0
    lager.StartTransaction()
    for j in range(ny):
        for i in range(nx):
            # Hornen raknas fran heltalsindex, inte genom upprepad addition,
            # sa att de blir exakta multipler av storleken.
            a, b = (math.floor(minx / s) + i) * s, (math.floor(miny / s) + j) * s
            r = _rektangel(a, b, a + s, b + s)
            snitt = yta.Intersection(r)
            if snitt is None or not berors(yta_m2, snitt.GetArea()):
                continue
            f = ogr.Feature(defn)
            f.SetField("ruta", rutnamn(a, b))
            f.SetField("minx", a)
            f.SetField("miny", b)
            f.SetField("storlek_m", s)
            f.SetGeometry(r)
            lager.CreateFeature(f)
            n += 1
    lager.CommitTransaction()
    lager = ds = None
    return n, _klar(tmp, utfil, varna)

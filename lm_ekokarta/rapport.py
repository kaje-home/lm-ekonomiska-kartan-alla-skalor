"""Rapporten per blad: ett bladlager (GeoPackage) och en textfil.

Bara GDAL/OGR. Varje blad far en rad, aven de som lamnades utanfor och de
rutor dar ingen ekonomisk karta finns -- ett tomt stalle i kartan ska ga att
skilja fran ett blad som vagrades.
"""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field

from osgeo import ogr, osr

from .lm_ekokarta_karna.filer import halvfardig

LEVERERAT, UTELAMNAT, SAKNAS = "levererat", "utelämnat", "saknas"


@dataclass
class Bladrad:
    blad: str                         # 5 km-ruta (1:10 000) eller katalognamn (1:20 000)
    serie: str                        # "1:10 000", "1:20 000" eller "" (ingen karta)
    ruta: tuple[float, float, float, float]   # minx, miny, maxx, maxy i RT 90
    ar: int | None = None
    utgava: str = ""
    metod: str = ""                   # världsfil, rutnät, kant
    status: str = UTELAMNAT
    orsak: str = ""
    passpunkter: int | None = None
    streck: int | None = None
    kors: bool | None = None
    loo_medel_m: float | None = None
    loo_p95_m: float | None = None
    anm: str = ""
    kalla: str = ""
    fil: str = ""
    rad: str = ""                     # raden till rapport.txt


@dataclass
class Sammanfattning:
    omrade: str
    dst_crs: str
    skala: str
    utgava: str
    rader: list[Bladrad] = field(default_factory=list)
    fel: list[str] = field(default_factory=list)
    vrt: str = ""
    overlapp: list[str] = field(default_factory=list)   # rutor med bada skalorna
    brickor: list = field(default_factory=list)         # brickor.Bricka
    brick_pixel: float = 0.0

    @property
    def ar(self) -> list[int]:
        return sorted({r.ar for r in self.rader if r.status == LEVERERAT and r.ar})


def ar_text(ar: list[int]) -> str:
    if not ar:
        return "utan_ar"
    return str(ar[0]) if len(ar) == 1 else f"{ar[0]}-{ar[-1]}"


_FALT = [("blad", ogr.OFTString), ("serie", ogr.OFTString), ("ar", ogr.OFTInteger),
         ("utgava", ogr.OFTString), ("metod", ogr.OFTString), ("status", ogr.OFTString),
         ("orsak", ogr.OFTString), ("passpunkter", ogr.OFTInteger),
         ("streck", ogr.OFTInteger), ("kors", ogr.OFTInteger),
         ("loo_medel_m", ogr.OFTReal), ("loo_p95_m", ogr.OFTReal),
         ("anm", ogr.OFTString), ("kalla", ogr.OFTString), ("fil", ogr.OFTString)]


_BRICKFALT = [("ruta", ogr.OFTString), ("status", ogr.OFTString),
              ("andel_karta", ogr.OFTReal), ("fil", ogr.OFTString)]


def skriv_gpkg(s: Sammanfattning, utfil: str) -> str:
    """Bladrutorna i malets koordinatsystem, med ett falt per matt."""
    ogr.UseExceptions()
    rt90 = osr.SpatialReference()
    rt90.ImportFromEPSG(3021)
    mal = osr.SpatialReference()
    mal.SetFromUserInput(s.dst_crs)
    for sr in (rt90, mal):
        sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(rt90, mal)

    tmp = halvfardig(utfil)
    if os.path.exists(tmp):
        os.remove(tmp)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(tmp)
    lager = ds.CreateLayer("blad", mal, ogr.wkbPolygon)
    for namn, typ in _FALT:
        lager.CreateField(ogr.FieldDefn(namn, typ))
    defn = lager.GetLayerDefn()
    for r in s.rader:
        f = ogr.Feature(defn)
        for namn, _ in _FALT:
            v = getattr(r, namn)
            if v is None or v == "":
                f.SetFieldNull(namn)
            else:
                f.SetField(namn, int(v) if isinstance(v, bool) else v)
        minx, miny, maxx, maxy = r.ruta
        g = ogr.CreateGeometryFromWkt(
            f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))")
        g.Segmentize(100.0)            # rutans kanter ar inte raka i SWEREF
        g.Transform(ct)
        f.SetGeometry(g)
        lager.CreateFeature(f)
    if s.brickor:
        # Brickorna ar redan i malets koordinatsystem.
        bl = ds.CreateLayer("brickor", mal, ogr.wkbPolygon)
        for namn, typ in _BRICKFALT:
            bl.CreateField(ogr.FieldDefn(namn, typ))
        for b in s.brickor:
            f = ogr.Feature(bl.GetLayerDefn())
            f.SetField("ruta", b.ruta)
            f.SetField("status", b.status)
            if b.andel_karta is not None:
                f.SetField("andel_karta", round(b.andel_karta, 4))
            if b.fil:
                f.SetField("fil", b.fil)
            minx, miny, maxx, maxy = b.utbredning
            f.SetGeometry(ogr.CreateGeometryFromWkt(
                f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"))
            bl.CreateFeature(f)
    ds = None
    if os.path.exists(utfil):
        os.remove(utfil)
    os.replace(tmp, utfil)
    return utfil


def skriv_text(s: Sammanfattning, utfil: str) -> str:
    lev = [r for r in s.rader if r.status == LEVERERAT]
    ut = [r for r in s.rader if r.status == UTELAMNAT]
    saknas = [r for r in s.rader if r.status == SAKNAS]
    n10 = sum(r.serie == "1:10 000" for r in lev)
    n20 = sum(r.serie == "1:20 000" for r in lev)
    ar = s.ar
    rader = [
        "Ekonomiska kartan – uttag",
        f"Gjort {datetime.date.today().isoformat()} med LM Ekonomiska kartan – alla skalor.",
        "",
        f"Område: {s.omrade}",
        f"Koordinatsystem: {s.dst_crs}. Skala: {s.skala}. Utgåva: {s.utgava}.",
        f"Levererade blad: {len(lev)} ({n10} i 1:10 000, {n20} i 1:20 000). "
        f"Utelämnade: {len(ut)}. Rutor utan karta: {len(saknas)}.",
        f"Tryckår: {ar_text(ar).replace('-', '–') if ar else 'inga'}.",
    ]
    if len(ar) > 1:
        rader.append(
            "Bladen är från olika år, och VRT:n blandar dem. Vilket år ett blad är "
            "från avgör vad som syns på det -- se året per blad nedan och i bladlagret.")
    rader += [
        "",
        "Källa: Lantmäteriet, Ekonomiska kartan, öppna data (CC0), "
        "ftp://download-opendata.lantmateriet.se/Ekonomiska_kartan/.",
        "1:20 000-bladen levereras av Lantmäteriet utan georeferens och är "
        "georefererade av pluginet mot kartans eget tryckta rutnät. Lägesfelet "
        "nedan gäller georefereringen, inte kartan.",
        "",
    ]
    if s.fel:
        rader += ["Gick inte att söka (luckorna kan vara blad som finns):"]
        rader += [f"  {f}" for f in s.fel] + [""]
    if s.overlapp:
        rader += ["Där skalorna överlappar (överst = det som syns i VRT:n):"]
        rader += [f"  {t}" for t in s.overlapp] + [""]
    if s.brickor:
        skrivna = [b for b in s.brickor if b.status == "skriven"]
        tomma = [b for b in s.brickor if b.status != "skriven"]
        delvis = [b for b in skrivna if (b.andel_karta or 0) < 0.9995]
        rader.append(f"Brickor: {len(skrivna)} av {len(s.brickor)} rutor skrivna till brickor/, "
                     f"{s.brick_pixel:g} m pixlar, hörnen på jämna multipler av pixelstorleken.")
        if tomma:
            rader.append(f"  Utan kartdata, hoppades över ({len(tomma)}): "
                         + ", ".join(b.ruta for b in tomma))
        if delvis:
            rader.append(f"  Delvis utan karta (alfabandet är maskning) ({len(delvis)}): "
                         + ", ".join(f"{b.ruta} {100 * b.andel_karta:.0f} %" for b in delvis))
        rader.append("")
    for r in sorted(s.rader, key=lambda r: (r.status != LEVERERAT, r.serie, r.blad, r.ar or 0)):
        rader.append(r.rad)
    tmp = halvfardig(utfil)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(rader) + "\n")
    os.replace(tmp, utfil)
    return utfil

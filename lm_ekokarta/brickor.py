"""En GeoTIFF per ruta ur mosaiken: brickor for den som tranar modeller.

Bara GDAL. Varje bricka skars ut ur VRT:n over hela uttaget med samma
pixelstorlek, och hornen ligger pa pixelrutnatet (multipler av
pixelstorleken), sa att alla brickor -- aven fran olika korningar -- har
samma rutnat. Med ett fast rutnat (rutnat.fast_rutnat) i samma
koordinatsystem ar varje bricka exakt sin ruta.

**En ruta i taget.** VRT:n ar bara en beskrivning; GDAL laser de blad som
beror den ruta som skrivs, och bara det fonster som behovs. Hela mosaiken
ligger aldrig i minnet, och ett uttag med tusentals rutor tar inte mer
minne an ett med en.

**Rutor utan kartdata** hoppas over: forst de som ingen bladfil beror,
sedan de som blev helt genomskinliga. Bada namns i rapporten. En ruta som
delvis saknar karta skrivs, med alfabandet som mask och andelen karta i
rapporten.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable

from osgeo import gdal

from .filbyte import byt_in
from .lm_ekokarta_karna import gdalfart
from .lm_ekokarta_karna.filer import halvfardig, kontrollera_raster

SKAPA = ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"]
SKRIVEN, TOM, FEL = "skriven", "ingen kartdata", "gick inte att skriva"


@dataclass
class Bricka:
    ruta: str
    utbredning: tuple[float, float, float, float]   # minx, miny, maxx, maxy i uttagets CRS
    status: str = ""
    andel_karta: float | None = None
    fil: str = ""
    orsak: str = ""


def pa_pixelrutnat(minx, miny, maxx, maxy, pixel: float) -> tuple[float, float, float, float]:
    """Utbredningen utvidgad till hela pixlar pa rutnatet med horn i 0."""
    return (math.floor(minx / pixel + 1e-9) * pixel, math.floor(miny / pixel + 1e-9) * pixel,
            math.ceil(maxx / pixel - 1e-9) * pixel, math.ceil(maxy / pixel - 1e-9) * pixel)


def _utbredning(fil: str) -> tuple[float, float, float, float]:
    d = gdal.Open(fil)
    gt = d.GetGeoTransform()
    return gt[0], gt[3] + gt[5] * d.RasterYSize, gt[0] + gt[1] * d.RasterXSize, gt[3]


def _skar(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def skriv(vrt: str, bladfiler: list[str], brickor: list[Bricka], pixel: float, mapp: str,
          steg: Callable[[str], None] = print, framsteg: Callable[[float], None] = lambda p: None,
          avbruten: Callable[[], bool] = lambda: False,
          varna: Callable[[str], None] = print) -> list[Bricka]:
    """Skriv brickorna till `mapp`/<ruta>.tif. Fyller i status per bricka.
    En bricka som inte gar att skriva far status FEL med orsaken; de ovriga
    skrivs anda."""
    gdal.UseExceptions()
    os.makedirs(mapp, exist_ok=True)
    vrt_px = gdal.Open(vrt).GetGeoTransform()[1]
    if abs(pixel - vrt_px) < 1e-9:
        metod = "near"              # samma rutnat: pixlarna flyttas, inte raknas om
    elif pixel > vrt_px:
        metod = "average"
    else:
        metod = "bilinear"
    bladytor = [_utbredning(f) for f in bladfiler]
    for n, b in enumerate(brickor, 1):
        if avbruten():
            break
        framsteg(100 * n / len(brickor))
        if not any(_skar(b.utbredning, y) for y in bladytor):
            b.status, b.andel_karta = TOM, 0.0
            continue
        steg(f"Bricka {n}/{len(brickor)}: {b.ruta}")
        try:
            _en(vrt, b, os.path.join(mapp, b.ruta + ".tif"), pixel, metod, varna)
        except Exception as e:                  # noqa: BLE001
            b.status, b.orsak = FEL, str(e)
            varna(f"Brickan {b.ruta} gick inte att skriva: {e}")
    return brickor


def _en(vrt: str, b: Bricka, ut: str, pixel: float, metod: str, varna) -> None:
    tmp = halvfardig(ut)
    try:
        # Utan PAM: annars blir histogrammet en .aux.xml bredvid brickan.
        with gdal.config_options({"GDAL_PAM_ENABLED": "NO"}):
            gdal.Warp(tmp, vrt, format="GTiff", outputBounds=b.utbredning,
                      xRes=pixel, yRes=pixel, resampleAlg=metod, dstAlpha=True,
                      creationOptions=SKAPA, **gdalfart.WARP)
            d = gdal.Open(tmp)
            alfa = d.GetRasterBand(d.RasterCount)
            # Histogrammet laser bandet block for block, inte hela i minnet.
            hist = alfa.GetHistogram(-0.5, 255.5, 256, include_out_of_range=0, approx_ok=0)
            tot = d.RasterXSize * d.RasterYSize
            d = None
        b.andel_karta = 1.0 - hist[0] / tot if tot else 0.0
        if hist[0] == tot:
            b.status = TOM
            return
        kontrollera_raster(tmp, minsta_byte=1000)
        b.status, b.fil = SKRIVEN, byt_in(tmp, ut, varna)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

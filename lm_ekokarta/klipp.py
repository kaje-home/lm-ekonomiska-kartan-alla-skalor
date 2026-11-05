"""Ett blad till GeoTIFF, klippt mot bladrutan, och VRT:n over alla blad.

Bara GDAL, inga QGIS-importer.

**Klippt mot bladrutan, med alfaband.** Bladet ar en ruta i RT 90. I SWEREF
99 TM ar rutan vriden knappt en grad (~0,7), och en rektangulart utskuren GeoTIFF far
da kilar runt om. Med alfa ar kilarna genomskinliga i stallet for vita eller
svarta, och tva grannblad kan ligga over varandra utan att det ena tacker det
andra. Samma klippning tar bort det som en skanning har utanfor sin ruta.

**Bladets egen upplosning:** 1 m i 1:10 000, 2 m i 1:20 000. Upprakningen
till 1 m gors forst i VRT:n, som har den finaste upplosningen.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Callable

from osgeo import gdal, osr

from .filbyte import byt_in, reserver
from .lm_ekokarta_karna import gdalfart
from .lm_ekokarta_karna.filer import halvfardig, kontrollera_raster

RT90 = "EPSG:3021"
SKAPA = ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"]
# Kallan och installningarna i varje blad; hoj KLIPP_VERSION nar klippningen
# andras, sa att gamla blad i en utmapp gors om.
KALLA_NYCKEL = "LM_EKOKARTA_KALLA"
KLIPP_VERSION = "1"


def rektangel_wkt(minx: float, miny: float, maxx: float, maxy: float) -> str:
    return (f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},"
            f"{minx} {maxy},{minx} {miny}))")


def samma_crs(a: str, b: str = RT90) -> bool:
    s1, s2 = osr.SpatialReference(), osr.SpatialReference()
    s1.SetFromUserInput(a)
    s2.SetFromUserInput(b)
    return bool(s1.IsSame(s2))


def _som_rgb(ds):
    """Fargtabell eller ett grått band blir tre band, sa att alla blad far
    samma bandantal och kan ga in i samma VRT."""
    if ds.RasterCount == 1:
        if ds.GetRasterBand(1).GetColorTable() is not None:
            return gdal.Translate("", ds, format="VRT", rgbExpand="rgb")
        return gdal.Translate("", ds, format="VRT", bandList=[1, 1, 1])
    return ds


def klipp(kalla: str, ruta: tuple[float, float, float, float], utfil: str,
          dst_crs: str, pixel_m: float, varna: Callable[[str], None] = print) -> str:
    """Skriv `kalla` (i RT 90) till `utfil` i `dst_crs`, klippt mot `ruta`
    (minx, miny, maxx, maxy i RT 90), med alfaband. Halvfardig fil tills den
    ar kontrollerad. Returnerar namnet filen fick (filbyte.byt_in).

    Finns bladet redan i utmappen, gjort ur samma kalla med samma
    installningar (KALLA_NYCKEL i filen), anvands det som det ar. Det sparar
    tid, och framfor allt behover filen inte skrivas om: ett blad som en
    inlast VRT har last i QGIS ar last tills QGIS startas om."""
    gdal.UseExceptions()
    nyckel = _nyckel(kalla, ruta, dst_crs, pixel_m)
    for f in [utfil] + reserver(utfil):
        if _har_nyckel(f, nyckel):
            return f
    ds = gdal.Open(kalla)
    src = _som_rgb(ds)
    os.makedirs(os.path.dirname(os.path.abspath(utfil)), exist_ok=True)
    tmp = halvfardig(utfil)
    # 1:10 000-bladens TIFF bar ett felaktigt geografiskt system i sina
    # GeoTIFF-nycklar (EPSG:4124 som inte stammer med registret) och ibland
    # inget alls -- RT 90 anges alltid uttryckligen.
    with gdal.config_options({"GDAL_PAM_ENABLED": "NO"}):
        gdal.Warp(tmp, src, format="GTiff", srcSRS=RT90, dstSRS=dst_crs,
                  cutlineWKT=rektangel_wkt(*ruta), cutlineSRS=RT90,
                  cropToCutline=True, dstAlpha=True,
                  xRes=pixel_m, yRes=pixel_m, targetAlignedPixels=True,
                  # I RT 90 ligger pixlarna redan ratt: ingen omsampling.
                  resampleAlg="near" if samma_crs(dst_crs) else "cubic",
                  creationOptions=SKAPA, **gdalfart.WARP)
    src = ds = None
    kontrollera_raster(tmp, minsta_byte=10_000)
    # Oversikterna och nyckeln innan filen far sitt namn: efter bytet kan den
    # vara last.
    gdalfart.oversikter(tmp)
    with gdal.config_options({"GDAL_PAM_ENABLED": "NO"}):
        d = gdal.Open(tmp, gdal.GA_Update)
        d.SetMetadataItem(KALLA_NYCKEL, nyckel)
        d = None
    return byt_in(tmp, utfil, varna)


def _nyckel(kalla: str, ruta, dst_crs: str, pixel_m: float) -> str:
    st = os.stat(kalla)
    return (f"{KLIPP_VERSION}|{os.path.normcase(os.path.abspath(kalla))}|{st.st_size}|"
            f"{int(st.st_mtime)}|{','.join(f'{v:.3f}' for v in ruta)}|{dst_crs}|{pixel_m:g}")


def _har_nyckel(fil: str, nyckel: str) -> bool:
    if not os.path.exists(fil):
        return False
    try:
        with gdal.config_options({"GDAL_PAM_ENABLED": "NO"}):
            d = gdal.Open(fil)
            ok = d.GetMetadataItem(KALLA_NYCKEL) == nyckel and d.RasterCount == 4
            d = None
        return ok
    except RuntimeError:
        return False


def bygg_vrt(filer: list[str], utfil: str, varna: Callable[[str], None] = print) -> str:
    """VRT over bladen i den ordning de ges -- det sista ritas overst.

    gdalbuildvrt later en kalla skriva over allt som kom fore inom sin
    rektangel, aven dar den sjalv ar genomskinlig. Varje kalla far darfor
    `UseMaskBand`: bara pixlar som bladets alfa sager ar karta skrivs.
    """
    gdal.UseExceptions()
    tmp = halvfardig(utfil)
    vrt = gdal.BuildVRT(tmp, filer, resolution="highest")
    if vrt is None:
        raise RuntimeError("VRT:n gick inte att bygga")
    vrt = None
    trad = ET.parse(tmp)
    for band in trad.getroot().iter("VRTRasterBand"):
        for kalla in list(band):
            if kalla.tag not in ("SimpleSource", "ComplexSource"):
                continue
            kalla.tag = "ComplexSource"
            if kalla.find("UseMaskBand") is None:
                ET.SubElement(kalla, "UseMaskBand").text = "true"
    trad.write(tmp, encoding="UTF-8", xml_declaration=False)
    kontrollera_raster(tmp, minsta_byte=100)
    return byt_in(tmp, utfil, varna)

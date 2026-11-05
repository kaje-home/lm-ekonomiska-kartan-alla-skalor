"""Alla karnor at GDAL -- mosaiker och oversiktsnivaer.

**Varfor.** `multithread=True` i gdal.Warp ger TVA tradar, en som laser och
en som raknar; sjalva omrakningen gar pa en karna. Oversiktsbygget ar
enkeltradat om inte `GDAL_NUM_THREADS` ar satt. Under ett skarpt uttag
2026-09-26 (fyra indexrutor, ortofoto 2023-2024, 8,5 GB) stod QGIS pa 1,0 av
datorns 20 karnor i en halvtimme.

Uppmatt samma dag pa en indexruta, fyra bildrutor 2024, 2,9 GB ut:

    som forut                     mosaik 74 s   oversikter 126 s
    alla karnor, 2 GB arbetsminne mosaik 65 s   oversikter  55 s

Pixel for pixel samma bild -- det ar bara hur arbetet fordelas som andras.
Arbetsminnet ar GDAL:s forval 64 MB annars, och en stor bild rakas da i
tusentals smabitar.
"""
from __future__ import annotations

# Till gdal.Warp: gdal.Warp(ut, in, **WARP, ...). Ersatter multithread=True.
WARP = {"multithread": True,
        "warpOptions": ["NUM_THREADS=ALL_CPUS"],
        "warpMemoryLimit": 2048}

NIVAER = (2, 4, 8, 16, 32)


def oversikter(sokvag: str, nivaer=NIVAER) -> None:
    """Interna oversiktsnivaer (AVERAGE) med alla karnor.

    Tradantalet satts bara for den har tradens anrop och aterstalls efterat --
    ett uttag kor flera steg, och en global installning skulle lacka."""
    from osgeo import gdal
    with gdal.config_options({"GDAL_NUM_THREADS": "ALL_CPUS"}):
        ds = gdal.Open(sokvag, gdal.GA_Update)
        ds.BuildOverviews("AVERAGE", list(nivaer))
        ds = None

"""Filer som skrivs halvfardiga och kontrolleras innan de far sitt namn.

Ordagrant ur LM Faltunderlag, lm_faltunderlag/verktyg/kontroll.py (commit
f31c0ba): bara det som hamtningen och georefereringen av ekonomiska kartan
anvander. Skalen star i funktionernas egna noter; "avsnitt 8" ar avsnittet i
Faltunderlagets kravspec om steg som rapporterar framgang utan att leverera.
"""
from __future__ import annotations

import os
import time


class Levererades_inte(Exception):
    """Ett steg rapporterade framgang men filen ar inte anvandbar."""


def _finns(sokvag: str, minsta_byte: int) -> None:
    if not os.path.exists(sokvag):
        raise Levererades_inte(
            f"{os.path.basename(sokvag)} skapades aldrig. Steget rapporterade "
            f"framgang, sa returvardet gar inte att lita pa -- se avsnitt 8."
        )
    n = os.path.getsize(sokvag)
    if n < minsta_byte:
        raise Levererades_inte(
            f"{os.path.basename(sokvag)} ar {n} byte, vilket ar for lite for att "
            f"vara komplett (vantade minst {minsta_byte})."
        )


def kontrollera_raster(sokvag: str, *, minsta_byte: int = 1024,
                       vantade_band: int | None = None,
                       vantad_crs: str | None = None) -> None:
    """Raster: finns, gar att oppna, har band och data."""
    from osgeo import gdal
    gdal.UseExceptions()
    _finns(sokvag, minsta_byte)
    try:
        ds = gdal.Open(sokvag)
    except Exception as e:
        raise Levererades_inte(f"{os.path.basename(sokvag)} gar inte att oppna: {e}")
    if ds is None:
        raise Levererades_inte(f"{os.path.basename(sokvag)} gar inte att oppna.")
    if ds.RasterXSize < 1 or ds.RasterYSize < 1:
        raise Levererades_inte(
            f"{os.path.basename(sokvag)} har storleken "
            f"{ds.RasterXSize}x{ds.RasterYSize}. Nollstora rader kommer typiskt "
            f"av att en utbredning inte tolkades -- se FILTER_EXTENT i avsnitt 3."
        )
    if vantade_band is not None and ds.RasterCount != vantade_band:
        raise Levererades_inte(
            f"{os.path.basename(sokvag)} har {ds.RasterCount} band, vantade "
            f"{vantade_band}. rvt_multi_hillshade ger 16 band och maste vagas "
            f"samman -- se avsnitt 7."
        )
    if vantad_crs is not None:
        wkt = ds.GetProjection()
        if not wkt:
            raise Levererades_inte(f"{os.path.basename(sokvag)} saknar CRS.")
    ds = None


def halvfardig(mal: str) -> str:
    """Namn pa den halvfardiga filen: `stam.delvis.ext`, inte `stam.ext.delvis`.

    Atomiciteten i avsnitt 8 kraver att filen heter nagot annat tills den ar
    komplett. Den naiva varianten -- lagga `.delvis` sist -- forstor filandelsen,
    och bade PDAL och GDAL valjer skrivare pa just den. Det slog till tva ganger:
    GDAL med *Cannot guess driver*, PDAL med *Cannot determine writer for output
    file*. GDAL gick att radda med ett uttryckligt `format="GTiff"`; PDAL
    translate har ingen motsvarande flagga som gar att satta lika enkelt.

    Att i stallet lagga `.delvis` **fore** andelsen loser bada pa en gang och
    kraver ingen kannedom om vilket format anropet rakar skriva. `.copc.laz`
    blir `.copc.delvis.laz` -- fortfarande LAZ for den som laser andelsen, och
    fortfarande ett namn som inte gar att forvaxla med den fardiga filen.

    Ingenting i pluginet soker filer med jokertecken, sa en `.delvis.laz` i en
    arbetskatalog kan inte plockas upp av misstag.
    """
    stam, ext = os.path.splitext(mal)
    return f"{stam}{_min_markering()}{ext}" if ext else mal + _min_markering()


def stada_gamla_delvis(mal: str, aldre_an_timmar: float = 24.0) -> int:
    """Ta bort OVERGIVNA halvfardiga filer for samma mal. Returnerar antalet.

    Sedan mellanledet fick dator och process i namnet kan en korning som dog
    -- stromavbrott, kraschat QGIS -- lamna efter sig en halvfardig fil som
    ingen nagonsin skriver over. I ett gemensamt arkiv pa en NAS ar det
    gigabyte som ligger och skrapar i all evighet.

    Darfor sopas de bort har. **Bara gamla**: en fil som rors just nu hor till
    en kollega som haller pa, och den far vara i fred. Ett dygn ar med god
    marginal -- den langsta uppmatta nedladdningen av en distributionsruta ar
    minuter, inte timmar.
    """
    import glob
    stam, ext = os.path.splitext(mal)
    granslinje = time.time() - aldre_an_timmar * 3600
    n = 0
    for f in glob.glob(f"{glob.escape(stam)}.delvis.*{ext}"):
        try:
            if os.path.getmtime(f) < granslinje:
                os.remove(f)
                n += 1
        except OSError:
            pass
    return n


def _min_markering() -> str:
    """`.delvis` plus vem som skriver -- dator och process.

    **Arkivet ar gemensamt.** Det ar hela poangen med det: alla pekar pa samma
    katalog pa en NAS och fyller pa den tillsammans. Men mellanledet hette
    bara `.delvis`, likadant for alla, och nedladdningen borjar med att ta bort
    ett mellanled som redan finns. Tva kollegor som hamtade samma ruta inom
    samma minuter raderade alltsa varandras halvfardiga fil och skrev till
    samma namn.

    Punktantalet kontrolleras mot katalogen innan filen far sitt riktiga namn,
    sa arkivet blev sannolikt inte trasigt -- men den ene fick ett obegripligt
    "filen ar sannolikt ofullstandig" i stallet for det verkliga skalet.

    Med dator och process i namnet kan de tva inte mota varandra. Den som blir
    fardig forst ger filen dess riktiga namn; den andre skriver over den med
    samma innehall, vilket ar ofarligt.
    """
    import socket
    dator = "".join(t for t in socket.gethostname() if t.isalnum() or t in "-_")
    return f".delvis.{dator[:24] or 'okand'}-{os.getpid()}"

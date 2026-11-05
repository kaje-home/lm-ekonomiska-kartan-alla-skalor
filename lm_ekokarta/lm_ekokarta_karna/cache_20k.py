"""Hamta, georeferera och cacha ett blad ur 1:20 000-serien.

Flyttad ur lm_faltunderlag/algoritmer/hamta_ekokarta.py (`_blad_20k`,
`_duger`). Det enda som andrats ar att QGIS-objektet `feedback` ersatts av tva
funktioner, `info` och `steg` -- Faltunderlaget skickar `feedback.pushInfo`
och `feedback.setProgressText` och far samma rader som forut.

Cachen per blad i `mapp` (i arkivet `<arkiv>/ekonomiska_kartan/20k/`):

    <katalog>.tif          den raa skanningen
    <katalog>_rt90.tif     den georefererade, RT 90, 2 m, exakt bladets 10 x 10 km
    <katalog>_rt90.json    {ok, rad, orsak, version, matt, gransidor}

`matt` tillkom 2026-11-04 for det nya pluginets rapport: passpunkter, streck
och lagesfel som tal. Faltunderlaget laser bara ok, rad och version, och en
aldre json utan `matt` duger som forut -- se `las_matt`.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

from . import blad as ekokarta
from . import rutnat_20k
from .filer import Levererades_inte, kontrollera_raster
from .ftp import hamta_fil


def blad_20k(b, mapp: str, info: Callable[[str], None],
             steg: Callable[[str], None], gransidor=()) -> tuple[str | None, str, int | None]:
    """Hamta och georeferera ett 1:20 000-blad. (utfil eller None, rad, ar).

    Bade den raa skanningen och den georefererade filen sparas, och utfallet i
    en .json bredvid: georefereringen ger samma svar varje gang (kravspecen),
    sa ett blad som redan provats -- lyckat eller inte -- provas inte om. Utom
    nar metoden har andrats (rutnat_20k.METOD_VERSION): ett blad som vagrades
    av en aldre metod kan klara en nyare.

    `gransidor`: kanterna mot 1:10 000-omradet (rutnat_20k.georeferera_20k).
    De sparas i json-filen. Ett vagrat blad provas om nar anroparen anger en
    kant som inte var med da: LM Faltunderlag anger inga, sa ett blad som
    det har vagrat i ett delat arkiv provas om av LM Ekonomiska kartan.
    """
    ra = os.path.join(mapp, b.katalog + ".tif")
    geo = os.path.join(mapp, b.katalog + "_rt90.tif")
    logg = os.path.join(mapp, b.katalog + "_rt90.json")
    gransidor = sorted(gransidor or ())
    if os.path.exists(logg):
        with open(logg, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == rutnat_20k.METOD_VERSION and (
                duger(geo) if d["ok"] else set(gransidor) <= set(d.get("gransidor", []))):
            info(f"   {b.katalog}: georefererat sedan tidigare")
            return (geo if d["ok"] else None), d["rad"], b.ar
    if not duger(ra):
        steg(f"Hämtar {b.katalog} (1:20 000)")
        hamta_fil(ekokarta.fil_20k(b), ra)
    steg(f"Georefererar {b.katalog}")
    res = rutnat_20k.georeferera_20k(ra, b.minx, b.maxy, geo, gransidor)
    rad = rutnat_20k.rad_for_uttag(b.katalog, b.ar, res)
    # Det som behovs for att forsta ett utelamnat blad i efterhand. Loggen
    # toms nar QGIS startas om; raden ovan gar till uttag.txt.
    per = res.period_px or (0.0, 0.0)
    info(
        f"   {b.katalog}: {'georefererat' if res.ok else 'utelämnat'} ({res.metod}); period "
        f"{per[0]:.2f}/{per[1]:.2f} px/km, vridning {res.vridning_grader or 0:.2f}°"
        + (f", {len(res.passpunkter)} passpunkter, RMS affin {res.rms_affin_m:.2f} m, "
           f"grad 2 {res.rms_grad2_m:.2f} m, lämna-en-utanför 95 % {res.loo_p95_m:.1f} m"
           if res.rms_affin_m is not None else "")
        + (f", {res.streck} kilometerstreck, mittkors {'ja' if res.kors else 'nej'}, "
           f"lämna-en-utanför 95 % {res.loo_p95_m:.1f} m"
           if res.metod == "kant" and res.loo_p95_m is not None else "")
        + ("" if res.ok else f" — {res.orsak}"))
    with open(logg, "w", encoding="utf-8") as f:
        json.dump({"ok": res.ok, "rad": rad, "orsak": res.orsak,
                   "version": rutnat_20k.METOD_VERSION, "matt": matt(res),
                   "gransidor": gransidor},
                  f, ensure_ascii=False)
    return (geo if res.ok else None), rad, b.ar


def duger(sokvag: str) -> bool:
    """Ar det arkiverade bladet anvandbart? En fil som inte gar att oppna
    tas bort, sa att den hamtas om -- hellre det an att en avbruten
    nedladdning ligger kvar i arkivet och ser hel ut."""
    if not os.path.exists(sokvag):
        return False
    try:
        kontrollera_raster(sokvag, minsta_byte=50_000)
        return True
    except Levererades_inte:
        os.remove(sokvag)
        return False


def matt(res) -> dict:
    """Kvalitetsmatten ur ett rutnat_20k.Resultat, som tal och inte som text."""
    per = res.period_px
    return {
        "metod": res.metod,
        "passpunkter": None if res.passpunkter is None or res.metod == "kant"
        else int(len(res.passpunkter)),
        "streck": int(res.streck) if res.metod == "kant" else None,
        "kors": bool(res.kors) if res.metod == "kant" else None,
        "period_px": None if per is None else [float(per[0]), float(per[1])],
        "vridning_grader": res.vridning_grader,
        "rms_affin_m": res.rms_affin_m,
        "rms_grad2_m": res.rms_grad2_m,
        "loo_medel_m": res.loo_medel_m,
        "loo_p95_m": res.loo_p95_m,
        "gransidor": list(res.gransidor) if res.metod == "kant" else None,
    }


def las_matt(mapp: str, katalog: str) -> dict:
    """Utfallet ur cachen: {ok, rad, orsak, version, matt}. Tom dict om bladet
    inte ar provat.

    En json fran fore 2026-11-04 saknar `matt`; da lases talen ur raden till
    uttag.txt, som har samma tal i fast form. En json skriven av LM
    Historiska kartor saknar aven raden, och da blir matten tomma.
    """
    logg = os.path.join(mapp, katalog + "_rt90.json")
    if not os.path.exists(logg):
        return {}
    with open(logg, encoding="utf-8") as f:
        d = json.load(f)
    if not d.get("matt"):
        d["matt"] = _matt_ur_rad(d.get("rad", ""))
    return d


def _matt_ur_rad(rad: str) -> dict:
    m = {"metod": None, "passpunkter": None, "streck": None, "kors": None,
         "loo_medel_m": None, "loo_p95_m": None}
    if not rad or "utelämnat" in rad:
        return m
    m["metod"] = "kant" if "streck i marginalen" in rad else "rutnät"
    if (t := re.search(r"(\d+) passpunkter", rad)):
        m["passpunkter"] = int(t.group(1))
    if (t := re.search(r"(\d+) kilometerstreck", rad)):
        m["streck"] = int(t.group(1))
    if m["metod"] == "kant":
        m["kors"] = "korset mitt på bladet" in rad
    if (t := re.search(r"([\d.]+) m i medel, ([\d.]+) m\s+för 95 %", rad)):
        m["loo_medel_m"], m["loo_p95_m"] = float(t.group(1)), float(t.group(2))
    return m

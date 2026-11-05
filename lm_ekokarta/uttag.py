"""Ett uttag: 5 km-rutor in, georefererade blad, VRT och rapport ut.

Bara GDAL och karnan, inga QGIS-importer: Processing-algoritmen raknar ut
vilka rutor omradet tacker och anropar `kor`, och samma funktion gar att kora
utan QGIS. Gangen:

1. 1:10 000-bladen har Lantmateriets varldsfil, som granskas: en
   ihoptryckt skanning (pixel under 1 m) lamnas utanfor.
2. 1:20 000-bladen hamtas ra och georefereras mot kartans eget rutnat
   (lm_ekokarta_karna.rutnat_20k). Ett blad i taget: ~0,6 GB per skanning.
3. I det automatiska laget galler utgavevalet aven mellan skalorna: per ruta
   provas bladen i ordningen "nyaste" (yngst forst) eller "aldsta" (aldst
   forst), 1:10 000 fore 1:20 000 vid samma ar, och det forsta som gar att
   leverera tar rutan. Ett blad som ingen ruta behover hamtas inte.
4. Varje levererat blad klipps mot sin ruta i malets koordinatsystem.
5. VRT over alla, i samma ordning i alla lagen, aven "bada": det yngsta
   (eller aldsta) bladet overst, 1:10 000 vid samma ar.
6. Bladlager och rapport, med ar, kalla, metod och lagesfel per blad, och
   vilket blad som ligger overst dar skalorna overlappar.

Arkivet har samma uppstallning som LM Faltunderlags, `<arkiv>/ekonomiska_kartan/`
och `.../20k/`, sa att de kan dela arkiv. Utan arkiv hamnar nedladdningen i
utmappen och stadas bort efterat.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Callable

from . import klipp, rapport
from .lm_ekokarta_karna import blad_alla, cache_20k, rutnat_20k
from .lm_ekokarta_karna.blad import BLAD_20K_M
from .lm_ekokarta_karna.ftp import hamta_fil
from .rapport import LEVERERAT, SAKNAS, UTELAMNAT, Bladrad, Sammanfattning

ARKIVMAPP = "ekonomiska_kartan"
MAPP_20K = "20k"
SKALOR = ("auto", "10k", "20k", "bada")
SKALA_TEXT = {"auto": "den skala vars blad passar utgåvevalet, 1:10 000 vid samma år",
              "10k": "bara 1:10 000", "20k": "bara 1:20 000",
              "bada": "båda serierna där de finns"}
UTGAVA_TEXT = {"nyaste": "nyaste", "aldsta": "äldsta", "alla": "alla utgåvor"}

ANM_KANT = ("lämna-en-utanför underskattar felet; prövat mot blad med heldraget "
            "rutnät är det verkliga felet omkring 2 m större")


class Avbrutet(Exception):
    pass


@dataclass
class Rapportor:
    """Hur uttaget talar med anroparen. Processing skickar feedback-objektets
    metoder; utan QGIS skrivs allt ut."""
    info: Callable[[str], None] = print
    varning: Callable[[str], None] = print
    steg: Callable[[str], None] = print
    framsteg: Callable[[float], None] = lambda p: None
    avbruten: Callable[[], bool] = lambda: False


def _kolla(r: Rapportor) -> None:
    if r.avbruten():
        raise Avbrutet()


def kor(rutor: list[tuple[float, float]], utmapp: str, arkiv: str, dst_crs: str,
        skala: str = "auto", utgava: str = "nyaste", vrt: bool = True,
        omrade: str = "", r: Rapportor | None = None) -> Sammanfattning:
    """`rutor`: 5 km-rutorna (minx, maxy i RT 90) som omradet tacker."""
    r = r or Rapportor()
    if skala not in SKALOR:
        raise ValueError(f"skala ska vara en av {SKALOR}")
    s = Sammanfattning(omrade=omrade, dst_crs=dst_crs, skala=SKALA_TEXT[skala],
                       utgava=UTGAVA_TEXT[utgava])
    tmp = os.path.join(arkiv, ARKIVMAPP) if arkiv else os.path.join(utmapp, "_nedladdat")
    bladmapp = os.path.join(utmapp, "blad")
    os.makedirs(bladmapp, exist_ok=True)
    rutor = sorted(set(rutor))
    try:
        levererade_rutor: set[tuple[float, float]] = set()
        b10 = _sok(r, s, "1:10 000", blad_alla.hitta_10k, rutor, utgava) \
            if skala in ("auto", "10k", "bada") else []
        b20 = _sok(r, s, "1:20 000", blad_alla.hitta_20k, rutor, utgava) \
            if skala in ("auto", "20k", "bada") else []
        kand: dict[tuple[float, float], list] = {q: [] for q in rutor}
        for b in b10:
            if (b.minx, b.maxy) in kand:
                kand[(b.minx, b.maxy)].append(("1:10 000", b))
        for b in b20:
            for q in blad_alla.rutor_20k(b):
                if q in kand:
                    kand[q].append(("1:20 000", b))
        gjorda: dict[tuple, Bladrad] = {}

        def leverera(serie, b) -> Bladrad:
            nyckel = _id(serie, b)
            if nyckel not in gjorda:
                _kolla(r)
                if serie == "1:10 000":
                    r.steg(f"1:10 000: {b.ruta} ({b.utgava})")
                    rad = _blad_10k(b, tmp, bladmapp, dst_crs, r)
                    tackta = [(b.minx, b.maxy)]
                else:
                    rad = _blad_20k(b, os.path.join(tmp, MAPP_20K), bladmapp, dst_crs, r)
                    tackta = blad_alla.rutor_20k(b)
                gjorda[nyckel] = rad
                s.rader.append(rad)
                if rad.status == LEVERERAT:
                    levererade_rutor.update(tackta)
            return gjorda[nyckel]

        if skala == "auto" and utgava != "alla":
            # Per ruta det blad som utgavevalet vill ha overst; vagras det
            # tas nasta. Ett blad som tagit en ruta ar redan gjort for de
            # ovriga rutor det tacker.
            for n, q in enumerate(rutor, 1):
                for serie, b in sorted(kand[q], reverse=True,
                                       key=lambda k: _nyckel(k[0], k[1].ar, utgava)):
                    if leverera(serie, b).status == LEVERERAT:
                        break
                r.framsteg(90 * n / len(rutor))
        else:
            # Alla funna blad: en serie (10k, 20k), bada, eller alla utgavor.
            alla = [("1:10 000", b) for b in b10] + [("1:20 000", b) for b in b20]
            for n, (serie, b) in enumerate(alla, 1):
                leverera(serie, b)
                r.framsteg(90 * n / len(alla))
        s.overlapp = _overlapp(rutor, s.rader, kand, utgava)

        # --- Rutor utan karta --------------------------------------------------
        if skala in ("auto", "bada"):
            for x, y in rutor:
                if (x, y) not in levererade_rutor and not _har_rad(s, x, y):
                    s.rader.append(Bladrad(
                        blad=(blad_alla.ruta_for(x, y) or ("", f"{x:.0f},{y:.0f}"))[1],
                        serie="", ruta=(x, y - 5000.0, x + 5000.0, y), status=SAKNAS,
                        orsak="ingen ekonomisk karta i någon serie",
                        rad=f"Ruta {(blad_alla.ruta_for(x, y) or ('', ''))[1]}: ingen "
                            f"ekonomisk karta i någon serie. Kartan är inte rikstäckande."))

        # --- VRT och rapport -------------------------------------------------
        _kolla(r)
        if vrt:
            filer = _vrt_ordning(s.rader, utgava)
            if filer:
                r.steg("Bygger VRT")
                namn = f"ekonomiska_kartan_{rapport.ar_text(s.ar)}.vrt"
                s.vrt = klipp.bygg_vrt(filer, os.path.join(utmapp, namn))
        r.steg("Skriver rapporten")
        rapport.skriv_gpkg(s, os.path.join(utmapp, "blad.gpkg"))
        rapport.skriv_text(s, os.path.join(utmapp, "rapport.txt"))
        for f in s.fel:
            r.varning(f)
        r.framsteg(100)
        return s
    finally:
        # Arkiverade blad ska ligga kvar -- det ar hela poangen med dem.
        if not arkiv:
            shutil.rmtree(tmp, ignore_errors=True)


def _sok(r: Rapportor, s: Sammanfattning, serie: str, hitta, rutor, utgava) -> list:
    r.steg(f"Söker i {serie}-serien")
    blad, fel = hitta(rutor, utgava)
    s.fel += fel
    r.info(f"{len(blad)} blad i {serie}")
    return blad


def _id(serie: str, b) -> tuple:
    """Samma nyckel for ett funnet blad och dess Bladrad (se _rad_id)."""
    if serie == "1:10 000":
        return (serie, b.ruta, b.utgava)
    return (serie, b.katalog, str(b.ar) if b.ar else "")


def _rad_id(d: Bladrad) -> tuple:
    return (d.serie, d.blad, d.utgava)


def _nyckel(serie: str, ar: int | None, utgava: str) -> tuple:
    """Ordningen mellan bladen, nedersta forst: det blad som ska
    synas har storst nyckel. "aldsta" vander pa aren; vid samma ar gar
    1:10 000 fore. Ett blad utan ar hamnar underst."""
    if utgava == "aldsta":
        a = -ar if ar else -10 ** 6
    else:
        a = ar or 0
    return (a, serie == "1:10 000")


def _ordning(utgava: str):
    """Samma regel i alla lagen, aven "bada": utgavevalet galler mellan skalorna."""
    return lambda q: _nyckel(q.serie, q.ar, utgava)


def _tacker(d: Bladrad, x: float, y: float) -> bool:
    minx, miny, maxx, maxy = d.ruta
    return minx <= x < maxx and miny < y <= maxy


def _har_rad(s: Sammanfattning, x: float, y: float) -> bool:
    """Har rutan redan en rad (ett vagrat blad)? Da ar den inte "utan karta"."""
    return any(_tacker(q, x, y) for q in s.rader)


def _vrt_ordning(rader: list[Bladrad], utgava: str) -> list[str]:
    """Nedersta bladet forst, sa att det sista ritas overst (klipp.bygg_vrt)."""
    lev = [q for q in rader if q.status == LEVERERAT and q.fil]
    lev.sort(key=_ordning(utgava))
    return [q.fil for q in lev]


def _benamn(serie: str, blad: str, ar: int | None) -> str:
    return f"{serie}-bladet {blad} ({ar or 'utan år'})"


def _overlapp(rutor, rader: list[Bladrad], kand: dict, utgava: str) -> list[str]:
    """Per ruta dar bada skalorna finns: vilket blad som ligger overst i
    VRT:n, vad som ligger under och vad som inte hamtades."""
    ordning = _ordning(utgava)
    gjorda = {_rad_id(d): d for d in rader}
    ut = []
    for x, y in rutor:
        tackande = sorted((d for d in rader if d.status == LEVERERAT and _tacker(d, x, y)),
                          key=ordning, reverse=True)
        ovriga = [(serie, b) for serie, b in kand.get((x, y), [])
                  if _id(serie, b) not in gjorda]
        if not tackande or len({d.serie for d in tackande} | {s for s, _ in ovriga}) < 2:
            continue
        namn = (blad_alla.ruta_for(x, y) or ("", f"{x:.0f},{y:.0f}"))[1]
        topp = tackande[0]
        if any(d.ar == topp.ar and d.serie != topp.serie for d in tackande[1:]) or \
                any(b.ar == topp.ar and s != topp.serie for s, b in ovriga):
            varfor = "samma år, 1:10 000 går före"
        else:
            varfor = "äldsta utgåvan överst" if utgava == "aldsta" else "nyaste utgåvan överst"
        text = f"Ruta {namn}: överst {_benamn(topp.serie, topp.blad, topp.ar)} -- {varfor}"
        if tackande[1:]:
            text += "; under det " + ", ".join(
                _benamn(d.serie, d.blad, d.ar) for d in tackande[1:])
        if ovriga:
            text += "; finns också men hämtades inte: " + ", ".join(
                _benamn(s, b.ruta if s == "1:10 000" else b.katalog, b.ar) for s, b in ovriga)
        ut.append(text + ".")
    return ut


def _filnamn(blad: str, ar: int | None, utgava: str, skala: str) -> str:
    """Aret star alltid i namnet: bladen ar fran olika ar."""
    u = utgava or (str(ar) if ar else "utan_ar")
    return f"{blad}_{u}_{skala}.tif"


def _blad_10k(b, mapp: str, bladmapp: str, dst_crs: str, r: Rapportor) -> Bladrad:
    rad = Bladrad(blad=b.ruta, serie="1:10 000", ruta=(b.minx, b.miny, b.maxx, b.maxy),
                  ar=b.ar, utgava=b.utgava, kalla=b.url("tif"))
    tif = os.path.join(mapp, b.namn + ".tif")
    tfw = os.path.join(mapp, b.namn + ".tfw")
    try:
        # Varldsfilen forst: den ar liten, och ar den fel behovs inte bilden.
        if not os.path.exists(tfw):
            hamta_fil(b.url("tfw"), tfw)
        orsak = blad_alla.varldsfilens_fel(tfw, b)
        if orsak:
            return _utelamnat(rad, orsak)
        if not cache_20k.duger(tif):
            r.steg(f"Hämtar {b.namn}")
            hamta_fil(b.url("tif"), tif)
        utfil = os.path.join(bladmapp, _filnamn(b.ruta, b.ar, b.utgava, "10k"))
        klipp.klipp(tif, rad.ruta, utfil, dst_crs, 1.0)
    except Exception as e:                      # noqa: BLE001
        return _utelamnat(rad, f"gick inte att hämta eller skriva ({e})")
    rad.status, rad.metod, rad.fil = LEVERERAT, "världsfil", utfil
    rad.rad = (f"Ekonomiska kartan 1:10 000, blad {b.ruta} ({b.utgava}): georefererat av "
               f"Lantmäteriet (världsfil, granskad). Lägesfelet är inte mätt av pluginet.")
    return rad


def _utelamnat(rad: Bladrad, orsak: str) -> Bladrad:
    rad.status, rad.orsak = UTELAMNAT, orsak
    rad.rad = (f"Ekonomiska kartan {rad.serie}, blad {rad.blad} "
               f"({rad.utgava or rad.ar or 'utan år'}): utelämnat -- {orsak}. "
               f"Bladet finns och kan hämtas för hand.")
    return rad


def _blad_20k(b, mapp: str, bladmapp: str, dst_crs: str, r: Rapportor) -> Bladrad:
    ruta = (b.minx, b.maxy - BLAD_20K_M, b.minx + BLAD_20K_M, b.maxy)
    rad = Bladrad(blad=b.katalog, serie="1:20 000", ruta=ruta, ar=b.ar,
                  utgava=str(b.ar) if b.ar else "", kalla=b.url)
    try:
        geo, text = _ur_hk_cache(b, mapp)
        if text is None:
            geo, text, _ = cache_20k.blad_20k(b, mapp, r.info, r.steg)
    except Exception as e:                      # noqa: BLE001
        return _utelamnat(rad, f"gick inte att hämta ({e})")
    d = cache_20k.las_matt(mapp, b.katalog)
    m = d.get("matt") or {}
    rad.rad = text
    rad.metod = m.get("metod") or ""
    for k in ("passpunkter", "streck", "kors", "loo_medel_m", "loo_p95_m"):
        setattr(rad, k, m.get(k))
    if rad.metod == "kant":
        rad.anm = ANM_KANT
    if not geo:
        rad.status, rad.orsak = UTELAMNAT, d.get("orsak") or "klarade inte spärrarna"
        return rad
    try:
        utfil = os.path.join(bladmapp, _filnamn(b.katalog, b.ar, rad.utgava, "20k"))
        klipp.klipp(geo, ruta, utfil, dst_crs, rutnat_20k.PIXEL_M)
    except Exception as e:                      # noqa: BLE001
        return _utelamnat(rad, f"georefererat men gick inte att skriva ({e})")
    rad.status, rad.fil = LEVERERAT, utfil
    return rad


def _ur_hk_cache(b, mapp: str) -> tuple[str | None, str | None]:
    """Ett blad som LM Historiska kartor har georefererat i ett delat arkiv:
    dess json saknar raden till rapporten, och cache_20k.blad_20k skulle
    stupa pa den. Med samma metodversion ar utfallet detsamma, sa bladet
    anvands -- utan matt. (None, None) om cachen inte ar en sadan."""
    logg = os.path.join(mapp, b.katalog + "_rt90.json")
    if not os.path.exists(logg):
        return None, None
    with open(logg, encoding="utf-8") as f:
        d = json.load(f)
    if "rad" in d or d.get("version") != rutnat_20k.METOD_VERSION:
        return None, None
    geo = os.path.join(mapp, b.katalog + "_rt90.tif")
    arstr = f" ({b.ar})" if b.ar else ""
    if d.get("ok") and cache_20k.duger(geo):
        return geo, (f"Ekonomiska kartan 1:20 000, blad {b.katalog}{arstr}: georefererat "
                     f"sedan tidigare (av LM Historiska kartor, samma metod); lägesfelet "
                     f"finns inte i arkivet.")
    if not d.get("ok"):
        return None, (f"Ekonomiska kartan 1:20 000, blad {b.katalog}{arstr}: utelämnat -- "
                      f"{d.get('orsak', '')}. Bladet finns och kan hämtas för hand.")
    return None, None

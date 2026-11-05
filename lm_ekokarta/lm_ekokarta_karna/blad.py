"""Ekonomiska kartan (1935-1978) fran Lantmateriets oppna data.

Avgiftsfri, CC0, anonym FTP -- ingen Geotorget-autentisering behovs. Det gor den
enklare att bygga in an bade laserdata och ortofoto.

Kartan redovisar fastigheter, bebyggelse, odlingsomraden, ortnamn och
**fornminnen** i skala 1:10 000, i Norrlands inland 1:20 000. Som faltunderlag ar
den framst nyttig for att se markanvandning och bebyggelse fore det moderna
skogsbruket -- torp, akerlappar och vagar som inte langre syns.

**Bladindelningen ar aritmetisk.** Filnamnet kodar laget, sa inget index behover
hamtas trots att serien har omkring 9 100 blad:

    133_19e6g71_0_b2.tif
        ^^^^^^^^
        19  blocknummer   -> Y
        e   blockbokstav  -> X
        6   bladsiffra    -> Y inom blocket
        g   bladbokstav   -> X inom blocket
        71  ar            -> 1971

Verifierat mot tio varldsfiler utan avvikelse. Notera att varldsfilen anger
bladets OVRE kant -- den forsta harledningen hade Y 5 000 m fel darfor.

Bladen ar 5 x 5 km med 1 m pixlar i **EPSG:3021 (RT 90 2,5 gon V)**, samma system
som de historiska ortofotona. TIFF-filen bar inget CRS alls: det finns bara i
varldsfilen och .TAB-filen, sa systemet maste anges uttryckligen vid
omprojicering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

VARD = "download-opendata.lantmateriet.se"
ROT = f"ftp://{VARD}/Ekonomiska_kartan"
CRS = "EPSG:3021"
BLAD_M = 5000.0
PIXEL_M = 1.0

_MONSTER = re.compile(
    r"^(?P<serie>\d+)_(?P<blocknr>\d{2})(?P<blockbok>[a-z])"
    r"(?P<siffra>\d)(?P<bladbok>[a-z])(?P<ar>\d{2})_(?P<rest>.+)$",
    re.IGNORECASE)


@dataclass(frozen=True)
class Blad:
    namn: str            # utan filandelse
    block: str           # katalogen, t.ex. "19e"
    minx: float
    maxy: float
    ar: int

    @property
    def maxx(self) -> float:
        return self.minx + BLAD_M

    @property
    def miny(self) -> float:
        return self.maxy - BLAD_M

    def url(self, andelse: str = "tif") -> str:
        return f"{ROT}/{self.block}/{self.namn}.{andelse}"


def tolka(filnamn: str) -> Blad:
    """Filnamn -> blad med utbredning i RT 90."""
    namn = re.sub(r"\.(tif|tfw|TAB)$", "", filnamn, flags=re.IGNORECASE)
    m = _MONSTER.match(namn)
    if not m:
        raise ValueError(
            f"'{filnamn}' följer inte ekonomiska kartans namnkonvention "
            f"(t.ex. 133_19e6g71_0_b2.tif).")
    d = m.groupdict()
    blocknr = int(d["blocknr"])
    x = (1200000
         + (ord(d["blockbok"].lower()) - ord("a")) * 50000
         + (ord(d["bladbok"].lower()) - ord("a")) * 5000)
    y = 6055000 + blocknr * 50000 + int(d["siffra"]) * 5000
    ar = int(d["ar"])
    return Blad(namn=namn, block=f"{d['blocknr']}{d['blockbok'].lower()}",
                minx=float(x), maxy=float(y), ar=1900 + ar)


def blad_for(minx: float, miny: float, maxx: float, maxy: float) -> list[tuple[str, str]]:
    """Vilka block och blad tacker en utbredning angiven i RT 90?

    Returnerar (block, bladbeteckning) som `("19e", "6g")`. Filnamnet gar inte
    att rakna fram -- serienummer och ar star i det -- sa katalogen maste listas
    for att hitta den faktiska filen.
    """
    ut: list[tuple[str, str]] = []
    x0 = int(minx // BLAD_M) * int(BLAD_M)
    y0 = int(miny // BLAD_M) * int(BLAD_M)
    x = x0
    while x < maxx:
        y = y0
        while y < maxy:
            maxy_blad = y + BLAD_M
            bx = int((x - 1200000) // 50000)
            sx = int(((x - 1200000) % 50000) // 5000)
            blocknr = int((maxy_blad - 6055000) // 50000)
            siffra = int(((maxy_blad - 6055000) % 50000) // 5000)
            if 0 <= bx < 26 and 0 <= sx < 26 and 0 <= siffra <= 9 and blocknr > 0:
                ut.append((f"{blocknr:02d}{chr(ord('a') + bx)}",
                           f"{siffra}{chr(ord('a') + sx)}"))
            y += int(BLAD_M)
        x += int(BLAD_M)
    return ut


def lista_katalog(block: str, tidsgrans: int = 60) -> list[str]:
    """Filnamnen i ett block. Anonym FTP, ingen autentisering."""
    import ftplib
    f = ftplib.FTP(VARD, timeout=tidsgrans)
    try:
        f.login()                              # anonymt
        f.cwd(f"/Ekonomiska_kartan/{block}")
        return f.nlst()
    finally:
        try:
            f.quit()
        except Exception:
            f.close()


def hitta_blad(minx: float, miny: float, maxx: float, maxy: float) -> list[Blad]:
    """Blad som tacker utbredningen, med de faktiska filnamnen ur katalogen.

    Serien har luckor: alla berakade blad finns inte. Saknade hoppas over tyst
    har -- anroparen far jamfora antalet mot det begarda.
    """
    onskade: dict[str, set[str]] = {}
    for block, blad in blad_for(minx, miny, maxx, maxy):
        onskade.setdefault(block, set()).add(blad.lower())

    funna: list[Blad] = []
    for block, blad in sorted(onskade.items()):
        try:
            filer = lista_katalog(block)
        except Exception:
            continue
        for fil in filer:
            if not fil.lower().endswith(".tif"):
                continue
            try:
                b = tolka(fil)
            except ValueError:
                continue
            nyckel = fil.split("_")[1][3:5].lower()
            if nyckel in blad:
                funna.append(b)
    return sorted(funna, key=lambda b: (b.maxy, b.minx))


# ---------------------------------------------------------------------------
# 1:20 000-serien over Norrlands inland
#
# Over Norrlands inland -- alltsa over det mesta av Jamtland -- gavs ekonomiska
# kartan ut i **1:20 000**, inte 1:10 000. De bladen ligger i en egen katalog
# och foljer varken samma namngivning, samma bladstorlek eller samma
# leveransform som 1:10 000-serien:
#
#   * Bladet ar 10 x 10 km, alltsa tva 5 km-rutor i vardera led:
#     `J141-16E4-5g-h74` = block 16E, raderna 4 och 5, kolumnerna g och h.
#   * Katalogen innehaller EN fil, sjalva TIFF:en. Det finns ingen varldsfil,
#     ingen .TAB och ingen georeferens i filen -- och bladen star inte heller i
#     `EkoRutor.shp`, indexet som tacker 1:10 000-serien.
#   * Skanningen ar av hela kartbladet med teckenforklaring, titel och marginal.
#     Kartytan ar 5000 x 5000 pixlar nagonstans inne i en bild pa cirka
#     6500 x 6185 pixlar, och var den borjar star ingenstans.
#
# Forr namngavs bladen bara, sa att den som behovde kartan kunde hamta och
# georeferera den for hand. Sedan 2026-09-27 georefereras de mot kartans eget
# tryckta kilometerrutnat (verktyg/rutnat_20k) och gar in i samma mosaik som
# 1:10 000-serien. Blad som inte klarar sparrarna lamnas utanfor, med orsaken.

KATALOG_20K = "Norrlands_inland"
BLAD_20K_M = 10000.0

_MONSTER_20K = re.compile(
    r"^J(?P<serie>\d{3})-(?P<blocknr>\d{1,2})(?P<blockbok>[A-Za-z])"
    r"(?P<r1>\d)-(?P<r2>\d)(?P<c1>[a-z])-(?P<c2>[a-z])(?P<ar>\d{2})?",
    re.IGNORECASE)


@dataclass(frozen=True)
class Blad20k:
    katalog: str         # katalognamnet pa servern
    minx: float
    maxy: float
    ar: int | None

    @property
    def maxx(self) -> float:
        return self.minx + BLAD_20K_M

    @property
    def miny(self) -> float:
        return self.maxy - BLAD_20K_M

    @property
    def url(self) -> str:
        return f"{ROT}/{KATALOG_20K}/{self.katalog}"


def tolka_20k(katalognamn: str) -> Blad20k:
    """Katalognamn -> blad med utbredning i RT 90.

    Samma rutindelning som 1:10 000-serien, bara tva rutor breda och hoga.
    Kontrollen att det stammer ar att serierna motts utan glapp: i block 16e
    slutar 1:10 000-bladen vid N 6 870 000, och dar borjar 16E4-5.
    """
    m = _MONSTER_20K.match(katalognamn.strip())
    if not m:
        raise ValueError(f"'{katalognamn}' följer inte 1:20 000-seriens namnform "
                         f"(t.ex. J141-16E4-5g-h74).")
    d = m.groupdict()
    x = (1200000
         + (ord(d["blockbok"].lower()) - ord("a")) * 50000
         + (ord(d["c1"].lower()) - ord("a")) * 5000)
    # Siffran anger bladets ovre kant, som i 1:10 000-serien. Bladet tacker tva
    # rader, sa den hogre av dem ar overkanten.
    y = 6055000 + int(d["blocknr"]) * 50000 + max(int(d["r1"]), int(d["r2"])) * 5000
    ar = int(d["ar"]) if d["ar"] else None
    return Blad20k(katalog=katalognamn.strip(), minx=float(x), maxy=float(y),
                   ar=1900 + ar if ar is not None else None)


def hitta_blad_20k(minx: float, miny: float, maxx: float,
                   maxy: float) -> list[Blad20k]:
    """1:20 000-blad som skar utbredningen. Tom lista om katalogen inte gar att na."""
    try:
        namn = lista_katalog(KATALOG_20K)
    except Exception:
        return []
    ut: list[Blad20k] = []
    for n in namn:
        try:
            b = tolka_20k(n)
        except ValueError:
            continue
        if b.minx < maxx and b.maxx > minx and b.miny < maxy and b.maxy > miny:
            ut.append(b)
    return sorted(ut, key=lambda b: (b.maxy, b.minx))


def fil_20k(blad: Blad20k) -> str:
    """URL till bladets TIFF. Katalogen innehaller en enda fil, men dess namn
    (`141_17c6-7g-h76_0.tif`) harleds inte ur katalognamnet -- det lases."""
    namn = [n for n in lista_katalog(f"{KATALOG_20K}/{blad.katalog}")
            if n.lower().endswith(".tif")]
    if not namn:
        raise ValueError(f"{blad.katalog}: ingen TIFF i katalogen")
    return f"{blad.url}/{namn[0]}"

"""Bladsokning over hela ekonomiska kartan, med val av utgava. Ny 2026-11-04.

`blad.hitta_blad` ar Faltunderlagets sokning och lamnas orord. Listningen av
FTP-katalogen 2026-11-04 visade tre saker den inte klarar, och det har ar
sokningen som det nya pluginet anvander:

* **Block 1-9.** Katalogerna heter `5d`, inte `05d`, och filnamnen
  `133_5d7c55_0_b2.tif`. Monstret i `blad` kraver tva siffror, sa 4 893 av
  seriens 12 016 TIFF-filer -- hela sodra Sverige -- hittas aldrig.
* **Tillagg efter artalet.** `133_5g1a43-3_0_b2.tif`: 94 filer.
* **Flera utgavor av samma blad.** 329 blad finns i mer an en utgava, och
  `hitta_blad` tar med alla. I en mosaik blir det slumpen som avgor vilket
  ar som syns.

Rattningen ska foras over till Faltunderlaget (se CLAUDE.md).

Dessutom: **varldsfilen granskas.** Omkring 1,5 % av utgavorna ar skannade
storre an sin ruta, och for dem har Lantmateriet skrivit en varldsfil som
trycker ihop hela skanningen till en ruta (pixelstorlek under 1 m). Bladet
ligger da fel. `varldsfilens_fel` hittar dem; anroparen lamnar dem utanfor.

1:20 000-serien har en utgava per omrade (1 046 omraden, provat samma dag),
men `valj_utgava` anvands for bada serierna.
"""
from __future__ import annotations

import ftplib
import re
from dataclasses import dataclass

from .blad import (BLAD_20K_M, BLAD_M, KATALOG_20K, ROT, VARD, Blad20k,
                   tolka_20k)

X0 = 1200000.0          # rutnatets vastra kant, RT 90
Y0 = 6055000.0          # ... och nollan for blocknumren (OVRE kanten)
BLOCK_M = 50000.0

UTGAVOR = ("nyaste", "aldsta", "alla")

_MONSTER = re.compile(
    r"^(?P<serie>\d+)_(?P<blocknr>\d{1,2})(?P<blockbok>[a-z])"
    r"(?P<siffra>\d)(?P<bladbok>[a-z])(?P<ar>\d{2})(?P<tillagg>-\d+)?"
    r"_(?P<rest>.+)$",
    re.IGNORECASE)


@dataclass(frozen=True)
class Blad10k:
    namn: str            # filnamnet utan andelse
    katalog: str         # blockkatalogen pa servern, t.ex. "5d" eller "19e"
    ruta: str            # bladbeteckningen, t.ex. "19e6g"
    minx: float
    maxy: float
    ar: int
    tillagg: str = ""    # "-3" i 133_5g1a43-3_0_b2

    @property
    def maxx(self) -> float:
        return self.minx + BLAD_M

    @property
    def miny(self) -> float:
        return self.maxy - BLAD_M

    @property
    def utgava(self) -> str:
        return f"{self.ar}{self.tillagg}"

    def url(self, andelse: str = "tif") -> str:
        return f"{ROT}/{self.katalog}/{self.namn}.{andelse}"


def tolka_10k(filnamn: str) -> Blad10k:
    """Filnamn -> blad med utbredning i RT 90, aven i block 1-9."""
    namn = re.sub(r"\.(tif|tfw|TAB)$", "", filnamn, flags=re.IGNORECASE)
    m = _MONSTER.match(namn)
    if not m:
        raise ValueError(
            f"'{filnamn}' följer inte ekonomiska kartans namnkonvention "
            f"(t.ex. 133_19e6g71_0_b2.tif).")
    d = m.groupdict()
    blocknr = int(d["blocknr"])
    bb, sb = d["blockbok"].lower(), d["bladbok"].lower()
    x = X0 + (ord(bb) - ord("a")) * BLOCK_M + (ord(sb) - ord("a")) * BLAD_M
    y = Y0 + blocknr * BLOCK_M + int(d["siffra"]) * BLAD_M
    return Blad10k(namn=namn, katalog=f"{blocknr}{bb}",
                   ruta=f"{blocknr}{bb}{d['siffra']}{sb}",
                   minx=x, maxy=y, ar=1900 + int(d["ar"]),
                   tillagg=d["tillagg"] or "")


def ruta_for(minx: float, maxy: float) -> tuple[str, str] | None:
    """(katalog, bladbeteckning) for 5 km-rutan med ovre vanstra hornet
    (minx, maxy). None utanfor seriens rutnat."""
    bx = int((minx - X0) // BLOCK_M)
    sx = int(((minx - X0) % BLOCK_M) // BLAD_M)
    blocknr = int((maxy - Y0) // BLOCK_M)
    siffra = int(((maxy - Y0) % BLOCK_M) // BLAD_M)
    if not (0 <= bx < 26 and 0 <= sx < 10 and 0 <= siffra <= 9 and blocknr > 0):
        return None
    kat = f"{blocknr}{chr(ord('a') + bx)}"
    return kat, f"{kat}{siffra}{chr(ord('a') + sx)}"


def rutor(minx: float, miny: float, maxx: float, maxy: float) -> list[tuple[float, float]]:
    """5 km-rutorna (minx, maxy) som skar utbredningen, i RT 90."""
    ut = []
    x = (minx - X0) // BLAD_M * BLAD_M + X0
    while x < maxx:
        y = (miny // BLAD_M) * BLAD_M + BLAD_M      # ovre kanten
        while y - BLAD_M < maxy:
            ut.append((float(x), float(y)))
            y += BLAD_M
        x += BLAD_M
    return ut


def rutor_20k(b: Blad20k) -> list[tuple[float, float]]:
    """De fyra 5 km-rutor som ett 1:20 000-blad tacker."""
    return [(b.minx + dx, b.maxy - dy) for dx in (0.0, BLAD_M) for dy in (0.0, BLAD_M)]


class Katalogfel(Exception):
    """En katalog pa servern gick inte att lista. Inte samma sak som att
    bladet saknas -- det ska sagas, inte tigas om."""


def _lista(katalog: str, tidsgrans: int = 60) -> list[str] | None:
    """Filnamnen i en katalog. None om katalogen inte finns (ingen tackning);
    Katalogfel om servern inte svarar."""
    try:
        f = ftplib.FTP(VARD, timeout=tidsgrans)
    except Exception as e:                      # noqa: BLE001
        raise Katalogfel(f"{VARD} svarar inte ({e})")
    try:
        f.login()
        try:
            f.cwd(f"/Ekonomiska_kartan/{katalog}")
        except ftplib.error_perm:
            return None
        return [n.rsplit("/", 1)[-1] for n in f.nlst()]
    except ftplib.error_perm:
        return None
    except Exception as e:                      # noqa: BLE001
        raise Katalogfel(f"katalogen {katalog} gick inte att lista ({e})")
    finally:
        try:
            f.quit()
        except Exception:
            f.close()


def valj_utgava(blad: list, utgava: str, nyckel) -> list:
    """Behall nyaste, aldsta eller alla utgavor per omrade. `nyckel(b)` ger
    omradet; utgavor sorteras pa ar och tillagg (utan ar sist)."""
    if utgava not in UTGAVOR:
        raise ValueError(f"utgåva ska vara en av {UTGAVOR}")
    grupper: dict = {}
    for b in blad:
        grupper.setdefault(nyckel(b), []).append(b)
    ut = []
    for lista in grupper.values():
        lista.sort(key=lambda b: (b.ar is None, b.ar or 0, getattr(b, "tillagg", "")))
        ut.extend(lista if utgava == "alla"
                  else [lista[-1] if utgava == "nyaste" else lista[0]])
    return sorted(ut, key=lambda b: (b.maxy, b.minx, b.ar or 0))


def hitta_10k(onskade: list[tuple[float, float]], utgava: str = "nyaste"
              ) -> tuple[list[Blad10k], list[str]]:
    """1:10 000-blad for 5 km-rutorna. (blad, fel): fel ar katalogerna som
    inte gick att lista, sa att en lucka inte tas for en lucka i serien."""
    per_katalog: dict[str, set[str]] = {}
    for x, y in onskade:
        r = ruta_for(x, y)
        if r:
            per_katalog.setdefault(r[0], set()).add(r[1])
    funna: list[Blad10k] = []
    fel: list[str] = []
    for kat, beteckningar in sorted(per_katalog.items()):
        try:
            filer = _lista(kat)
        except Katalogfel as e:
            fel.append(str(e))
            continue
        for fil in filer or []:
            if not fil.lower().endswith(".tif"):
                continue
            try:
                b = tolka_10k(fil)
            except ValueError:
                continue
            if b.ruta in beteckningar:
                funna.append(b)
    return valj_utgava(funna, utgava, lambda b: b.ruta), fel


def hitta_20k(onskade: list[tuple[float, float]], utgava: str = "nyaste"
              ) -> tuple[list[Blad20k], list[str]]:
    """1:20 000-blad som tacker nagon av 5 km-rutorna. (blad, fel)."""
    try:
        namn = _lista(KATALOG_20K) or []
    except Katalogfel as e:
        return [], [str(e)]
    mangd = set(onskade)
    funna = []
    for n in namn:
        try:
            b = tolka_20k(n)
        except ValueError:
            continue
        if mangd.intersection(rutor_20k(b)):
            funna.append(b)
    return valj_utgava(funna, utgava, lambda b: (b.minx, b.maxy)), []


def varldsfilens_fel(tfw: str, b: Blad10k) -> str:
    """Tom strang om varldsfilen lagger bladet ratt: 1 m pixlar utan vridning
    och forsta pixelns mitt en halv meter innanfor bladets ovre vanstra horn.
    Annars orsaken, i klartext."""
    try:
        with open(tfw, encoding="ascii", errors="replace") as f:
            v = [float(t) for t in f.read().split()]
    except (OSError, ValueError) as e:
        return f"världsfilen går inte att läsa ({e})"
    if len(v) != 6:
        return f"världsfilen har {len(v)} tal, inte 6"
    a, d, b_, e, c, f_ = v
    if abs(a - 1.0) > 1e-6 or abs(e + 1.0) > 1e-6:
        return (f"världsfilen anger {a:.4f} × {-e:.4f} m pixlar i stället för 1 m: "
                f"skanningen är större än bladet och har tryckts ihop till en ruta, "
                f"så kartan ligger fel")
    if abs(d) > 1e-9 or abs(b_) > 1e-9:
        return "världsfilen anger en vriden bild"
    if abs(c - (b.minx + 0.5)) > 1.0 or abs(f_ - (b.maxy - 0.5)) > 1.0:
        return (f"världsfilens hörn ({c - 0.5:.0f}, {f_ + 0.5:.0f}) stämmer inte med "
                f"bladnamnets ({b.minx:.0f}, {b.maxy:.0f})")
    return ""


def omrade_20k(b: Blad20k) -> tuple[float, float, float, float]:
    return b.minx, b.maxy - BLAD_20K_M, b.minx + BLAD_20K_M, b.maxy

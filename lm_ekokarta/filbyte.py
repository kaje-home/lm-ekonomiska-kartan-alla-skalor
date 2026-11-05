"""En fardig fil pa sin plats, aven nar den gamla ar last.

Bara standardbiblioteket. Allt pluginet levererar skrivs forst som en
halvfardig fil (filer.halvfardig) och byts sedan in under sitt namn. Pa
Windows gar det inte nar den gamla filen ar oppen i ett annat program --
vanligast att uttaget fran forra korningen ar inlast i QGIS. Da far den nya
filen ett reservnamn, `stam.ny.ext`, `stam.ny2.ext` ..., och det sags i
loggen; uttaget kraschar inte. Nasta gang malet gar att skriva tas
reservfilerna bort.

**GeoPackage** ar SQLite: en -wal- eller -shm-fil bredvid malet hor till den
gamla databasen och skulle laggas pa den nya. De tas bort forst; gar det inte
ar databasen oppen, och reservnamnet anvands.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Callable

MAX_RESERV = 50


def reservnamn(mal: str, n: int) -> str:
    stam, ext = os.path.splitext(mal)
    return f"{stam}.ny{'' if n == 1 else n}{ext}"


def _sidofiler(mal: str) -> list[str]:
    return [mal + "-wal", mal + "-shm"] if mal.lower().endswith(".gpkg") else []


def _byt(tmp: str, mal: str) -> None:
    for f in _sidofiler(mal):
        if os.path.exists(f):
            os.remove(f)                 # PermissionError: databasen ar oppen
    os.replace(tmp, mal)


def reserver(mal: str) -> list[str]:
    """Reservfilerna for `mal` som finns pa disken."""
    stam, ext = os.path.splitext(mal)
    m = re.compile(re.escape(os.path.basename(stam)) + r"\.ny\d*" + re.escape(ext) + "$")
    return [f for f in glob.glob(glob.escape(stam) + ".ny*" + ext)
            if m.match(os.path.basename(f))]


def stada_reserver(mal: str) -> None:
    """Reservfiler fran tidigare korningar; de som fortfarande ar oppna far ligga."""
    for f in reserver(mal):
        for g in [f] + _sidofiler(f):
            try:
                if os.path.exists(g):
                    os.remove(g)
            except OSError:
                pass


def byt_in(tmp: str, mal: str, varna: Callable[[str], None] = print) -> str:
    """Den fardiga `tmp` till `mal`, eller till ett reservnamn om `mal` ar
    last. Returnerar namnet filen fick."""
    try:
        _byt(tmp, mal)
    except PermissionError:
        pass
    else:
        stada_reserver(mal)
        return mal
    for n in range(1, MAX_RESERV + 1):
        alt = reservnamn(mal, n)
        try:
            _byt(tmp, alt)
        except PermissionError:
            continue
        varna(f"{os.path.basename(mal)} är öppen i ett annat program, troligen inläst i "
              f"QGIS från en tidigare körning, och kunde inte skrivas över. Den nya filen "
              f"heter {os.path.basename(alt)}.")
        return alt
    raise PermissionError(f"{mal} och {MAX_RESERV} reservnamn är låsta")

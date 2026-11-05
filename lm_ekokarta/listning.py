"""Hela ekonomiska kartan pa FTP:n, listad en gang och cachad med datum.

Bara ftplib, inga QGIS-importer. Bladrutnatet (rutnat.py) bygger pa den har
listningen. Sjalva uttaget listar fortfarande de kataloger det behover nar
det kors, sa att det aldrig hamtar efter en gammal listning.

**En anslutning for alla kataloger.** 1:10 000-serien ligger i 173
blockkataloger (`1c` .. `27n`) och 1:20 000-serien i en (`Norrlands_inland`).
`blad_alla._lista` oppnar en ny anslutning per katalog, vilket ar ratt for
ett uttag som behover nagra fa men onodigt langsamt for alla 174.

**Cachen** ar en JSON-fil: `{"datum": "2026-11-05", "10k": {katalog: [filnamn]},
"20k": [katalognamn]}`. Den skrivs forst nar hela listningen gick igenom --
en avbruten listning lamnar den gamla kvar.
"""
from __future__ import annotations

import datetime
import ftplib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable

from .lm_ekokarta_karna import blad_alla
from .lm_ekokarta_karna.blad import KATALOG_20K, VARD, Blad20k, tolka_20k
from .lm_ekokarta_karna.filer import halvfardig

_BLOCK = re.compile(r"^\d{1,2}[a-z]$", re.IGNORECASE)
CACHEFIL = "listning.json"


@dataclass
class Listning:
    datum: str                                            # ISO-datum
    filer_10k: dict[str, list[str]] = field(default_factory=dict)
    kataloger_20k: list[str] = field(default_factory=list)

    def blad_10k(self) -> list[blad_alla.Blad10k]:
        ut = []
        for filer in self.filer_10k.values():
            for f in filer:
                try:
                    ut.append(blad_alla.tolka_10k(f))
                except ValueError:
                    pass
        return ut

    def blad_20k(self) -> list[Blad20k]:
        ut = []
        for k in self.kataloger_20k:
            try:
                ut.append(tolka_20k(k))
            except ValueError:
                pass
        return ut


def _namn(rad: str) -> str:
    return rad.rsplit("/", 1)[-1]


def lista(cachefil: str, ny: bool = False, steg: Callable[[str], None] = print,
          framsteg: Callable[[float], None] = lambda p: None,
          avbruten: Callable[[], bool] = lambda: False) -> Listning:
    """Listningen ur cachen, eller fran FTP:n om cachen saknas eller `ny`.

    Katalogfel om servern inte svarar; da ar cachen orord."""
    if not ny and os.path.exists(cachefil):
        with open(cachefil, encoding="utf-8") as f:
            d = json.load(f)
        return Listning(d["datum"], d["10k"], d["20k"])
    try:
        ftp = ftplib.FTP(VARD, timeout=60)
    except Exception as e:                       # noqa: BLE001
        raise blad_alla.Katalogfel(f"{VARD} svarar inte ({e})")
    try:
        ftp.login()
        ftp.cwd("/Ekonomiska_kartan")
        block = sorted((_namn(n) for n in ftp.nlst() if _BLOCK.match(_namn(n))),
                       key=lambda k: (int(k[:-1]), k[-1]))
        filer: dict[str, list[str]] = {}
        for i, k in enumerate(block, 1):
            if avbruten():
                raise blad_alla.Katalogfel("listningen avbröts")
            steg(f"Listar {k} ({i}/{len(block) + 1})")
            ftp.cwd(f"/Ekonomiska_kartan/{k}")
            filer[k] = sorted(_namn(n) for n in ftp.nlst() if n.lower().endswith(".tif"))
            framsteg(95 * i / (len(block) + 1))
        steg(f"Listar {KATALOG_20K}")
        ftp.cwd(f"/Ekonomiska_kartan/{KATALOG_20K}")
        k20 = sorted(_namn(n) for n in ftp.nlst())
    except blad_alla.Katalogfel:
        raise
    except Exception as e:                       # noqa: BLE001
        raise blad_alla.Katalogfel(f"FTP-katalogen gick inte att lista ({e})")
    finally:
        try:
            ftp.quit()
        except Exception:                        # noqa: BLE001
            ftp.close()
    lis = Listning(datetime.date.today().isoformat(), filer, k20)
    os.makedirs(os.path.dirname(os.path.abspath(cachefil)), exist_ok=True)
    tmp = halvfardig(cachefil)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"datum": lis.datum, "10k": lis.filer_10k, "20k": lis.kataloger_20k},
                  f, ensure_ascii=False)
    os.replace(tmp, cachefil)
    return lis

"""Nedladdning over anonym FTP fran Lantmateriets oppna data.

Flyttad ur lm_faltunderlag/algoritmer/hamta_ekokarta.py (`_hamta_fil`) utan
andring.
"""
from __future__ import annotations

import os

from .filer import Levererades_inte, halvfardig, stada_gamla_delvis


def hamta_fil(url: str, mal: str, tidsgrans: int = 300) -> str:
    """Hamta en fil over anonym FTP.

    ftplib i stallet for QgsFileDownloader: Qt5:s FTP-stod ar borttaget i Qt6,
    och QGIS ar pa vag dit. Priset ar att QGIS proxykonfiguration inte foljer
    med -- star man bakom en proxy som blockerar FTP maste den oppnas separat.
    """
    import ftplib
    from urllib.parse import urlparse
    u = urlparse(url)
    os.makedirs(os.path.dirname(mal), exist_ok=True)
    tillfallig = halvfardig(mal)
    # Overgivna mellanled fran korningar som dog. Sedan mellanledet fick
    # dator och process i namnet kan ingen annan skriva over dem, sa de
    # maste sopas bort uttryckligen -- se filer.stada_gamla_delvis.
    stada_gamla_delvis(mal)
    f = ftplib.FTP(u.hostname, timeout=tidsgrans)
    try:
        f.login()
        with open(tillfallig, "wb") as ut:
            f.retrbinary(f"RETR {u.path}", ut.write)
    finally:
        try:
            f.quit()
        except Exception:
            f.close()
    if os.path.getsize(tillfallig) == 0:
        os.remove(tillfallig)
        raise Levererades_inte(f"{os.path.basename(mal)} kom tom.")
    os.replace(tillfallig, mal)
    return mal

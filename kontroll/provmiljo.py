"""Gemensamt for proven i QGIS utan granssnitt: argument, QGIS och providern.

Proven kors med QGIS egen Python, till exempel

    "C:\\Program Files\\QGIS 3.44.14\\bin\\python-qgis-ltr.bat" kontroll/prov_rutnat.py
    "C:\\Program Files\\QGIS 4.2.3\\bin\\python-qgis.bat" kontroll/prov_rutnat.py --ut D:\\prov\\q4

QGIS far en tom profil i en tempmapp; anvandarens profil ror proven inte.
Utmappen toms fore varje korning, men bara om den ar tom eller skapad av ett
tidigare prov (markfilen PROVMARKE) -- en fel angiven mapp raderas aldrig.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

HAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repots rot
PROV = r"C:\Claude_projekt\ekokartan-prov"     # provmappen pa utvecklingsdatorn
PROVMARKE = ".lm_ekokarta_prov"


def argument(beskrivning: str, standard_ut: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=beskrivning)
    p.add_argument("--plugin", default=HAR,
                   help="mappen som innehaller lm_ekokarta/ (forval: det har repot; "
                        "for zip-provet: mappen zip-filen packats upp i)")
    p.add_argument("--arkiv", default=os.path.join(PROV, "arkiv"),
                   help="arkiv med listningen och Sveg- och Stromsundsbladen "
                        f"(forval {os.path.join(PROV, 'arkiv')})")
    p.add_argument("--ut", default=os.path.join(PROV, standard_ut),
                   help=f"utmapp, toms forst (forval {os.path.join(PROV, standard_ut)})")
    return p


def utmapp(ut: str) -> str:
    ut = os.path.abspath(ut)
    if os.path.isdir(ut) and os.listdir(ut):
        if not os.path.exists(os.path.join(ut, PROVMARKE)):
            sys.exit(f"{ut} ar inte tom och inte skapad av ett prov; valj en annan --ut")
        shutil.rmtree(ut)
    os.makedirs(ut, exist_ok=True)
    open(os.path.join(ut, PROVMARKE), "w").close()
    return ut


def starta(plugin: str):
    """QGIS utan granssnitt, Processing och pluginets provider. (app, processing, provider)"""
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qgis.core import Qgis, QgsApplication
    app = QgsApplication([], True, tempfile.mkdtemp(prefix="lm_ekokarta_profil_"))
    app.initQgis()
    print("QGIS", Qgis.version())
    sys.path.insert(0, os.path.join(QgsApplication.prefixPath(), "python", "plugins"))
    from processing.core.Processing import Processing
    Processing.initialize()
    import processing
    sys.path.insert(0, os.path.abspath(plugin))
    import lm_ekokarta
    print("paket:", os.path.dirname(lm_ekokarta.__file__))
    from lm_ekokarta.provider import Provider
    prov = Provider()                  # maste leva kvar, annars gar createInstance fel
    QgsApplication.processingRegistry().addProvider(prov)
    print("algoritmer:", [a.id() for a in prov.algorithms()])
    return app, processing, prov


class Utfall:
    """Samlar kontrollerna; slut() skriver sammanfattningen och avslutar."""

    def __init__(self):
        self.fel: list[str] = []

    def krav(self, villkor: bool, text: str) -> bool:
        print(("  ok   " if villkor else "  FEL  ") + text)
        if not villkor:
            self.fel.append(text)
        return villkor

    def slut(self, app) -> None:
        app.exitQgis()
        if self.fel:
            print(f"\n{len(self.fel)} KRAV EJ UPPFYLLDA:")
            for f in self.fel:
                print("  " + f)
            sys.exit(1)
        print("\nALLA KRAV UPPFYLLDA")

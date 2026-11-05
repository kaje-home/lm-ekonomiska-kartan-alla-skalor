"""Dialogens rutnatsval i QGIS utan granssnitt: Bygg bladrutnat som
bakgrundsuppgift (tva ganger, sa att ett inlast bladrutnat ersatts), rutan
16e2h markerad, Hamta med brickor.

    python-qgis-ltr.bat kontroll/prov_dialog_rutnat.py [--plugin MAPP] [--arkiv MAPP]
                                                       [--ut MAPP]

Bladrutnatet byggs i utmappen, inte i arkivet. Arkivet ska ha listningen och
16e2h med 1:20 000-bladet J141-16E2-3g-h77 (se prov_rutnat.py). Knappen
Skapa fast rutnat oppnar Processings dialog och provas inte har.
"""
from __future__ import annotations

import os
import time

from provmiljo import Utfall, argument, starta, utmapp

a = argument(__doc__.splitlines()[0], "dialog_rutnat").parse_args()
UT = utmapp(a.ut)
app, processing, _prov = starta(a.plugin)

from qgis.core import QgsExpression, QgsFeatureRequest, QgsProject  # noqa: E402
from qgis.gui import QgsMapCanvas  # noqa: E402

from lm_ekokarta.dialog import HamtaDialog  # noqa: E402

u = Utfall()


class Iface:
    def __init__(self):
        self.c = QgsMapCanvas()

    def mapCanvas(self):
        return self.c

    def mainWindow(self):
        return None


def vanta(villkor, s: float = 600) -> None:
    t = time.time()
    while not villkor() and time.time() - t < s:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()


d = HamtaDialog(Iface())
d._spara = lambda: None                 # anvandarens installningar ror vi inte
u.krav([b.text() for b in d.knappar.buttons()][-1] == "Rutor ur ett rutnät",
       "fjarde omradesvalet finns")
u.krav(not d.brickor.isEnabled(), "brickvalet ar avstangt utan rutnatsval")
d.arkiv.setFilePath("")
d.utmapp.setFilePath(UT)
u.krav(d._bladrutnat_fil() == os.path.join(UT, "bladrutnat.gpkg"),
       "bladrutnatet i utmappen utan arkiv")
d.arkiv.setFilePath(a.arkiv)
u.krav(d._bladrutnat_fil() == os.path.join(a.arkiv, "ekonomiska_kartan", "bladrutnat.gpkg"),
       "bladrutnatet i arkivet med arkiv")
d._bladrutnat_fil = lambda: os.path.join(UT, "bladrutnat.gpkg")

for omgang in (1, 2):
    d._bladrutnat()
    vanta(lambda: d.r_uppgift is None)
    print(f"omgang {omgang}: {d.resultat.text()}")
    lagren = [v.name() for v in QgsProject.instance().mapLayers().values()]
    u.krav(len(lagren) == 1 and lagren[0].startswith("Bladrutnät, listat "),
           f"bygg bladrutnat, omgang {omgang}: ett lager ({lagren})")
v = d.rutlager.currentLayer()
u.krav(v is not None and d.r_rutnat.isChecked(), "bladrutnatet valt som omrade")
u.krav(type(v.renderer()).__name__ == "QgsRuleBasedRenderer", "bladrutnatet stilsatt")

u.krav(d._parametrar() is None and "markerade" in d.resultat.text(),
       "utan markerade rutor vagras korningen")
v.selectByIds([f.id() for f in v.getFeatures(QgsFeatureRequest(QgsExpression("\"blad\" = '16e2h'")))])
d.brickor.setChecked(True)
d.brickpixel.setValue(2.0)
u.krav(d.brickpixel.isEnabled(), "pixelstorleken gar att andra med brickor valda")
p = d._parametrar()
u.krav(p["LAGER"].selectedFeaturesOnly and p["BRICKOR"] and p["BRICKPIXEL"] == 2.0,
       "parametrarna: markerade rutor, brickor, 2 m")
d._kor()
vanta(lambda: d.uppgift is None)
print("hamta:", d.resultat.text())
u.krav(os.listdir(os.path.join(UT, "brickor")) == ["16e2h.tif"], "brickan 16e2h.tif skriven")
u.krav("1 brickor skrivna" in d.resultat.text(), "resultatraden namner brickorna")
u.slut(app)

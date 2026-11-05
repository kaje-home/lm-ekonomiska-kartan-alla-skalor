"""Lasta filer: ett nytt uttag till samma utmapp medan lagren fran det forra
ar inlasta i QGIS. Uttaget ska ga igenom, filerna fa reservnamn och loggen
saga det; nar lagren ar borta ska de vanliga namnen tillbaka och
reservfilerna bort.

    python-qgis-ltr.bat kontroll/prov_lasta_filer.py [--plugin MAPP] [--arkiv MAPP]
                                                     [--ut MAPP]

Arkivet ska ha listningen och Sveg-bladet J141-16E2-3g-h77 (se prov_rutnat.py).
"""
from __future__ import annotations

import glob
import os

from provmiljo import Utfall, argument, starta, utmapp

a = argument(__doc__.splitlines()[0], "lasta_filer").parse_args()
UT = utmapp(a.ut)
app, processing, _prov = starta(a.plugin)

from qgis.core import (QgsExpression, QgsFeatureRequest,  # noqa: E402
                       QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback,
                       QgsProject, QgsRasterLayer, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QEvent  # noqa: E402

u = Utfall()
prj = QgsProject.instance()
UTTAG = os.path.join(UT, "uttag")


class Aterkoppling(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.varningar: list[str] = []

    def pushWarning(self, t):
        super().pushWarning(t)
        self.varningar.append(t)


def lagg_in(fil: str, namn: str):
    v = QgsVectorLayer(fil, namn, "ogr") if ".gpkg" in fil else QgsRasterLayer(fil, namn)
    assert v.isValid(), fil
    prj.addMapLayer(v)
    return v


# Bladrutnat och fyra 2,5 km-rutor inom Sveg-bladet.
res = processing.run("lmeko:bladrutnat", {"ARKIV": a.arkiv, "CRS": "EPSG:3006",
                                          "UTDATA": os.path.join(UT, "bladrutnat.gpkg")})
br = lagg_in(res["BLADRUTNAT"], "bladrutnat")
br.selectByIds([f.id() for f in br.getFeatures(QgsFeatureRequest(
    QgsExpression("\"blad\" = 'J141-16E2-3g-h77'")))])
sveg = br.selectedFeatures()[0].geometry()
r = processing.run("lmeko:fast_rutnat", {
    "LAGER": QgsProcessingFeatureSourceDefinition(br.id(), True), "STORLEK": 2.5,
    "UTDATA": os.path.join(UT, "rutnat.gpkg")})
rn = lagg_in(r["RUTNAT"], "rutnat")
rn.selectByIds([f.id() for f in rn.getFeatures() if sveg.contains(f.geometry())][:4])


def hamta(namn: str) -> tuple[dict, list[str]]:
    fb = Aterkoppling()
    res = processing.run("lmeko:hamta_ekonomiska_kartan", {
        "LAGER": QgsProcessingFeatureSourceDefinition(rn.id(), True), "CRS": "EPSG:3006",
        "ARKIV": a.arkiv, "VRT": True, "BRICKOR": True, "BRICKPIXEL": 2.0,
        "UTMAPP": UTTAG}, feedback=fb)
    print(f"{namn}: BLAD {res['BLAD']}, VRT {res['VRT_LAGER']}, "
          f"brickor {res['BRICKOR_SKRIVNA']}, {len(fb.varningar)} varningar")
    for v in fb.varningar:
        print("    " + v[:160])
    return res, fb.varningar


# 1. Forsta uttaget.
res1, _ = hamta("uttag 1")
u.krav(res1["BLAD"].startswith(os.path.join(UTTAG, "blad.gpkg")), "uttag 1: blad.gpkg")

# 2. Lagren fran uttag 1 inlasta: bladlagret, VRT:n, ett blad och en bricka.
# Bladen ar gjorda ur samma kallor och ska anvandas som de ar (en VRT som ar
# inlast i QGIS laser sina blad tills QGIS startas om); bladlagret och brickan
# ska fa reservnamn, VRT-filen sjalv ar inte last.
blad_tif = sorted(glob.glob(os.path.join(UTTAG, "blad", "*.tif")))[0]
bricka = sorted(glob.glob(os.path.join(UTTAG, "brickor", "*.tif")))[0]
bladtider = {f: os.path.getmtime(f) for f in glob.glob(os.path.join(UTTAG, "blad", "*.tif"))}
inlasta = [lagg_in(res1["BLAD"], "blad"), lagg_in(res1["VRT_LAGER"], "vrt"),
           lagg_in(blad_tif, "ett blad"), lagg_in(bricka, "en bricka")]
res2, varn2 = hamta("uttag 2, med lagren inlasta")
u.krav(res2["BLAD"].startswith(os.path.join(UTTAG, "blad.ny.gpkg")),
       "uttag 2: bladlagret under reservnamn")
u.krav(res2["VRT_LAGER"] == res1["VRT_LAGER"], "uttag 2: VRT:n under sitt vanliga namn")
u.krav({f: os.path.getmtime(f) for f in bladtider} == bladtider and
       not glob.glob(os.path.join(UTTAG, "blad", "*.ny*")),
       "uttag 2: bladen anvanda som de var, inte omskrivna")
u.krav(os.path.exists(os.path.splitext(bricka)[0] + ".ny.tif"),
       "uttag 2: den inlasta brickan under reservnamn")
u.krav(sum("kunde inte skrivas över" in v for v in varn2) == 2,
       "uttag 2: loggen namner de tva reservnamnen")
with open(os.path.join(UTTAG, "rapport.txt"), encoding="utf-8") as f:
    u.krav("Under ett nytt namn" in f.read(), "uttag 2: rapporten namner brickan med nytt namn")
v = lagg_in(res2["VRT_LAGER"], "vrt 2")
inlasta.append(v)
u.krav(v.width() > 0, "uttag 2: VRT:n gar att lasa")

# 3. Bladrutnatet byggs om medan det ar inlast.
fb = Aterkoppling()
res = processing.run("lmeko:bladrutnat", {"ARKIV": a.arkiv, "CRS": "EPSG:3006",
                                          "UTDATA": os.path.join(UT, "bladrutnat.gpkg")},
                     feedback=fb)
u.krav(res["UTDATA"].endswith("bladrutnat.ny.gpkg") and fb.varningar,
       f"bladrutnatet inlast: reservnamn och varning ({os.path.basename(res['UTDATA'])})")

# 4. Lagren borta: vanliga namn igen, reservfilerna bort.
prj.removeMapLayers([v.id() for v in inlasta])
del inlasta, v
# GeoPackage slapps forst nar lagret verkligen ar raderat.
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
res3, varn3 = hamta("uttag 3, lagren borttagna")
u.krav(res3["BLAD"].startswith(os.path.join(UTTAG, "blad.gpkg")) and
       res3["VRT_LAGER"] == res1["VRT_LAGER"] and not varn3,
       "uttag 3: vanliga namn och inga varningar")
u.krav({f: os.path.getmtime(f) for f in bladtider} == bladtider,
       "uttag 3: bladen fortfarande desamma")
rester = [os.path.relpath(f, UTTAG) for f in glob.glob(os.path.join(UTTAG, "**", "*.ny*"),
                                                       recursive=True)]
u.krav(not rester, f"uttag 3: reservfilerna borta ({rester or 'inga'})")
u.slut(app)

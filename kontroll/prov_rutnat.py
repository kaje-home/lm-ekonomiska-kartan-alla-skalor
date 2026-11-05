"""Rutnatsfunktionerna i QGIS utan granssnitt: bladrutnat, fast rutnat,
uttag med markerade rutor och brickor, pa Sveg och Stromsund.

    python-qgis-ltr.bat kontroll/prov_rutnat.py [--plugin MAPP] [--arkiv MAPP]
                                                [--ut MAPP] [--utan-stort]

Arkivet ska ha listningen (ekonomiska_kartan/listning.json) och bladen
16e2h, de atta 1:20 000-bladen J141-16E2..16E6 kring Sveg,
J141-20F6-7g-h74 (Stromsund) och J141-17F0-1e-f73 (Mullberget). Saknas de
hamtas och georefereras de, och listningen och indexet gors om (en minut);
proven blir da langsamma men ska ga igenom.

Kraven:
- bladrutnatet: bada skalorna, falten, listningsdatumet, cachestatus,
  bladnamn och de 80 delbladen ur indexet
- en markerad bladruta (16e2h) ger en bricka, 1:10 000-bladet fran 1958:
  rutan ar inte 1:20 000 enligt indexet
- Mullberget (delblad): bara den vastra halften, med bladnamn, gransida och
  delblad i rapporten
- reserv: Sveg automatiskt har ingen; bara 1:20 000 over Sveg ger 16e2h som
  reserv ur Halvar-Jonsberg, egen fil och rad; rutan 19i8a (inget
  1:10 000-blad) far reserv ur J141-19I8-9a-b67 aven automatiskt
- fast rutnat: tva korningar over grannomraden ger samma rutor och namn
- Sveg, bara 1:10 000: 4 brickor, 5 rutor utan kartdata
- Sveg automatiskt och Stromsund med 2 m: 9 brickor vardera
- brickorna: ratt pixelstorlek, horn pa pixelrutnatet, ratt storlek, 4 band,
  inga rester (.delvis, .aux.xml)
- stort uttag (1 km-rutor over Sveg, omkring 740 brickor): alla skrivna,
  minnet vaxer mindre an 300 MB
- brickor utan omradeslager vagras med ett begripligt fel
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import glob
import os
import time

from provmiljo import Utfall, argument, starta, utmapp

p = argument(__doc__.splitlines()[0], "rutnat")
p.add_argument("--utan-stort", action="store_true", help="hoppa over det stora uttaget")
a = p.parse_args()
UT = utmapp(a.ut)
ARKIV = a.arkiv
app, processing, _prov = starta(a.plugin)

from osgeo import gdal  # noqa: E402
from qgis.core import (QgsExpression, QgsFeatureRequest, QgsGeometry,  # noqa: E402
                       QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback,
                       QgsProject, QgsVectorLayer)

gdal.UseExceptions()
u = Utfall()
prj = QgsProject.instance()


def topp_minne_mb() -> float:
    """Processens hogsta arbetsminne hittills (Windows)."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.wintypes.DWORD), ("PageFaultCount", ctypes.wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                    ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    m = PMC()
    m.cb = ctypes.sizeof(m)
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p,
                                          ctypes.wintypes.DWORD]
    k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(m), m.cb)
    return m.PeakWorkingSetSize / 2**20


def lager(kalla: str, namn: str) -> QgsVectorLayer:
    v = QgsVectorLayer(kalla, namn, "ogr")
    assert v.isValid(), kalla
    prj.addMapLayer(v)
    return v


def objekt(v, uttryck: str) -> list:
    return list(v.getFeatures(QgsFeatureRequest(QgsExpression(uttryck))))


def markera(v, uttryck: str) -> int:
    v.selectByIds([f.id() for f in objekt(v, uttryck)])
    return v.selectedFeatureCount()


def hamta(namn: str, lag, **param) -> dict:
    res = processing.run("lmeko:hamta_ekonomiska_kartan", {
        "LAGER": QgsProcessingFeatureSourceDefinition(lag.id(), True), "SKALA": 0,
        "UTGAVA": 0, "CRS": "EPSG:3006", "ARKIV": ARKIV, "VRT": True, "BRICKOR": True,
        "BRICKPIXEL": 1.0, "UTMAPP": os.path.join(UT, namn), **param})
    print(f"{namn}: levererade {res['LEVERERADE']}, utelamnade {res['UTELAMNADE']}, "
          f"ar {res['AR']}, brickor {res['BRICKOR_SKRIVNA']}, tomma {res['BRICKOR_TOMMA']}")
    return res


def granska_brickor(namn: str, pixel: float, storlek: float | None) -> None:
    mapp = os.path.join(UT, namn, "brickor")
    fel = []
    for f in sorted(glob.glob(os.path.join(mapp, "*.tif"))):
        d = gdal.Open(f)
        gt = d.GetGeoTransform()
        x0, y0 = gt[0] / pixel, gt[3] / pixel
        if abs(gt[1] - pixel) > 1e-9 or abs(gt[5] + pixel) > 1e-9:
            fel.append(f"{os.path.basename(f)}: pixel {gt[1]} {gt[5]}")
        if abs(x0 - round(x0)) > 1e-6 or abs(y0 - round(y0)) > 1e-6:
            fel.append(f"{os.path.basename(f)}: horn {gt[0]} {gt[3]} utanfor pixelrutnatet")
        if storlek and (d.RasterXSize, d.RasterYSize) != (storlek / pixel, storlek / pixel):
            fel.append(f"{os.path.basename(f)}: {d.RasterXSize} x {d.RasterYSize} px")
        if d.RasterCount != 4:
            fel.append(f"{os.path.basename(f)}: {d.RasterCount} band")
    rester = [f for f in os.listdir(mapp) if not f.endswith(".tif") or ".delvis." in f]
    u.krav(not fel, f"{namn}: pixelstorlek, horn, storlek och band ({fel[:3] or 'inga fel'})")
    u.krav(not rester, f"{namn}: inga rester i brickor/ ({rester[:3] or 'inga'})")


# 1. Bladrutnatet ur listningen.
res = processing.run("lmeko:bladrutnat", {"ARKIV": ARKIV, "LISTA_OM": False, "CRS": "EPSG:3006",
                                          "UTDATA": os.path.join(UT, "bladrutnat.gpkg")})
print(f"bladrutnat: {res['RUTOR_10K']} rutor i 1:10 000, {res['BLAD_20K']} blad i 1:20 000, "
      f"listat {res['LISTAD']}")
br = lager(res["BLADRUTNAT"], "bladrutnat")
u.krav(res["RUTOR_10K"] > 11000 and res["BLAD_20K"] > 1000, "bladrutnat: bada skalorna")
u.krav(br.fields().names()[1:] == ["blad", "bladnamn", "serie", "skala", "delblad", "ar",
                                   "ar_aldsta", "ar_alla", "utgavor", "cachad", "cache",
                                   "katalog", "listad"],
       "bladrutnat: falten")
f = objekt(br, "\"blad\" = 'J141-16E2-3g-h77'")[0]
u.krav(f["ar"] == 1977 and f["listad"] == res["LISTAD"], "bladrutnat: ar och listningsdatum")
u.krav(f["cache"].startswith("georefererat"), f"bladrutnat: cachestatus ({f['cache']})")
print("  1:10 000-rutor med flera utgavor:",
      len(objekt(br, "\"skala\" = 10000 AND \"utgavor\" > 1")))
# Indexet: bladnamn och delblad. Halvar-Jonsberg ar ett L (16e2h ar
# 1:10 000), Mullberget den vastra halften.
delblad = objekt(br, "\"skala\" = 20000 AND \"delblad\" = 1")
u.krav(len(delblad) == 80 and not objekt(br, "\"skala\" = 20000 AND \"delblad\" IS NULL"),
       f"bladrutnat: 80 delblad ur indexet ({len(delblad)})")
mull = objekt(br, "\"blad\" = 'J141-17F0-1e-f73'")[0]
u.krav(f["bladnamn"] == "Halvar-Jonsberg" and f["delblad"] == 1
       and abs(f.geometry().area() / 75e6 - 1) < 0.01
       and mull["bladnamn"] == "Mullberget" and abs(mull.geometry().area() / 50e6 - 1) < 0.01,
       f"bladrutnat: bladnamn och delbladens yta ({f['bladnamn']} "
       f"{f.geometry().area() / 1e6:.1f} km², {mull['bladnamn']} "
       f"{mull.geometry().area() / 1e6:.1f} km²)")

# 2. En markerad bladruta. 16e2h ar inte 1:20 000 enligt indexet: bara
# 1:10 000-bladet fran 1958, aven om Halvar-Jonsberg (1977) ar tryckt dar.
markera(br, "\"blad\" = '16e2h'")
res = hamta("sveg_markerad", br)
u.krav(res["LEVERERADE"] == 1 and res["AR"] == "1958" and res["BRICKOR_SKRIVNA"] == 1,
       "markerad bladruta 16e2h: en bricka, 1:10 000 fran 1958")
granska_brickor("sveg_markerad", 1.0, None)

# 2b. Mullberget, bara 1:20 000: den vastra halften, georefererad utan den
# ostra kanten, som saknar streck.
markera(br, "\"blad\" = 'J141-17F0-1e-f73'")
res = hamta("mullberget", br, SKALA=2)
with open(os.path.join(UT, "mullberget", "rapport.txt"), encoding="utf-8") as f_:
    rapport = f_.read()
bl = lager(res["BLAD"], "mullberget_blad")
g_blad = [q.geometry() for q in bl.getFeatures()]
u.krav(res["LEVERERADE"] == 1 and res["BRICKOR_SKRIVNA"] == 1
       and "J141-17F0-1e-f73 Mullberget (1973)" in rapport
       and "östra kanten, mot 1:10 000-området, har inga streck" in rapport
       and "bara delvis 1:20 000: rutorna" in rapport,
       "Mullberget: levererat, med bladnamn, gransida och delblad i rapporten")
vrt = gdal.Open(res["VRT_LAGER"])
bredd = vrt.RasterXSize * vrt.GetGeoTransform()[1]
vrt = None
u.krav(len(g_blad) == 1 and abs(g_blad[0].area() / 50e6 - 1) < 0.01
       and abs(bredd / 5000 - 1) < 0.05,         # rutan ar vriden i SWEREF
       f"Mullberget: bladlagret och VRT:n bara den vastra halften "
       f"({g_blad[0].area() / 1e6:.1f} km², VRT {bredd:.0f} m bred)")
granska_brickor("mullberget", 1.0, None)

# 3. Fast rutnat over Sveg-bladet och over en del av det.
# Halvar-Jonsberg ar ett L; med 16e2h blir det hela 10 x 10 km-rutan.
SVEG = "\"blad\" IN ('J141-16E2-3g-h77', '16e2h')"
markera(br, SVEG)
sveg = QgsGeometry.unaryUnion([q.geometry() for q in objekt(br, SVEG)])
bb = sveg.boundingBox()
DEL = (f"{bb.xMinimum() + 1000},{bb.xMinimum() + 7000},"
       f"{bb.yMinimum() + 1000},{bb.yMinimum() + 6000} [EPSG:3006]")
r1 = processing.run("lmeko:fast_rutnat", {
    "LAGER": QgsProcessingFeatureSourceDefinition(br.id(), True), "STORLEK": 2.5,
    "UTDATA": os.path.join(UT, "rutnat_sveg.gpkg")})
r2 = processing.run("lmeko:fast_rutnat", {"UTBREDNING": DEL, "STORLEK": 2.5,
                                          "UTDATA": os.path.join(UT, "rutnat_sveg_del.gpkg")})
g1, g2 = lager(r1["RUTNAT"], "rutnat_sveg"), lager(r2["RUTNAT"], "rutnat_sveg_del")
n1 = {f["ruta"]: f.geometry().asWkt(0) for f in g1.getFeatures()}
n2 = {f["ruta"]: f.geometry().asWkt(0) for f in g2.getFeatures()}
u.krav(n2 and set(n2) <= set(n1) and all(n1[k] == n2[k] for k in n2),
       f"fast rutnat: samma rutor och namn i tva korningar ({len(n1)} och {len(n2)} rutor, "
       f"t.ex. {sorted(n2)[0]})")
g1.selectByIds([f.id() for f in g1.getFeatures() if sveg.contains(f.geometry())])
print(f"  {g1.selectedFeatureCount()} rutor helt inom Sveg-bladet")

# 4. Sveg, bara 1:10 000: bara 16e2h finns.
res = hamta("sveg_10k", g1, SKALA=1, VRT=False)
u.krav((res["BRICKOR_SKRIVNA"], res["BRICKOR_TOMMA"]) == (4, 5),
       "bara 1:10 000: 4 brickor, 5 rutor utan kartdata")
with open(os.path.join(UT, "sveg_10k", "rapport.txt"), encoding="utf-8") as f:
    rapport = f.read()
u.krav("Utan kartdata, hoppades över (5)" in rapport, "bara 1:10 000: tomma rutor i rapporten")
granska_brickor("sveg_10k", 1.0, 2500)

# 5. Sveg automatiskt.
res = hamta("sveg_auto", g1)
u.krav((res["BRICKOR_SKRIVNA"], res["BRICKOR_TOMMA"]) == (9, 0), "Sveg automatiskt: 9 brickor")
granska_brickor("sveg_auto", 1.0, 2500)
bl = lager(res["BLAD"], "sveg_auto_blad")
u.krav(not [q for q in bl.getFeatures() if q["reserv"] == 1],
       "Sveg automatiskt: ingen reserv, 16e2h har sitt 1:10 000-blad")


def reservrader(namn: str, res: dict) -> tuple[list, str]:
    v = lager(res["BLAD"], f"{namn}_blad")
    with open(os.path.join(UT, namn, "rapport.txt"), encoding="utf-8") as f_:
        return [q for q in v.getFeatures() if q["reserv"] == 1], f_.read()


RESERV = "reserv (utanför 1:20 000-delen enligt indexet)"

# 5b. Sveg, bara 1:20 000: Halvar-Jonsberg, och 16e2h som reserv ur samma
# blad, eftersom inget annat blad tacker rutan.
markera(br, SVEG)
res = hamta("sveg_20k", br, SKALA=2, BRICKOR=False)
res_rader, rapport = reservrader("sveg_20k", res)
filer = sorted(os.listdir(os.path.join(UT, "sveg_20k", "blad")))
u.krav(res["LEVERERADE"] == 1 and len(res_rader) == 1
       and abs(res_rader[0].geometry().area() / 25e6 - 1) < 0.01
       and res_rader[0]["anm"].startswith(RESERV)
       and "Reservdelar (delblad utanför 1:20 000-delen, där inget annat blad finns): 1" in rapport
       and f"(1977), {RESERV}: " in rapport and "Reserven täcker rutan 16e2h" in rapport
       and filer == ["J141-16E2-3g-h77_1977_20k.tif", "J141-16E2-3g-h77_1977_20k_reserv.tif"],
       f"bara 1:20 000: 16e2h som reserv, egen fil och egen rad ({filer})")
vrt = gdal.Open(res["VRT_LAGER"])
bredd = vrt.RasterXSize * vrt.GetGeoTransform()[1]
vrt = None
u.krav(abs(bredd / 10000 - 1) < 0.05, f"bara 1:20 000: VRT:n tacker hela bladet ({bredd:.0f} m)")

# 5c. Rutan 19i8a har inget 1:10 000-blad: reserv ur J141-19I8-9a-b67 aven
# i det automatiska laget.
res = processing.run("lmeko:hamta_ekonomiska_kartan", {
    "UTBREDNING": "1600500,1604500,7040500,7044500 [EPSG:3021]", "SKALA": 0, "UTGAVA": 0,
    "CRS": "EPSG:3006", "ARKIV": ARKIV, "VRT": True, "UTMAPP": os.path.join(UT, "reserv_19i8a")})
res_rader, rapport = reservrader("reserv_19i8a", res)
u.krav(res["LEVERERADE"] == 0 and len(res_rader) == 1 and res_rader[0]["blad"] == "J141-19I8-9a-b67"
       and "Rutor utan karta: 0" in rapport and "Reserven täcker rutan 19i8a" in rapport,
       f"19i8a: reserv ur J141-19I8-9a-b67, ingen ruta utan karta "
       f"({len(res_rader)} reservrader, levererade {res['LEVERERADE']})")

# 6. Stromsund, 2 m pixlar.
markera(br, "\"blad\" = 'J141-20F6-7g-h74'")
stromsund = objekt(br, "\"blad\" = 'J141-20F6-7g-h74'")[0].geometry()
r3 = processing.run("lmeko:fast_rutnat", {
    "LAGER": QgsProcessingFeatureSourceDefinition(br.id(), True), "STORLEK": 2.5,
    "UTDATA": os.path.join(UT, "rutnat_stromsund.gpkg")})
g3 = lager(r3["RUTNAT"], "rutnat_stromsund")
g3.selectByIds([f.id() for f in g3.getFeatures() if stromsund.contains(f.geometry())])
res = hamta("stromsund", g3, BRICKPIXEL=2.0, VRT=False)
u.krav((res["BRICKOR_SKRIVNA"], res["BRICKOR_TOMMA"]) == (9, 0), "Stromsund 2 m: 9 brickor")
granska_brickor("stromsund", 2.0, 2500)

# 7. Stort uttag: 1 km-rutor over de cachade 1:20 000-bladen kring Sveg.
if not a.utan_stort:
    yta = QgsGeometry.unaryUnion([f.geometry() for f in objekt(
        br, "\"skala\" = 20000 AND \"cachad\" = 1 AND \"blad\" LIKE 'J141-16E%'")])
    b = yta.boundingBox()
    r4 = processing.run("lmeko:fast_rutnat", {
        "UTBREDNING": f"{b.xMinimum()},{b.xMaximum()},{b.yMinimum()},{b.yMaximum()} [EPSG:3006]",
        "STORLEK": 1, "UTDATA": os.path.join(UT, "rutnat_1km.gpkg")})
    g4 = lager(r4["RUTNAT"], "rutnat_1km")
    g4.selectByIds([f.id() for f in g4.getFeatures() if yta.contains(f.geometry())])
    n = g4.selectedFeatureCount()
    m0, t0 = topp_minne_mb(), time.time()
    res = hamta("stort", g4, SKALA=2, VRT=False)
    okning = topp_minne_mb() - m0
    print(f"  {n} rutor, {time.time() - t0:.0f} s, toppminnet okade {okning:.0f} MB")
    u.krav(n > 100 and res["BRICKOR_SKRIVNA"] == n, f"stort uttag: alla {n} brickor skrivna")
    u.krav(okning < 300, f"stort uttag: minnet okade {okning:.0f} MB (< 300)")
    granska_brickor("stort", 1.0, 1000)


# 8. Brickor utan omradeslager.
class Aterkoppling(QgsProcessingFeedback):
    fel: list[str] = []

    def reportError(self, e, fatal=False):
        Aterkoppling.fel.append(e)


try:
    processing.run("lmeko:hamta_ekonomiska_kartan", {
        "UTBREDNING": DEL, "CRS": "EPSG:3006", "ARKIV": ARKIV, "BRICKOR": True,
        "UTMAPP": os.path.join(UT, "fel")}, feedback=Aterkoppling())
    u.krav(False, "brickor utan omradeslager vagras")
except Exception:  # noqa: BLE001
    u.krav(any("kräver ett områdeslager" in e for e in Aterkoppling.fel),
           "brickor utan omradeslager vagras med begripligt fel")

u.slut(app)

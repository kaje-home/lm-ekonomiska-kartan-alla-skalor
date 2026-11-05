"""Bladindelningen mot Lantmateriets egna index: Norrlands_Inland.shp
(1:20 000) och EkoRutor.shp (1:10 000).

    python-qgis-ltr.bat kontroll/prov_index.py [--plugin MAPP] [--arkiv MAPP]
                                               [--ut MAPP] [--lista-om]

Bara GDAL; QGIS behovs inte, men dess Python har GDAL. Indexen hamtas pa
nytt fran FTP:n till utmappen varje gang. Listningen tas ur arkivets cache
(ekonomiska_kartan/listning.json), eller listas om med --lista-om.

Var bladindelning ar aritmetisk och raknas ur namnen (blad.tolka_20k,
blad_alla.tolka_10k). Indexen ar facit.

Kraven, 1:20 000:
- indexet och listningen har samma kataloger, och alla gar att tolka
- de hela bladen ligger inom 1 m fran indexets polygon
- delbladen ar 80, och 1:20 000-delen (bladindex) tacker samma yta som
  indexets polygon
- ett blad utan ar i namnet saknar ar i indexet ocksa (som 0), och tvartom;
  ar som skiljer skrivs ut men ar inget fel
- Mullberget (J141-17F0-1e-f73): den vastra halften, ostra kanten mot
  1:10 000-omradet; Halvar-Jonsberg (J141-16E2-3g-h77): tre rutor

Kraven, 1:10 000:
- varje fil i listningen som gar att tolka har samma ruta som i EkoRutor
- de namn som inte gar att tolka ar de 16 kanda (CLAUDE.md, planerat till
  en senare 0.2.x); ett nytt eller forsvunnet sadant namn ar ett fel
- filerna i listningen men inte i EkoRutor ar bara den kanda
  133_10i8c53-1_0_b2.tif
"""
from __future__ import annotations

import os

from provmiljo import Utfall, argument, utmapp

p = argument(__doc__.splitlines()[0], "index")
p.add_argument("--lista-om", action="store_true", help="lista FTP:n pa nytt")
a = p.parse_args()
UT = utmapp(a.ut)

import sys  # noqa: E402

sys.path.insert(0, os.path.abspath(a.plugin))
from osgeo import gdal, ogr, osr  # noqa: E402

from lm_ekokarta import bladindex, listning  # noqa: E402
from lm_ekokarta.lm_ekokarta_karna import blad_alla  # noqa: E402
from lm_ekokarta.lm_ekokarta_karna.blad import ROT, tolka_20k  # noqa: E402
from lm_ekokarta.lm_ekokarta_karna.ftp import hamta_fil  # noqa: E402

gdal.UseExceptions()
ogr.UseExceptions()
u = Utfall()

OTOLKADE_10K = {
    # utan artal
    "133_7e4g_0_b2.tif", "133_11j1j_0_b2.tif", "133_11j3i_0_b2.tif", "133_11j3j_0_b2.tif",
    "133_11k0a_0_b2.tif", "133_11k1a_0_b2.tif", "133_11k1b_0_b2.tif", "133_14c5g_0_b2.tif",
    "133_14c5h_0_b2.tif", "133_19d3i_0_b2.tif", "133_19i5f_0_b2.tif", "133_26l0h_0_b2.tif",
    # sammanslagna blad
    "133_3c0a-b71_0_b2.tif", "133_3e1h-i2h-i73_0_b2.tif",
    # utan artal, i fel katalog (13g)
    "133_13h5f_0_b2.tif", "133_13h5g_0_b2.tif",
}
INTE_I_EKORUTOR = {"133_10i8c53-1_0_b2.tif"}

lis = listning.lista(os.path.join(a.arkiv, "ekonomiska_kartan", listning.CACHEFIL),
                     a.lista_om)
print(f"listningen: {lis.datum}")

# --- 1:20 000 ------------------------------------------------------------------
ix = bladindex.Index20k(bladindex.hamta(UT))
# Indexets filer och en oversikt (Översikt_A0.pdf) ligger bland
# bladkatalogerna; katalognamnen har ingen punkt.
k20 = {k for k in lis.kataloger_20k if "." not in k}
print(f"  filer bland 1:20 000-katalogerna: {sorted(set(lis.kataloger_20k) - k20)}")
u.krav(set(ix.blad) == k20 and len(k20) > 1000,
       f"1:20 000: samma {len(k20)} kataloger i indexet och listningen "
       f"(bara i indexet {sorted(set(ix.blad) - k20)[:3]}, bara i listningen "
       f"{sorted(k20 - set(ix.blad))[:3]})")
otolkade_20k = []
for k in k20:
    try:
        tolka_20k(k)
    except ValueError:
        otolkade_20k.append(k)
u.krav(not otolkade_20k, f"1:20 000: alla kataloger tolkas ({otolkade_20k[:3]})")

# Indexets polygoner, i RT 90, en gang till: Index20k sparar bara rutorna.
rt90 = osr.SpatialReference()
rt90.ImportFromEPSG(3021)
rt90.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
with gdal.config_options({"SHAPE_ENCODING": "CP1252"}):
    ds = ogr.Open(bladindex.sokvag(UT))
    lag = ds.GetLayer()
    src = lag.GetSpatialRef()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, rt90)
    poly = {}
    for f in lag:
        g = f.GetGeometryRef().Clone()
        g.Transform(ct)
        poly[f.GetField("Bladnummer")] = (g, f.GetField(3))
    ds = None

hel_fel, del_fel, ar_fel, delblad = [], [], [], []
for k, (g, ar) in poly.items():
    try:
        b = tolka_20k(k)
    except ValueError:
        continue
    if (ar or None) != b.ar:
        ar_fel.append((k, b.ar, ar))
    if ix.ar_delblad(b):
        delblad.append(k)
        egen = ogr.CreateGeometryFromWkt(ix.yta_wkt(b))
        skillnad = g.SymDifference(egen).GetArea()
        if skillnad > 0.001 * egen.GetArea():
            del_fel.append((k, round(skillnad)))
    else:
        e = g.GetEnvelope()                 # minx, maxx, miny, maxy
        avv = max(abs(e[0] - b.minx), abs(e[1] - b.minx - 10000),
                  abs(e[2] - b.maxy + 10000), abs(e[3] - b.maxy))
        if avv > 1.0:
            hel_fel.append((k, round(avv, 1)))
u.krav(not hel_fel, f"1:20 000: de {len(poly) - len(delblad)} hela bladen inom 1 m fran "
                    f"indexet ({hel_fel[:3] or 'inga avvikelser'})")
u.krav(len(delblad) == 80 and not del_fel,
       f"1:20 000: {len(delblad)} delblad, 1:20 000-delen lika med indexets polygon "
       f"({del_fel[:3] or 'inga avvikelser'})")
# Aret i katalognamnet ar den skannade utgavans; indexets ar skiljer for
# nagra blad och ar bara upplysning. Utan ar ska vara utan ar i bada.
print(f"  ar som skiljer mellan namnet och indexet: {len(ar_fel)} "
      + ", ".join(f"{k} {a1}/{a2}" for k, a1, a2 in sorted(ar_fel)))
u.krav(not [q for q in ar_fel if q[1] is None or q[2] in (None, 0)],
       "1:20 000: blad utan ar saknar ar bade i namnet och i indexet")
mull = tolka_20k("J141-17F0-1e-f73")
halv = tolka_20k("J141-16E2-3g-h77")
u.krav(ix.bladnamn(mull.katalog) == "Mullberget" and ix.gransidor(mull) == ("o",)
       and sorted(ix.celler(mull)) == [(mull.minx, mull.maxy - 5000), (mull.minx, mull.maxy)],
       f"1:20 000: Mullberget, vastra halften, ostra kanten mot 1:10 000 "
       f"({ix.gransidor(mull)})")
u.krav(ix.bladnamn(halv.katalog) == "Halvar-Jonsberg" and len(ix.celler(halv)) == 3
       and ix.gransidor(halv) == (),
       f"1:20 000: Halvar-Jonsberg, tre rutor ({len(ix.celler(halv))})")

# --- 1:10 000 ------------------------------------------------------------------
EKORUTOR = os.path.join(UT, "EkoRutor")
for e in ("shp", "shx", "dbf", "prj"):
    hamta_fil(f"{ROT}/Bladindelningskartor/Shape/EkoRutor.{e}", f"{EKORUTOR}.{e}")
ds = ogr.Open(EKORUTOR + ".shp")
lag = ds.GetLayer()
src = lag.GetSpatialRef()
src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = None if src.IsSame(rt90) else osr.CoordinateTransformation(src, rt90)
eko = {}
for f in lag:
    g = f.GetGeometryRef().Clone()
    if ct:
        g.Transform(ct)
    eko[f.GetField("fileName")] = g.GetEnvelope()
ds = None
filer = {n for v in lis.filer_10k.values() for n in v}
print(f"EkoRutor: {len(eko)} filer; listningen: {len(filer)}")
u.krav(filer - set(eko) == INTE_I_EKORUTOR,
       f"1:10 000: i listningen men inte i EkoRutor bara den kanda "
       f"({sorted(filer - set(eko))[:5]})")
print(f"  i EkoRutor men inte i listningen: {len(set(eko) - filer)} "
      f"{sorted(set(eko) - filer)[:5]}")
otolkade, avv = set(), []
for n in filer & set(eko):
    try:
        b = blad_alla.tolka_10k(n)
    except ValueError:
        otolkade.add(n)
        continue
    e = eko[n]
    if max(abs(e[0] - b.minx), abs(e[1] - b.maxx), abs(e[2] - b.miny), abs(e[3] - b.maxy)) > 1:
        avv.append(n)
u.krav(not avv, f"1:10 000: {len(filer & set(eko)) - len(otolkade)} tolkade filer, samma ruta "
                f"som i EkoRutor ({avv[:3] or 'inga avvikelser'})")
u.krav(otolkade == OTOLKADE_10K,
       f"1:10 000: de otolkade namnen ar de 16 kanda (nya {sorted(otolkade - OTOLKADE_10K)[:3]}, "
       f"borta {sorted(OTOLKADE_10K - otolkade)[:3]})")


class _App:
    def exitQgis(self):
        pass


u.slut(_App())

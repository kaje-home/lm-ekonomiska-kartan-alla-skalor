"""
Georeferering av ekonomiska kartan 1:20 000 (Norrlands inland) mot kartans eget
tryckta kilometerrutnät.

Inbyggd 2026-09-27 ur en prototyp som var provkörd på två grannblad
(J141-17C6-7g-h76 och J141-17C6-7i-j76, båda 1976). Anropas från
hamta_ekokarta. Kravspecen står i lm-faltunderlag-kravspec.md, avsnittet om
ekonomiska kartan 1:20 000.

Varför det behövs
-----------------
1:10 000-bladen levereras med världsfil och .TAB och är beskurna till kartytan.
1:20 000-bladen är en enda TIFF utan georeferens: en rå skanning av hela det
tryckta bladet, med marginal och teckenförklaring, olika beskuren och olika
vriden från blad till blad. Kartytan (10 x 10 km, 2 m/pixel vid 254 dpi) ligger
någonstans inne i bilden och var den börjar står ingenstans.

Vad bladen har lärt oss
-----------------------
* Rutnätet är tryckt som tunna mörkröda heldragna linjer -- i samma färg och
  tjocklek som höjdkurvorna. I fjällterräng dränks det av kurvorna om man
  letar efter "mörkt". Det som skiljer rutnätet från kurvorna är att det är
  helt rakt.
* En fast gråskaletröskel fungerade på det ena bladet och inte alls på det
  andra. Därför mäts i stället hur mycket mörkare en pixel är än sin närmaste
  omgivning, i grönkanalen (röd linje på grön fotokarta syns bäst där).
* Skanningarna är vridna olika mycket: 0,09 grader på det ena bladet, 0,75 på
  det andra. En linje en pixel bred som lutar så vandrar 65 pixlar över bladet.
  Linjerna måste därför sökas längs sin egen lutning, inte längs pixelraderna.
* Papperet har krympt ungefär en halv procent: 497 px per km i stället för 500.

Metod
-----
1. Linjekontrast: hur mycket mörkare än omgivningen varje pixel är, separat
   för lodräta och vågräta linjer.
2. Kamfilter med lutning: pröva lutningar upp till ~1 grad och, för varje
   lutning, den period och förskjutning där nio inre linjer med jämnt avstånd
   ger starkast signal.
3. Varje inre rutnätslinje mäts för sig i band längs linjen och anpassas robust
   till en rät linje. Band där en väg, kurva eller text lurat mätningen kastas.
4. Korsningarna blir passpunkter; koordinaterna ges av bladets hörn (ur
   bladnamnet) plus hela kilometer.
5. Spärrar avgör om resultatet duger. Duger det skrivs en GeoTIFF i RT 90 som
   täcker exakt bladets 10 x 10 km -- marginalen försvinner i samma steg.

Kors-bladen (tillagt 2026-09-27)
--------------------------------
På de flesta blad är rutnätet inte tryckt som linjer, bara som korta streck i
marginalen vid varje kilometer och ibland ett kors mitt på bladet (7 av 11
provade blad). Där finns inget rutnät att kamma. I stället används:

* Kartytans kant: grönt tryck mot vitt papper. Kanten ligger någon pixel
  utanför bladgränsen; hur mycket (beta) skattas ur bladet självt.
* Kilometerstrecken i marginalen, 9 per kant. Ett streck på norrkanten säger
  bara E = hel km, inte N -- varje streck ger ett villkor, inte en passpunkt.
* Mittkorset, när det finns.

Allt anpassas i ett svep: bild -> RT 90 som polynom av grad 2 plus beta,
viktad minsta kvadrat med rensning per slag av observation. Prövad mot
rutnätsmetoden på sex linjeblad: 95 % under 3,1-4,1 m (ett sjörikt blad
6,8 m). Lämna-en-utanför underskattar där felet med omkring 2 m.

Endast numpy och GDAL, som finns i QGIS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()

# Hojs nar metoden andras sa att andra utfall ar mojliga. Cachen i arkivet
# (hamta_ekokarta) provar da om bladen.
METOD_VERSION = "2026-09-27 kant 6 m"

CRS_EPSG = 3021            # RT 90 2,5 gon V, samma som 1:10 000-serien
BLAD_M = 10000.0           # bladet är 10 x 10 km
KM = 1000.0
PIXEL_M = 2.0              # 254 dpi i 1:20 000 -> 2 m per pixel
LINJER = 11                # rutnätslinjer per led, kanterna inräknade

# --- Spärrar och parametrar. Ändras de ska det stå varför i kravspecen. -----
KONTRAST_FONSTER = 9       # px; omgivningen en pixel jämförs med
KONTRAST_SKALA = 30.0      # gråvärdesskillnad som räknas som full linje
PERIOD_MIN, PERIOD_MAX = 485.0, 505.0   # px per km; nominellt 500
LUTNING_MAX = 0.02         # ~1,1 grad; skanningarna har visat upp till 0,75
LUTNING_STEG = 81
PERIOD_SKILLNAD_MAX = 3.0  # krympningen ska vara ungefär lika i båda led
VRIDNING_SKILLNAD_MAX = 0.003   # lodräta och vågräta linjer ska vridas lika
KONTRAST_MIN = 2.5         # rutnätets signal mot profilens median
MIN_LINJER = 6             # inre linjer som måste gå att mäta, per led
MIN_BAND = 6               # mätband per linje efter rensning
MIN_PASSPUNKTER = 36
LOO_P95_MAX_M = 4.0        # två pixlar

# --- Kantmetoden (kors-bladen) ---------------------------------------------
PAPPER_MIN = 205           # min(R,G,B) över detta är vitt papper
KANT_LOPP = 40             # px i följd som inte är papper: kartytan börjar
KANT_TRIM = 150            # px närmast hörnen används inte (hörnmärkena)
KANT_STEG = 250            # px mellan kantpunkterna i anpassningen
KANT_VIKT = 0.2            # en kantpunkts vikt mot ett strecks
MARGINAL_MIN = 10          # px papper runt kartytan; mindre = beskuren skanning
STRECK_SOK = 20            # px åt vardera hållet kring väntat streck
STRECK_REMSA = (2, 9)      # px utanför kanten där strecket mäts
STRECK_KONTRAST_MIN = 60   # så mycket mörkare än remsans median
STRECK_BREDD_MAX = 5.0     # px vid halva höjden; bredare är text
MIN_STRECK = 24            # av 36 möjliga
MIN_STRECK_PER_KANT = 4
BETA_MAX_M = 12.0          # kanten mer än 6 px från bladgränsen: något annat fel
KANT_LOO_P95_MAX_M = 6.0   # beslut 2026-09-27; verkligt fel ~2 m mer, se kravspecen
KORS_ARM = (12, 30)        # px från mitten; korset är ett X med tom mitt
KORS_MIN = 0.5             # armarnas svagaste kontrast; skogstextur ger 0,2-0,4


@dataclass
class Resultat:
    ok: bool
    orsak: str = ""
    period_px: tuple[float, float] | None = None
    vridning_grader: float | None = None
    passpunkter: np.ndarray | None = None      # rader: kolumn, rad, E, N
    rms_affin_m: float | None = None
    rms_grad2_m: float | None = None
    loo_medel_m: float | None = None
    loo_p95_m: float | None = None
    utfil: str | None = None
    metod: str = "rutnät"          # eller "kant" för kors-bladen
    streck: int = 0                # kantmetoden: använda kilometerstreck
    kors: bool = False             # kantmetoden: mittkorset hittat


# ---------------------------------------------------------------------------
def _medel_langs(a: np.ndarray, w: int, axel: int) -> np.ndarray:
    """Glidande medelvärde över w pixlar längs en axel (bara numpy)."""
    pad = [(0, 0), (w // 2 + 1, w // 2)] if axel == 1 else [(w // 2 + 1, w // 2), (0, 0)]
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axel, dtype=np.float64)
    d = (c[:, w:] - c[:, :-w]) if axel == 1 else (c[w:, :] - c[:-w, :])
    return (d / w).astype(np.float32)


def _linjekontrast(tif: str) -> tuple[np.ndarray, np.ndarray]:
    """Kontrast för lodräta respektive vågräta linjer, 0..1.

    Grönkanalen: rutnätet är rött på en grön fotokarta. Saknas färg används
    det enda bandet.
    """
    ds = gdal.Open(tif)
    b = 2 if ds.RasterCount >= 3 else 1
    sig = -ds.GetRasterBand(b).ReadAsArray().astype(np.float32)
    ds = None
    lod = np.clip((sig - _medel_langs(sig, KONTRAST_FONSTER, 1)) / KONTRAST_SKALA, 0, 1)
    vag = np.clip((sig - _medel_langs(sig, KONTRAST_FONSTER, 0)) / KONTRAST_SKALA, 0, 1)
    return lod, vag


def _kam(profil: np.ndarray, delvis: bool = False) -> tuple[float, float, float]:
    """Bästa (signal, period, förskjutning) för de nio inre linjerna.

    Kanterna räknas inte: de är ofta inte tryckta som linjer, kartinnehållet
    tar bara slut där.

    Normalt måste hela rutnätet, kanterna inräknade, rymmas i bilden. Med
    delvis räcker de inre linjerna -- så att ett beskuret blad fångas av
    hörnspärren med rätt orsak, i stället för att se ut som ett blad utan
    rutnät.
    """
    L = len(profil)
    bast = (-1.0, 0.0, 0.0)
    k = np.arange(1, LINJER - 1)
    for per in np.arange(PERIOD_MIN, PERIOD_MAX + 0.01, 0.25):
        minoff = -int(per) + 1 if delvis else 0
        maxoff = int(L - (LINJER - (2 if delvis else 1)) * per) - 1
        if maxoff <= minoff:
            continue
        off = np.arange(minoff, maxoff)
        pos = np.rint(off[:, None] + k[None, :] * per).astype(int)
        s = profil[pos].mean(axis=1)
        i = int(s.argmax())
        if s[i] > bast[0]:
            bast = (float(s[i]), float(per), float(off[i]))
    return bast


def _kam_med_lutning(c: np.ndarray, remsa: int = 100,
                     delvis: bool = False) -> tuple[float, float, float, float]:
    """Sök lutning, period och förskjutning för linjer som löper längs axel 0.

    Returnerar (kontrast, lutning, period, förskjutning), där linje k ligger på
    x = förskjutning + k*period + lutning*(y - H/2).
    """
    H, _ = c.shape
    ys = list(range(300, H - 300 - remsa, remsa))
    P = np.stack([c[y:y + remsa].mean(axis=0) for y in ys])
    yc = np.array(ys) + remsa / 2 - H / 2
    bast = (-1.0, 0.0, 0.0, 0.0)
    for t in np.linspace(-LUTNING_MAX, LUTNING_MAX, LUTNING_STEG):
        sh = np.rint(yc * t).astype(int)
        prof = np.mean([np.roll(P[i], -sh[i]) for i in range(len(ys))], axis=0)
        s, per, off = _kam(prof, delvis)
        kontrast = s / max(float(np.median(prof)), 1e-6)
        if kontrast > bast[0]:
            bast = (kontrast, float(t), per, off)
    return bast


def _linjer(c: np.ndarray, off: float, per: float, t: float) -> dict:
    """Mät varje inre linje (längs axel 0) i band och anpassa robust: x = a + b*y."""
    H, W = c.shape
    ut = {}
    for k in range(1, LINJER - 1):
        pts = []
        for b0 in range(150, H - 150, 150):
            yc = b0 + 75
            forv = off + k * per + t * (yc - H / 2)
            lo, hi = max(int(forv) - 18, 0), min(int(forv) + 19, W)
            if hi - lo < 10:
                continue
            prof = c[b0:b0 + 150, lo:hi].mean(axis=0)
            prof = np.clip(prof - np.median(prof), 0, None)
            if prof.max() < 0.3:
                continue
            i = int(prof.argmax())
            a_, b_ = max(i - 2, 0), min(i + 3, len(prof))
            w = prof[a_:b_]
            pts.append((yc, (np.arange(a_, b_) * w).sum() / w.sum() + lo))
        if len(pts) < MIN_BAND:
            continue
        y, x = np.array(pts, dtype=float).T
        keep = np.ones(len(y), bool)
        for _ in range(4):
            a, b = np.polyfit(y[keep], x[keep], 1)[::-1]
            res = np.abs(x - (a + b * y))
            keep = res < max(1.0, 3 * np.median(res[keep]))
        if keep.sum() >= MIN_BAND:
            ut[k] = (float(a), float(b))
    return ut


def _design(x: np.ndarray, y: np.ndarray, grad: int) -> np.ndarray:
    x, y = x / 1000.0, y / 1000.0
    cols = [np.ones_like(x), x, y]
    if grad == 2:
        cols += [x * x, x * y, y * y]
    return np.stack(cols, 1)


def _fel(g: np.ndarray, grad: int) -> np.ndarray:
    A = _design(g[:, 0], g[:, 1], grad)
    r = []
    for tgt in (g[:, 2], g[:, 3]):
        c, *_ = np.linalg.lstsq(A, tgt, rcond=None)
        r.append(tgt - A @ c)
    return np.hypot(*r)


def _loo(g: np.ndarray, grad: int = 2) -> np.ndarray:
    """Lämna en utanför: hur långt hamnar varje passpunkt när den inte får vara med?"""
    A = _design(g[:, 0], g[:, 1], grad)
    ut = []
    for i in range(len(g)):
        m = np.arange(len(g)) != i
        e = []
        for tgt in (g[:, 2], g[:, 3]):
            c, *_ = np.linalg.lstsq(A[m], tgt[m], rcond=None)
            e.append(tgt[i] - A[i] @ c)
        ut.append(np.hypot(*e))
    return np.array(ut)


def _horn_inne_i_bilden(g: np.ndarray, minx: float, maxy: float, W: int, H: int) -> bool:
    """Extrapolera bladets hörn till bildkoordinater och kontrollera att de ryms."""
    A = _design(g[:, 2] - minx, maxy - g[:, 3], 1)
    cx, *_ = np.linalg.lstsq(A, g[:, 0], rcond=None)
    cy, *_ = np.linalg.lstsq(A, g[:, 1], rcond=None)
    horn = np.array([[0, 0], [BLAD_M, 0], [0, BLAD_M], [BLAD_M, BLAD_M]])
    Ah = _design(horn[:, 0], horn[:, 1], 1)
    px, py = Ah @ cx, Ah @ cy
    return bool((px >= 0).all() and (px < W).all() and (py >= 0).all() and (py < H).all())


# ---------------------------------------------------------------------------
def georeferera_20k(tif: str, minx: float, maxy: float, utfil: str) -> Resultat:
    """Georeferera ett 1:20 000-blad och skriv en GeoTIFF i RT 90 över bladytan.

    minx, maxy: bladets västra och övre kant i RT 90, ur bladnamnet
    (ekokarta.tolka_20k). utfil skrivs bara om alla spärrar klaras.
    """
    lod, vag = _linjekontrast(tif)
    H, W = lod.shape

    kv, tv, perx, offx = _kam_med_lutning(lod)      # lodräta: x = f(y)
    kh, th, pery, offy = _kam_med_lutning(vag.T)    # vågräta: y = f(x)
    # Inget rutnät med kanterna i bilden: sok om med bara de inre linjerna.
    # Ett blad som klarar forsta sokningen paverkas inte. Ett beskuret blad
    # hittas nu och stoppas av hornspärren -- med ratt orsak.
    if kv < KONTRAST_MIN:
        kv, tv, perx, offx = _kam_med_lutning(lod, delvis=True)
    if kh < KONTRAST_MIN:
        kh, th, pery, offy = _kam_med_lutning(vag.T, delvis=True)
    res = Resultat(ok=False, period_px=(perx, pery),
                   vridning_grader=float(np.degrees(np.arctan((tv - th) / 2))))

    if min(kv, kh) < KONTRAST_MIN:
        # Pa de flesta blad ar rutnatet bara tryckt som streck i marginalen
        # (7 av 11 provade, 2026-09-27). Da provas kantmetoden; orsaken fran
        # rutnatet foljer med om aven den vagrar.
        lod = vag = None
        return _georeferera_kant(
            tif, minx, maxy, utfil,
            f"inget heldraget kilometerrutnät (kontrast {kv:.1f}/{kh:.1f}, "
            f"gräns {KONTRAST_MIN})")
    if not (PERIOD_MIN < perx < PERIOD_MAX and PERIOD_MIN < pery < PERIOD_MAX):
        res.orsak = f"rutnätets period {perx:.1f}/{pery:.1f} px stämmer inte med 1:20 000"
        return res
    if abs(perx - pery) > PERIOD_SKILLNAD_MAX:
        res.orsak = f"olika period i de två leden ({perx:.1f} mot {pery:.1f} px)"
        return res
    # En vridning av bladet ger lika stor lutning åt motsatt håll i de två leden.
    if abs(tv + th) > VRIDNING_SKILLNAD_MAX:
        res.orsak = "lodräta och vågräta linjer är inte vridna lika -- skevt rutnät"
        return res

    V = _linjer(lod, offx, perx, tv)          # x = a + b*y
    Hz = _linjer(vag.T, offy, pery, th)       # y = a + b*x
    if len(V) < MIN_LINJER or len(Hz) < MIN_LINJER:
        res.orsak = f"för få mätbara rutnätslinjer ({len(V)} lodräta, {len(Hz)} vågräta)"
        return res

    g = []
    for kx, (a1, b1) in V.items():
        for ky, (a2, b2) in Hz.items():
            x = (a1 + b1 * a2) / (1 - b1 * b2)
            y = a2 + b2 * x
            g.append((x, y, minx + kx * KM, maxy - ky * KM))
    g = np.array(g)
    res.passpunkter = g
    if len(g) < MIN_PASSPUNKTER:
        res.orsak = f"för få passpunkter ({len(g)})"
        return res

    fa, f2, loo = _fel(g, 1), _fel(g, 2), _loo(g, 2)
    res.rms_affin_m = float(np.sqrt((fa ** 2).mean()))
    res.rms_grad2_m = float(np.sqrt((f2 ** 2).mean()))
    res.loo_medel_m = float(loo.mean())
    res.loo_p95_m = float(np.percentile(loo, 95))
    if res.loo_p95_m > LOO_P95_MAX_M:
        res.orsak = f"lägesfelet för stort ({res.loo_p95_m:.1f} m, gräns {LOO_P95_MAX_M:.0f} m)"
        return res
    if not _horn_inne_i_bilden(g, minx, maxy, W, H):
        res.orsak = "bladets hörn hamnar utanför skanningen -- bladet är beskuret"
        return res

    _skriv(tif, g, minx, maxy, utfil)
    res.ok = True
    res.utfil = utfil
    return res


def _skriv(tif: str, g: np.ndarray, minx: float, maxy: float, utfil: str) -> None:
    """GeoTIFF i RT 90 över exakt bladytan, ur passpunkter (kolumn, rad, E, N)."""
    # Passpunkter i GDAL:s konvention: pixelhörn, så centrum = index + 0,5.
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(CRS_EPSG)
    gcps = [gdal.GCP(E, N, 0.0, x + 0.5, y + 0.5) for x, y, E, N in g]
    vrt = gdal.Translate("", tif, format="VRT", GCPs=gcps, outputSRS=srs.ExportToWkt())
    os.makedirs(os.path.dirname(os.path.abspath(utfil)), exist_ok=True)
    gdal.Warp(utfil, vrt, dstSRS=f"EPSG:{CRS_EPSG}", polynomialOrder=2,
              outputBounds=(minx, maxy - BLAD_M, minx + BLAD_M, maxy),
              xRes=PIXEL_M, yRes=PIXEL_M, resampleAlg="bilinear",
              creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=2"])
    vrt = None


# --- Kantmetoden (kors-bladen) -----------------------------------------------
def _samp(c: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinjär sampling i c vid (x, y)."""
    H, W = c.shape
    x = np.clip(x, 0, W - 1.001)
    y = np.clip(y, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (c[y0, x0] * (1 - fx) * (1 - fy) + c[y0, x0 + 1] * fx * (1 - fy)
            + c[y0 + 1, x0] * (1 - fx) * fy + c[y0 + 1, x0 + 1] * fx * fy)


def _kant(mn: np.ndarray, fran_start: bool) -> np.ndarray:
    """Per rad (var 5:e): kolumnen där kartytan börjar, med delpixel.

    Kartytan börjar där KANT_LOPP pixlar i följd inte är vitt papper; läget
    är där min(R,G,B) passerar PAPPER_MIN. NaN där ingen kant hittas.
    """
    H, W = mn.shape
    ut = np.full(H, np.nan)
    for y in range(0, H, 5):
        rad = mn[y] if fran_start else mn[y, ::-1]
        c = np.convolve((rad <= PAPPER_MIN).astype(np.int32),
                        np.ones(KANT_LOPP, np.int32), "valid")
        i = int(np.argmax(c >= KANT_LOPP))
        if c[i] < KANT_LOPP:
            continue
        pos = float(i)
        if i > 0 and rad[i - 1] > PAPPER_MIN:
            pos = i - 1 + (rad[i - 1] - PAPPER_MIN) / max(float(rad[i - 1] - rad[i]), 1e-6)
        ut[y] = pos if fran_start else W - 1 - pos
    return ut


def _rak(t: np.ndarray, q: np.ndarray) -> tuple[float, float]:
    """Robust rät linje q = a + b*t genom kantmätningarna (NaN hoppas över)."""
    m = ~np.isnan(q)
    m[:KANT_TRIM] = False
    m[len(q) - KANT_TRIM:] = False
    t, q = t[m], q[m]
    keep = np.ones(len(t), bool)
    for _ in range(5):
        a, b = np.polyfit(t[keep], q[keep], 1)[::-1]
        r = np.abs(q - (a + b * t))
        keep = r < max(1.5, 3 * np.median(r[keep]))
    return float(a), float(b)


def _skarning(L1, L2) -> np.ndarray:
    """Skärning mellan x = a1 + b1*y och y = a2 + b2*x."""
    (a1, b1), (a2, b2) = L1, L2
    x = (a1 + b1 * a2) / (1 - b1 * b2)
    return np.array([x, a2 + b2 * x])


def _streck(g, L, p0, p1, utat: int, langs_x: bool) -> dict:
    """Kilometerstrecken längs en kant: {km: (x, y)}.

    L är kantlinjen (y = f(x) om langs_x, annars x = f(y)); p0, p1 kantens
    hörn; utat +1/-1 bort från kartytan. Strecket söks nära sitt väntade läge
    som det mörkaste smala stället i en remsa strax utanför kanten.
    """
    ut = {}
    for i in range(1, 10):
        e = p0 + i / 10 * (p1 - p0)
        t0 = e[0] if langs_x else e[1]
        ts = np.arange(t0 - STRECK_SOK, t0 + STRECK_SOK + 0.01, 0.5)
        tv = L[0] + L[1] * ts
        rem = [(_samp(g, ts, tv + utat * d) if langs_x else _samp(g, tv + utat * d, ts))
               for d in range(*STRECK_REMSA)]
        prof = 255.0 - np.min(rem, axis=0)
        bas = float(np.median(prof))
        k = int(np.argmax(prof))
        if prof[k] - bas < STRECK_KONTRAST_MIN:
            continue
        halv = bas + (prof[k] - bas) / 2
        lo = hi = k
        while lo > 0 and prof[lo - 1] > halv:
            lo -= 1
        while hi < len(prof) - 1 and prof[hi + 1] > halv:
            hi += 1
        if (hi - lo) * 0.5 > STRECK_BREDD_MAX:
            continue
        w = prof[lo:hi + 1] - halv
        t = float((ts[lo:hi + 1] * w).sum() / w.sum()) if w.sum() > 0 else float(ts[k])
        q = L[0] + L[1] * t
        ut[i] = (t, q) if langs_x else (q, t)
    return ut


def _mittkors(g: np.ndarray, px: float, py: float) -> tuple[float, float] | None:
    """Korset mitt på bladet: ett X med tom mitt. None om det inte syns.

    Ett kors räknas bara om alla fyra armarna syns -- en väg eller kurva ger
    högst två. Läget blir skärningen mellan de två diagonalerna, var och en
    mätt som en rät linje.
    """
    r = KORS_ARM[1] + 50
    x0, y0 = int(px) - r, int(py) - r
    if x0 < 0 or y0 < 0 or x0 + 2 * r >= g.shape[1] or y0 + 2 * r >= g.shape[0]:
        return None
    s = -g[y0:y0 + 2 * r, x0:x0 + 2 * r].astype(np.float32)
    m = _medel_langs(_medel_langs(s, KONTRAST_FONSTER, 1), KONTRAST_FONSTER, 0)
    c = np.clip((s - m) / KONTRAST_SKALA, 0, 1)
    diag = [np.array([1, 1]) / np.sqrt(2), np.array([1, -1]) / np.sqrt(2)]
    t = np.arange(KORS_ARM[0], KORS_ARM[1] + 1, dtype=float)
    X, Y = np.meshgrid(np.arange(r - 40, r + 41, dtype=float), np.arange(r - 40, r + 41, dtype=float))
    armar = [_samp(c, X[..., None] + sg * t * d[0], Y[..., None] + sg * t * d[1]).mean(-1)
             for d in diag for sg in (1, -1)]
    mn = np.min(armar, axis=0)
    k = np.unravel_index(int(np.argmax(mn)), mn.shape)
    if mn[k] < KORS_MIN:
        return None
    cx, cy = X[k], Y[k]
    linjer = []
    for d in diag:
        n = np.array([-d[1], d[0]])
        pts = []
        for tt in list(range(-KORS_ARM[1], -KORS_ARM[0] + 1)) + list(range(KORS_ARM[0], KORS_ARM[1] + 1)):
            sv = np.arange(-4, 4.01, 0.5)
            p = _samp(c, cx + tt * d[0] + sv * n[0], cy + tt * d[1] + sv * n[1])
            w = np.clip(p - np.median(p), 0, None)
            if w.sum() >= 0.05:
                pts.append((tt, (sv * w).sum() / w.sum()))
        if len(pts) < 16:
            return None
        tt, sv = np.array(pts).T
        a, b = np.polyfit(tt, sv, 1)[::-1]
        linjer.append((np.array([cx, cy]) + a * n, d + b * n))
    (p1, r1), (p2, r2) = linjer
    t1 = np.linalg.solve(np.column_stack([r1, -r2]), p2 - p1)[0]
    q = p1 + t1 * r1
    if np.hypot(q[0] - cx, q[1] - cy) > 3:
        return None
    return float(q[0] + x0), float(q[1] + y0)


def _rader(x, y) -> np.ndarray:
    x, y = np.asarray(x, float) / 1000.0, np.asarray(y, float) / 1000.0
    return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], -1)


def _kant_losning(obs: list, aktiv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Viktad MK för 6+6 koefficienter (bild -> E, N) och beta. Restfel i meter."""
    X = np.zeros((len(obs), 13))
    y = np.zeros(len(obs))
    w = np.zeros(len(obs))
    for k, (px, py, vad, mal, bk, vikt, _) in enumerate(obs):
        j = 0 if vad == "E" else 6
        X[k, j:j + 6] = _rader(px, py)
        X[k, 12] = -bk
        y[k] = mal
        w[k] = vikt if aktiv[k] else 0.0
    sw = np.sqrt(w)
    c = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
    return c, X @ c - y


def _georeferera_kant(tif: str, minx: float, maxy: float, utfil: str,
                      orsak_rutnat: str) -> Resultat:
    """Kors-bladen: kartytans kant, kilometerstrecken och mittkorset.

    Varje observation säger bara det den vet: ett streck på norr- eller
    södra kanten ger E = hel km, ett på västra eller östra N = hel km; en
    kantpunkt ligger på bladgränsen plus beta; korset ger båda. Se modulens
    docstring och kravspecen.
    """
    res = Resultat(ok=False, metod="kant")

    def vagra(varfor: str) -> Resultat:
        res.orsak = f"{orsak_rutnat}, och kantmetoden: {varfor}"
        return res

    ds = gdal.Open(tif)
    a = ds.ReadAsArray()
    ds = None
    if a.ndim != 3:
        return vagra("skanningen är inte i färg")
    mn = a.min(axis=0)
    g = a[1].astype(np.float32)
    a = None
    H, W = mn.shape
    ys, xs = np.arange(H, dtype=float), np.arange(W, dtype=float)
    ra = {"v": _kant(mn, True), "o": _kant(mn, False),
          "n": _kant(mn.T, True), "s": _kant(mn.T, False)}
    mn = None
    if min(np.isfinite(r[::5]).mean() for r in ra.values()) < 0.5:
        return vagra("ingen kartyta med kant mot vitt papper")
    v, o = _rak(ys, ra["v"]), _rak(ys, ra["o"])
    n, s = _rak(xs, ra["n"]), _rak(xs, ra["s"])
    NV, NO, SV, SO = _skarning(v, n), _skarning(o, n), _skarning(v, s), _skarning(o, s)
    horn = np.array([NV, NO, SV, SO])
    if (horn.min(axis=0) < MARGINAL_MIN).any() or horn[:, 0].max() > W - 1 - MARGINAL_MIN \
            or horn[:, 1].max() > H - 1 - MARGINAL_MIN:
        return vagra("ingen pappersmarginal runt kartytan -- skanningen är beskuren "
                     "och bladgränsen går inte att se")

    B = BLAD_M
    obs = []          # (x, y, 'E'/'N', mål, betakoefficient, vikt, slag)
    per_kant = {}
    for namn, L, p0, p1, utat, lx in (("n", n, NV, NO, -1, True), ("s", s, SV, SO, +1, True),
                                      ("v", v, NV, SV, -1, False), ("o", o, NO, SO, +1, False)):
        st = _streck(g, L, p0, p1, utat, lx)
        per_kant[namn] = st
        for i, (x, y) in st.items():
            if lx:
                obs.append((x, y, "E", minx + i * KM, 0.0, 1.0, "streck"))
            else:
                obs.append((x, y, "N", maxy - i * KM, 0.0, 1.0, "streck"))
    for namn, lx, vad, mal, bk in (("n", True, "N", maxy, 1.0), ("s", True, "N", maxy - B, -1.0),
                                   ("v", False, "E", minx, -1.0), ("o", False, "E", minx + B, 1.0)):
        r = ra[namn]
        for t in range(KANT_TRIM, len(r) - KANT_TRIM, KANT_STEG):
            q = r[max(t - 20, 0):t + 21]
            if np.isfinite(q).sum() < 4:
                continue
            q = float(np.nanmedian(q))
            obs.append(((t, q) if lx else (q, t)) + (vad, mal, bk, KANT_VIKT, "kant"))
    mitt = (NV + NO + SV + SO) / 4
    kors = _mittkors(g, mitt[0], mitt[1])
    g = None
    if kors is not None:
        obs.append((kors[0], kors[1], "E", minx + B / 2, 0.0, 1.0, "kors"))
        obs.append((kors[0], kors[1], "N", maxy - B / 2, 0.0, 1.0, "kors"))

    # Robust: rensa per slag, sa att de manga kantpunkterna inte bestammer
    # vad som ar ett avvikande streck.
    slag = np.array([o_[6] for o_ in obs])
    aktiv = np.ones(len(obs), bool)
    for _ in range(8):
        c, fel = _kant_losning(obs, aktiv)
        ny = aktiv.copy()
        for sl in ("streck", "kant", "kors"):
            m = slag == sl
            if (m & aktiv).any():
                ny[m] = np.abs(fel[m]) < max(3.0, 4 * np.median(np.abs(fel[m & aktiv])))
        if (ny == aktiv).all():
            break
        aktiv = ny
    c, fel = _kant_losning(obs, aktiv)
    res.streck = int(((slag == "streck") & aktiv).sum())
    res.kors = bool(((slag == "kors") & aktiv).any())
    beta = float(c[12])

    # Period och vridning ur modellens lutning mitt pa bladet.
    rc = _rader(mitt[0], mitt[1])
    rx, ry = _rader(mitt[0] + 1, mitt[1]), _rader(mitt[0], mitt[1] + 1)
    dEx, dNx = (rx - rc) @ c[0:6], (rx - rc) @ c[6:12]
    dEy, dNy = (ry - rc) @ c[0:6], (ry - rc) @ c[6:12]
    perx, pery = KM / np.hypot(dEx, dNx), KM / np.hypot(dEy, dNy)
    # Vriden bild: x-axeln pekar at (cos v, sin v), y-axeln (nedat) at (sin v, -cos v).
    vx, vy = np.arctan2(dNx, dEx), np.arctan2(dEy, -dNy)
    res.period_px = (float(perx), float(pery))
    res.vridning_grader = float(np.degrees((vx + vy) / 2))

    kanter = {k_: len(st) for k_, st in per_kant.items()}
    if res.streck < MIN_STRECK or min(kanter.values()) < MIN_STRECK_PER_KANT:
        return vagra(f"för få kilometerstreck i marginalen ({res.streck} av 36; "
                     + ", ".join(f"{k_} {n_}" for k_, n_ in kanter.items()) + ")")
    if not (PERIOD_MIN < perx < PERIOD_MAX and PERIOD_MIN < pery < PERIOD_MAX):
        return vagra(f"skalan {perx:.1f}/{pery:.1f} px per km stämmer inte med 1:20 000")
    if abs(perx - pery) > PERIOD_SKILLNAD_MAX:
        return vagra(f"olika skala i de två leden ({perx:.1f} mot {pery:.1f} px per km)")
    if abs(vx - vy) > VRIDNING_SKILLNAD_MAX:
        return vagra("kanterna och strecken är inte vridna lika -- skev modell")
    if abs(beta) > BETA_MAX_M:
        return vagra(f"kartytans kant ligger {beta:.0f} m från bladgränsen")

    # Lamna ett streck (eller korset) utanfor: hur langt fel hamnar det?
    loo = []
    for k, o_ in enumerate(obs):
        if not aktiv[k] or o_[6] == "kant" or (o_[6] == "kors" and o_[2] == "N"):
            continue
        a2 = aktiv.copy()
        a2[k] = False
        if o_[6] == "kors":
            a2[k + 1] = False
            _, f2 = _kant_losning(obs, a2)
            loo.append(float(np.hypot(f2[k], f2[k + 1])))
        else:
            _, f2 = _kant_losning(obs, a2)
            loo.append(abs(float(f2[k])))
    loo = np.array(loo)
    res.loo_medel_m = float(loo.mean())
    res.loo_p95_m = float(np.percentile(loo, 95))
    res.rms_grad2_m = float(np.sqrt((fel[aktiv & (slag != "kant")] ** 2).mean()))
    if res.loo_p95_m > KANT_LOO_P95_MAX_M:
        return vagra(f"lägesfelet för stort ({res.loo_p95_m:.1f} m, gräns "
                     f"{KANT_LOO_P95_MAX_M:.0f} m)")

    # Passpunkter till GDAL: modellen utvard i ett rutnat over kartytan. Den
    # ar ett andragradspolynom, sa GDAL:s andragradsanpassning ar exakt.
    u = np.linspace(0, 1, 11)
    U, V = np.meshgrid(u, u)
    U, V = U.ravel(), V.ravel()
    px = NV[0] * (1 - U) * (1 - V) + NO[0] * U * (1 - V) + SV[0] * (1 - U) * V + SO[0] * U * V
    py = NV[1] * (1 - U) * (1 - V) + NO[1] * U * (1 - V) + SV[1] * (1 - U) * V + SO[1] * U * V
    r_ = _rader(px, py)
    res.passpunkter = np.column_stack([px, py, r_ @ c[0:6], r_ @ c[6:12]])
    _skriv(tif, res.passpunkter, minx, maxy, utfil)
    res.ok = True
    res.utfil = utfil
    return res


def rad_for_uttag(bladnamn: str, ar: int | None, r: Resultat) -> str:
    """En rad till uttag.txt, i samma ton som resten av rapporten."""
    arstr = f" ({ar})" if ar else ""
    if not r.ok:
        return (f"Ekonomiska kartan 1:20 000, blad {bladnamn}{arstr}: utelämnat -- "
                f"{r.orsak}. Bladet finns och kan hämtas för hand.")
    if r.metod == "kant":
        return (f"Ekonomiska kartan 1:20 000, blad {bladnamn}{arstr}: rutnätet är "
                f"bara tryckt som streck i marginalen, så bladet är georefererat mot "
                f"kartytans kant och {r.streck} kilometerstreck"
                f"{' samt korset mitt på bladet' if r.kors else ''}. Lägesfel i "
                f"georefereringen {r.loo_medel_m:.1f} m i medel, {r.loo_p95_m:.1f} m "
                f"för 95 % -- prövat mot blad med heldraget rutnät är det verkliga "
                f"felet omkring 2 m större. Det gäller georefereringen, inte kartan: "
                f"vad kartan själv visar är osäkrare än så.")
    return (f"Ekonomiska kartan 1:20 000, blad {bladnamn}{arstr}: georefererat mot "
            f"kartans tryckta RT 90-rutnät, {len(r.passpunkter)} passpunkter. "
            f"Lägesfel i georefereringen {r.loo_medel_m:.1f} m i medel, "
            f"{r.loo_p95_m:.1f} m för 95 %. Det gäller georefereringen, inte kartan: "
            f"vad kartan själv visar är osäkrare än så.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 5:
        sys.exit("användning: rutnat_20k.py blad.tif minx maxy ut.tif")
    r = georeferera_20k(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4])
    print(rad_for_uttag(os.path.basename(sys.argv[1]), None, r))

"""Ar kopiorna av ekonomiska kartans karna lika? Bara lasning, inget skrivs.

Karnan (lm_ekokarta_karna) finns byte for byte i tva plugin, och delar av
den i ett tredje projekt:

    LM Faltunderlag                       lm_faltunderlag/lm_ekokarta_karna/
    LM Ekonomiska kartan – alla skalor    lm_ekokarta/lm_ekokarta_karna/
    LM Historiska kartor (aldre kopia)    lm_historiska_kartor/underlag/

De tva forsta ska vara identiska -- skiljer de sig ar det ett FEL och
skriptet avslutar med kod 1. Kopiorna i LM Historiska kartor har en egen
rubrikrad och andra filnamn (ekokarta.py = blad.py); de jamfors utan rubriken
och ger en VARNING, inte ett fel: det projektet ska inte andras harifran.
Radslut raknas inte (git checkar ut CRLF pa Windows).

    python kontroll/jamfor_karna.py [--falt MAPP] [--alla MAPP] [--hk MAPP]

Mapparna ar plugin- eller projektrotterna. Utan argument letas de bredvid
det har repot och i C:\\Claude_projekt.
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys

HAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMN_ALLA = "lm-ekonomiska-kartan-alla-skalor"
PROJEKT = r"C:\Claude_projekt"        # dar projekten ligger pa utvecklingsdatorn

# karnfil -> filnamn i LM Historiska kartor/lm_historiska_kartor/underlag
HK_PAR = {"rutnat_20k.py": "rutnat_20k.py", "blad.py": "ekokarta.py",
          "gdalfart.py": "gdalfart.py"}


def _forsta(*kandidater: str) -> str | None:
    for k in kandidater:
        if k and os.path.isdir(k):
            return k
    return None


def _las(sokvag: str, utan_rubrik: bool = False) -> list[str]:
    with open(sokvag, encoding="utf-8") as f:
        rader = f.read().replace("\r\n", "\n").split("\n")
    if utan_rubrik:
        # "# Kopierad ur LM Faltunderlag ..." -- kommentarsrader fore koden
        while rader and rader[0].startswith("#"):
            rader.pop(0)
    return rader


def _skillnad(a: list[str], b: list[str], na: str, nb: str, n: int = 12) -> str:
    d = list(difflib.unified_diff(a, b, na, nb, lineterm="", n=1))
    return "\n".join(d[:n]) + (f"\n      ... {len(d) - n} rader till" if len(d) > n else "")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--falt", help="LM Faltunderlags repo (med lm_faltunderlag/)")
    p.add_argument("--alla", help=f"{NAMN_ALLA} (med lm_ekokarta/)")
    p.add_argument("--hk", help="LM Historiska kartor (med lm_historiska_kartor/)")
    a = p.parse_args()

    upp = os.path.dirname(HAR)
    falt = _forsta(a.falt, HAR if os.path.isdir(os.path.join(HAR, "lm_faltunderlag")) else None,
                   upp if os.path.isdir(os.path.join(upp, "lm_faltunderlag")) else None,
                   os.path.join(upp, "Fältförberedelser"), os.path.join(PROJEKT, "Fältförberedelser"))
    alla = _forsta(a.alla, HAR if os.path.isdir(os.path.join(HAR, "lm_ekokarta")) else None,
                   os.path.join(HAR, NAMN_ALLA), os.path.join(upp, NAMN_ALLA))
    hk = _forsta(a.hk, os.path.join(upp, "LM Historiska kartor"),
                 os.path.join(PROJEKT, "LM Historiska kartor"))

    fel, varn = 0, 0
    if not falt or not alla:
        print(f"FEL  hittar inte {'LM Faltunderlag' if not falt else NAMN_ALLA}; ange --falt/--alla")
        return 1
    k1 = os.path.join(falt, "lm_faltunderlag", "lm_ekokarta_karna")
    k2 = os.path.join(alla, "lm_ekokarta", "lm_ekokarta_karna")
    print(f"Faltunderlaget: {k1}\nAlla skalor:    {k2}")
    filer = sorted({f for k in (k1, k2) if os.path.isdir(k)
                    for f in os.listdir(k) if f.endswith(".py")})
    for f in filer:
        a1, a2 = os.path.join(k1, f), os.path.join(k2, f)
        if not (os.path.exists(a1) and os.path.exists(a2)):
            print(f"   FEL  {f} finns bara i {'Faltunderlaget' if os.path.exists(a1) else 'Alla skalor'}")
            fel += 1
        elif _las(a1) != _las(a2):
            print(f"   FEL  {f} skiljer sig\n{_skillnad(_las(a1), _las(a2), 'falt/' + f, 'alla/' + f)}")
            fel += 1
        else:
            print(f"   lika {f}")

    if hk:
        u = os.path.join(hk, "lm_historiska_kartor", "underlag")
        print(f"LM Historiska kartor: {u}")
        for kf, hf in HK_PAR.items():
            a1, a2 = os.path.join(k1, kf), os.path.join(u, hf)
            if not os.path.exists(a2):
                print(f"   VARNING  {hf} saknas där")
                varn += 1
            elif _las(a1) != _las(a2, utan_rubrik=True):
                print(f"   VARNING  {hf} skiljer sig från kärnans {kf} -- rätta där för hand\n"
                      f"{_skillnad(_las(a1), _las(a2, True), 'karna/' + kf, 'hk/' + hf)}")
                varn += 1
            else:
                print(f"   lika {hf} (= {kf})")
        print("   (kontroll.py, nedladdning.py med flera där jämförs inte: de är "
              "Faltunderlagets egna moduler, inte kärnan)")
    else:
        print("LM Historiska kartor hittades inte; ange --hk för att jämföra dess kopior")

    print(f"\n{'ALLA KOPIOR LIKA' if not fel else f'{fel} FEL'}"
          f"{f', {varn} varningar' if varn else ''}")
    return 1 if fel else 0


if __name__ == "__main__":
    sys.exit(main())

"""Ekonomiska kartan: bladindelning, hamtning och georeferering av 1:20 000-bladen.

Karnan som LM Faltunderlag och LM Ekonomiska kartan – alla skalor delar. Den
har inga QGIS-importer -- bara numpy, GDAL och standardbiblioteket -- sa att
den kan koras utan QGIS och provas fristaende.

**Samma filer finns i bada pluginen, byte for byte.** Ett QGIS-plugin kan inte
importera ur ett annat utan att det andra ar installerat, och Faltunderlaget
ska fungera som forut utan det nya pluginet. Darfor en kopia i vardera:

    lm_faltunderlag/lm_ekokarta_karna/                        (LM Faltunderlag)
    lm-ekonomiska-kartan-alla-skalor/lm_ekokarta/lm_ekokarta_karna/

En rattning gors i bada. `kontroll/jamfor_karna.py` jamfor dem och varnar
aven for kopiorna i LM Historiska kartor (`lm_historiska_kartor/underlag/`).

Moduler:

    rutnat_20k  georefereringen mot kartans eget rutnat (METOD_VERSION, sparrar)
    blad        bladindelningen som Faltunderlaget anvander, ordagrant
    blad_alla   bladsokning over hela serien, med val av utgava (nytt pluginet)
    cache_20k   hamta, georeferera och cacha ett 1:20 000-blad
    ftp         nedladdning over anonym FTP
    filer       halvfardiga filer och rasterkontroll
    gdalfart    alla karnor at GDAL
"""

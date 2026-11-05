"""Tva Processing-algoritmer for rutnat: bladrutnatet och ett fast rutnat.

Bada ger ett GeoPackage som gar att anvanda som omrade i
lmeko:hamta_ekonomiska_kartan, med alla eller bara markerade rutor
("Endast markerade objekt" i verktygslådan).
"""
from __future__ import annotations

import os

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
                       QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingException,
                       QgsProcessingOutputNumber, QgsProcessingOutputString,
                       QgsProcessingOutputVectorLayer, QgsProcessingParameterBoolean,
                       QgsProcessingParameterCrs, QgsProcessingParameterExtent,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterFile,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterNumber)

from . import listning, rutnat, stil
from .lm_ekokarta_karna import blad_alla


def cachefil(arkiv: str) -> str:
    """Listningens cache: i arkivet om det finns ett, annars i QGIS-profilen."""
    if arkiv:
        return os.path.join(arkiv, "ekonomiska_kartan", listning.CACHEFIL)
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "lm_ekokarta", listning.CACHEFIL)


class Bladrutnat(QgsProcessingAlgorithm):
    ARKIV, LISTA_OM, CRS, UTDATA = "ARKIV", "LISTA_OM", "CRS", "UTDATA"

    def name(self):
        return "bladrutnat"

    def displayName(self):
        return "Bladrutnät (översikt över bladen i båda skalorna)"

    def group(self):
        return "Ekonomiska kartan"

    def groupId(self):
        return "ekonomiska_kartan"

    def createInstance(self):
        return Bladrutnat()

    def shortHelpString(self):
        return (
            "Bygger ett GeoPackage med bladrutorna för hela ekonomiska kartan, "
            "1:10 000 (5 km) och 1:20 000 (10 km), ur Lantmäteriets FTP-katalog.\n\n"
            "Fält: blad, serie, skala, år (nyaste), äldsta år, alla år, antal "
            "utgåvor, om bladet finns i arkivet (hämtat, georefererat eller "
            "vägrat) och listningens datum.\n\n"
            "Listningen tar omkring en minut och sparas med datum, i arkivet om "
            "ett anges, annars i QGIS-profilen. Nästa gång används den sparade "
            "listningen, om du inte kryssar i att lista på nytt. Datumet står i "
            "lagrets namn och i fältet listad.\n\n"
            "Markera rutor i lagret och använd det som område i Hämta ekonomiska "
            "kartan med Endast markerade objekt: samma skal- och utgåveregler "
            "gäller som annars.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.ARKIV, "Arkiv (valfritt): listningens cache och vilka blad som är hämtade",
            behavior=Qgis.ProcessingFileParameterBehavior.Folder, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LISTA_OM, "Lista FTP:n på nytt (annars den sparade listningen)",
            defaultValue=False))
        self.addParameter(QgsProcessingParameterCrs(
            self.CRS, "Koordinatsystem", defaultValue="EPSG:3006"))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.UTDATA, "Bladrutnät", fileFilter="GeoPackage (*.gpkg)"))
        self.addOutput(QgsProcessingOutputVectorLayer(
            "BLADRUTNAT", "Bladrutnät", Qgis.ProcessingSourceType.VectorPolygon))
        self.addOutput(QgsProcessingOutputString("LISTAD", "Listningens datum"))
        self.addOutput(QgsProcessingOutputNumber("RUTOR_10K", "Rutor i 1:10 000"))
        self.addOutput(QgsProcessingOutputNumber("BLAD_20K", "Blad i 1:20 000"))

    def prepareAlgorithm(self, parameters, context, feedback):
        self._arkiv = (self.parameterAsString(parameters, self.ARKIV, context) or "").strip()
        self._cache = cachefil(self._arkiv)
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        self._dst = crs.authid() if crs.authid().upper().startswith("EPSG:") else crs.toWkt()
        return True

    def processAlgorithm(self, parameters, context, feedback):
        ny = self.parameterAsBool(parameters, self.LISTA_OM, context)
        utfil = self.parameterAsFileOutput(parameters, self.UTDATA, context)
        if not utfil.lower().endswith(".gpkg"):
            utfil += ".gpkg"
        if not ny and os.path.exists(self._cache):
            feedback.pushInfo(f"Sparad listning: {self._cache}")
        else:
            feedback.pushInfo("Listar FTP-katalogen (omkring en minut)")
        try:
            lis = listning.lista(self._cache, ny, feedback.setProgressText,
                                 feedback.setProgress, feedback.isCanceled)
        except blad_alla.Katalogfel as e:
            raise QgsProcessingException(str(e))
        feedback.setProgressText("Skriver bladrutnätet")
        n10, n20 = rutnat.bladrutnat(lis, self._arkiv, utfil, self._dst)
        feedback.pushInfo(f"Listat {lis.datum}: {n10} rutor i 1:10 000, {n20} blad i 1:20 000")
        namn = f"Bladrutnät, listat {lis.datum}"
        kalla = utfil + "|layername=bladrutnat"
        context.addLayerToLoadOnCompletion(kalla, QgsProcessingContext.LayerDetails(
            namn, context.project(), "BLADRUTNAT"))
        context.layerToLoadOnCompletionDetails(kalla).setPostProcessor(
            stil.efter(stil.bladrutnat, namn))
        return {self.UTDATA: utfil, "BLADRUTNAT": kalla, "LISTAD": lis.datum,
                "RUTOR_10K": n10, "BLAD_20K": n20}


class FastRutnat(QgsProcessingAlgorithm):
    LAGER, UTBREDNING, STORLEK, UTDATA = "LAGER", "UTBREDNING", "STORLEK", "UTDATA"

    def name(self):
        return "fast_rutnat"

    def displayName(self):
        return "Fast rutnät i SWEREF 99 TM"

    def group(self):
        return "Ekonomiska kartan"

    def groupId(self):
        return "ekonomiska_kartan"

    def createInstance(self):
        return FastRutnat()

    def shortHelpString(self):
        return (
            "Kvadratiska rutor i SWEREF 99 TM (EPSG:3006) över ett område. Hörnen "
            "ligger på jämna multipler av rutstorleken, så rutor från olika "
            "körningar passar ihop, och rutnamnet byggs av nedre vänstra hörnet "
            "i meter: N7082500_E520000.\n\n"
            "Använd rutnätet som område i Hämta ekonomiska kartan, med alla "
            "eller bara markerade rutor. Kryssa där i En GeoTIFF per ruta för "
            "att få brickor: en GeoTIFF per ruta med samma pixelstorlek och "
            "pixelrutnät, färdiga för maskininlärning.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LAGER, "Område: polygonlager",
            [Qgis.ProcessingSourceType.VectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterExtent(
            self.UTBREDNING, "Område: utbredning", optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.STORLEK, "Rutstorlek (km), t.ex. 1, 2,5, 5 eller 10",
            Qgis.ProcessingNumberParameterType.Double, defaultValue=2.5, minValue=0.1))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.UTDATA, "Rutnät", fileFilter="GeoPackage (*.gpkg)"))
        self.addOutput(QgsProcessingOutputVectorLayer(
            "RUTNAT", "Rutnät", Qgis.ProcessingSourceType.VectorPolygon))
        self.addOutput(QgsProcessingOutputNumber("ANTAL", "Antal rutor"))

    def prepareAlgorithm(self, parameters, context, feedback):
        sw = QgsCoordinateReferenceSystem(rutnat.SWEREF)
        delar = []
        kalla = self.parameterAsSource(parameters, self.LAGER, context)
        if kalla is not None:
            ct = QgsCoordinateTransform(kalla.sourceCrs(), sw, context.transformContext())
            for f in kalla.getFeatures(QgsFeatureRequest().setNoAttributes()):
                g = QgsGeometry(f.geometry())
                if not g.isEmpty():
                    g.transform(ct)
                    delar.append(g)
        if parameters.get(self.UTBREDNING):
            g = self.parameterAsExtentGeometry(parameters, self.UTBREDNING, context, sw)
            if g and not g.isEmpty():
                delar.append(g)
        if not delar:
            raise QgsProcessingException("Inget område angivet: välj ett polygonlager eller en utbredning.")
        self._wkt = QgsGeometry.unaryUnion(delar).asWkt()
        return True

    def processAlgorithm(self, parameters, context, feedback):
        km = self.parameterAsDouble(parameters, self.STORLEK, context)
        utfil = self.parameterAsFileOutput(parameters, self.UTDATA, context)
        if not utfil.lower().endswith(".gpkg"):
            utfil += ".gpkg"
        try:
            n = rutnat.fast_rutnat(self._wkt, km * 1000.0, utfil)
        except ValueError as e:
            raise QgsProcessingException(str(e))
        feedback.pushInfo(f"{n} rutor om {km:g} km")
        namn = f"Rutnät {km:g} km"
        kalla = utfil + "|layername=rutnat"
        context.addLayerToLoadOnCompletion(kalla, QgsProcessingContext.LayerDetails(
            namn, context.project(), "RUTNAT"))
        context.layerToLoadOnCompletionDetails(kalla).setPostProcessor(
            stil.efter(stil.rutnat, namn))
        return {self.UTDATA: utfil, "RUTNAT": kalla, "ANTAL": n}

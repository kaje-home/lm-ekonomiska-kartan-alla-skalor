"""Processing-algoritmen: omrade in, georefererade blad, VRT och rapport ut.

Gar att kora i verktygslådan, i batch och i Model Designer. Dialogen
(dialog.py) ar bara ett enklare satt att fylla i samma parametrar.

Omradet kan anges pa tre satt -- ett lager (med eller utan bara markerade
objekt), en utbredning eller en ritad geometri. Anges flera anvands
foreningen. Det raknas om till 5 km-rutor i RT 90 i `prepareAlgorithm`, som
kors i huvudtraden: lagren far inte lasas fran en arbetstrad.
"""
from __future__ import annotations

import os

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsFeatureRequest, QgsGeometry,
                       QgsProcessingAlgorithm, QgsProcessingContext,
                       QgsProcessingException, QgsProcessingOutputFile,
                       QgsProcessingOutputNumber, QgsProcessingOutputRasterLayer,
                       QgsProcessingOutputString, QgsProcessingOutputVectorLayer,
                       QgsProcessingParameterBoolean, QgsProcessingParameterCrs,
                       QgsProcessingParameterEnum, QgsProcessingParameterExtent,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterGeometry, QgsProcessingParameterNumber,
                       QgsRectangle)

from . import brickor as brickmod
from . import rapport, rutnat, stil, uttag
from .lm_ekokarta_karna import blad_alla

RT90 = "EPSG:3021"
SKALOR = [("auto", "Automatiskt: den skala vars blad passar utgåvan, 1:10 000 vid samma år"),
          ("10k", "Bara 1:10 000"), ("20k", "Bara 1:20 000"),
          ("bada", "Båda serierna där de finns")]
UTGAVOR = [("nyaste", "Nyaste"), ("aldsta", "Äldsta"), ("alla", "Alla utgåvor")]


class HamtaEkonomiskaKartan(QgsProcessingAlgorithm):
    LAGER = "LAGER"
    UTBREDNING = "UTBREDNING"
    GEOMETRI = "GEOMETRI"
    BUFFERT = "BUFFERT"
    SKALA = "SKALA"
    UTGAVA = "UTGAVA"
    CRS = "CRS"
    ARKIV = "ARKIV"
    VRT = "VRT"
    UTMAPP = "UTMAPP"
    BRICKOR = "BRICKOR"
    BRICKPIXEL = "BRICKPIXEL"

    def name(self):
        return "hamta_ekonomiska_kartan"

    def displayName(self):
        return "Hämta ekonomiska kartan (alla skalor)"

    def group(self):
        return "Ekonomiska kartan"

    def groupId(self):
        return "ekonomiska_kartan"

    def createInstance(self):
        return HamtaEkonomiskaKartan()

    def shortHelpString(self):
        return (
            "Hämtar Lantmäteriets ekonomiska karta (1942–1988) över ett område och "
            "levererar georefererade GeoTIFF-blad, utan att du behöver veta skala "
            "eller källa.\n\n"
            "• 1:10 000 hämtas med Lantmäteriets världsfil. Världsfilen granskas: "
            "ett blad som tryckts ihop till sin ruta lämnas utanför.\n"
            "• 1:20 000-bladen (Norrlands inland) levereras av Lantmäteriet utan "
            "georeferens och georefereras mot kartans eget tryckta kilometerrutnät. "
            "Ett blad som inte klarar kontrollerna lämnas utanför, med orsaken.\n"
            "• Automatiskt läge: där båda skalorna finns gäller utgåvevalet även "
            "mellan dem. Med Nyaste tas det yngsta bladet, med Äldsta det äldsta, "
            "och vid samma år 1:10 000. Vägras bladet tas nästa.\n\n"
            "Varje blad klipps mot sin ruta med alfaband, så kanterna blir "
            "genomskinliga. VRT:n samlar alla blad i samma ordning, och rapporten "
            "säger vilket blad som ligger överst där skalorna överlappar. Bladen är "
            "från olika år: året står i filnamnet, i bladlagret och i rapporten.\n\n"
            "Rapporten (blad.gpkg och rapport.txt) säger per blad källa, metod och "
            "lägesfel i georefereringen. Lägesfelet gäller georefereringen, inte "
            "kartans innehåll.\n\n"
            "Området kan också vara ett bladrutnät eller ett fast rutnät (de två "
            "algoritmerna bredvid), med alla eller bara markerade rutor (Endast "
            "markerade objekt). Rutor som bara nuddar området tas inte med.\n\n"
            "Brickor: med En GeoTIFF per ruta skärs varje ruta i områdeslagret ut "
            "ur mosaiken som en egen GeoTIFF i brickor/, i bladens koordinatsystem, "
            "med samma pixelstorlek och pixelrutnät i alla rutor. Rutor utan "
            "kartdata hoppas över och nämns i rapporten. Brickorna skärs en i "
            "taget, så hela mosaiken ligger aldrig i minnet.\n\n"
            "Data: Lantmäteriet, öppna data, CC0. Ingen inloggning. Fristående "
            "tillägg, inte från Lantmäteriet.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LAGER, "Område: polygonlager",
            [Qgis.ProcessingSourceType.VectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterExtent(
            self.UTBREDNING, "Område: utbredning", optional=True))
        self.addParameter(QgsProcessingParameterGeometry(
            self.GEOMETRI, "Område: geometri",
            geometryTypes=[Qgis.GeometryType.Polygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFERT, "Buffert (m)", Qgis.ProcessingNumberParameterType.Double,
            defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.SKALA, "Skala", options=[t for _, t in SKALOR], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.UTGAVA, "Utgåva, där ett blad finns från flera år",
            options=[t for _, t in UTGAVOR], defaultValue=0))
        self.addParameter(QgsProcessingParameterCrs(
            self.CRS, "Koordinatsystem för bladen", defaultValue="EPSG:3006"))
        self.addParameter(QgsProcessingParameterFile(
            self.ARKIV, "Arkiv för nedladdade blad (valfritt, kan delas med LM Fältunderlag)",
            behavior=Qgis.ProcessingFileParameterBehavior.Folder, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.VRT, "Bygg en VRT över hela området", defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.BRICKOR, "En GeoTIFF per ruta i områdeslagret (brickor)", defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.BRICKPIXEL, "Brickornas pixelstorlek (m)",
            Qgis.ProcessingNumberParameterType.Double, defaultValue=1.0, minValue=0.1))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.UTMAPP, "Utmapp"))
        self.addOutput(QgsProcessingOutputRasterLayer("VRT_LAGER", "Ekonomiska kartan (VRT)"))
        self.addOutput(QgsProcessingOutputVectorLayer(
            "BLAD", "Blad med källa och lägesfel", Qgis.ProcessingSourceType.VectorPolygon))
        self.addOutput(QgsProcessingOutputFile("RAPPORT", "Rapport (text)"))
        self.addOutput(QgsProcessingOutputNumber("LEVERERADE", "Levererade blad"))
        self.addOutput(QgsProcessingOutputNumber("UTELAMNADE", "Utelämnade blad"))
        self.addOutput(QgsProcessingOutputString("AR", "Tryckår"))
        self.addOutput(QgsProcessingOutputNumber("BRICKOR_SKRIVNA", "Brickor skrivna"))
        self.addOutput(QgsProcessingOutputNumber("BRICKOR_TOMMA", "Rutor utan kartdata"))

    # --- I huvudtraden: lagren lases har --------------------------------------
    def prepareAlgorithm(self, parameters, context, feedback):
        rt90 = QgsCoordinateReferenceSystem(RT90)
        delar: list[QgsGeometry] = []
        beskr: list[str] = []

        crs = self.parameterAsCrs(parameters, self.CRS, context)
        self._dst = crs.authid() if crs.authid().upper().startswith("EPSG:") else crs.toWkt()
        self._crs_namn = crs.authid() or crs.description()
        med_brickor = self.parameterAsBool(parameters, self.BRICKOR, context)
        self._pixel = self.parameterAsDouble(parameters, self.BRICKPIXEL, context)
        self._brickor: list[brickmod.Bricka] = []

        kalla = self.parameterAsSource(parameters, self.LAGER, context)
        if kalla is not None:
            ct = QgsCoordinateTransform(kalla.sourceCrs(), rt90, context.transformContext())
            ct_ut = QgsCoordinateTransform(kalla.sourceCrs(), crs, context.transformContext())
            falt = kalla.fields().names()
            namnfalt = next((n for n in ("ruta", "blad") if n in falt), None)
            req = QgsFeatureRequest()
            if not med_brickor:
                req.setNoAttributes()
            for f in kalla.getFeatures(req):
                g = QgsGeometry(f.geometry())
                if g.isEmpty():
                    continue
                if med_brickor:
                    # Brickan ar rutans utbredning i bladens koordinatsystem,
                    # utvidgad till hela pixlar pa ett gemensamt pixelrutnat.
                    gu = QgsGeometry(g)
                    gu.transform(ct_ut)
                    bb = gu.boundingBox()
                    namn = str(f[namnfalt]) if namnfalt and f[namnfalt] else f"ruta_{f.id()}"
                    self._brickor.append(brickmod.Bricka(namn, brickmod.pa_pixelrutnat(
                        bb.xMinimum(), bb.yMinimum(), bb.xMaximum(), bb.yMaximum(),
                        self._pixel)))
                g.transform(ct)
                delar.append(g)
            beskr.append(f"lager {kalla.sourceName()}")
        if med_brickor and not self._brickor:
            raise QgsProcessingException(
                "En GeoTIFF per ruta kräver ett områdeslager med rutor, t.ex. ett fast "
                "rutnät eller ett bladrutnät.")
        if len({b.ruta for b in self._brickor}) < len(self._brickor):
            raise QgsProcessingException(
                "Samma rutnamn (fältet ruta eller blad) finns mer än en gång i "
                "områdeslagret, och brickorna skulle skriva över varandra.")
        if parameters.get(self.UTBREDNING):
            g = self.parameterAsExtentGeometry(parameters, self.UTBREDNING, context, rt90)
            if g and not g.isEmpty():
                delar.append(g)
                beskr.append("utbredning")
        if parameters.get(self.GEOMETRI):
            g = self.parameterAsGeometry(parameters, self.GEOMETRI, context, rt90)
            if g and not g.isEmpty():
                delar.append(g)
                beskr.append("ritad yta")
        if not delar:
            raise QgsProcessingException(
                "Inget område angivet: välj ett polygonlager, en utbredning eller rita en yta.")
        yta = QgsGeometry.unaryUnion(delar)
        buffert = self.parameterAsDouble(parameters, self.BUFFERT, context)
        if buffert > 0:
            yta = yta.buffer(buffert, 8)
        bb = yta.boundingBox()
        # En ruta som bara nuddar ytan i en kant eller ett horn ar inte med,
        # t.ex. hornrutan mellan tva ytor som foljer bladgranserna, och inte
        # heller en som bara far en flisa nar ett rutlager i SWEREF raknas om
        # till RT 90 (rutnat.berors).
        self._rutor = []
        yta_m2 = yta.area()
        for x, y in blad_alla.rutor(bb.xMinimum(), bb.yMinimum(), bb.xMaximum(), bb.yMaximum()):
            r = QgsGeometry.fromRect(QgsRectangle(x, y - 5000.0, x + 5000.0, y))
            if yta.intersects(r) and rutnat.berors(yta_m2, yta.intersection(r).area()):
                self._rutor.append((x, y))
        if not self._rutor:
            raise QgsProcessingException("Området ligger utanför ekonomiska kartans rutnät.")
        km2 = yta.area() / 1e6
        self._omrade = (f"{' + '.join(beskr)}, {km2:.1f} km², "
                        f"{len(self._rutor)} rutor om 5 × 5 km"
                        + (f", buffert {buffert:.0f} m" if buffert > 0 else "")
                        + (f", {len(self._brickor)} brickor om {self._pixel:g} m pixlar"
                           if self._brickor else ""))
        return True

    # --- I arbetstraden: bara GDAL ---------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        skala = SKALOR[self.parameterAsEnum(parameters, self.SKALA, context)][0]
        utgava = UTGAVOR[self.parameterAsEnum(parameters, self.UTGAVA, context)][0]
        arkiv = (self.parameterAsString(parameters, self.ARKIV, context) or "").strip()
        utmapp = self.parameterAsString(parameters, self.UTMAPP, context)
        med_vrt = self.parameterAsBool(parameters, self.VRT, context)
        feedback.pushInfo(f"Område: {self._omrade}")
        r = uttag.Rapportor(info=feedback.pushInfo, varning=feedback.pushWarning,
                            steg=feedback.setProgressText, framsteg=feedback.setProgress,
                            avbruten=feedback.isCanceled)
        try:
            s = uttag.kor(self._rutor, utmapp, arkiv, self._dst, skala, utgava,
                          med_vrt, self._omrade, r, self._brickor or None, self._pixel)
        except uttag.Avbrutet:
            return {}
        lev = [q for q in s.rader if q.status == rapport.LEVERERAT]
        ut = [q for q in s.rader if q.status == rapport.UTELAMNAT]
        for q in s.rader:
            if q.status == rapport.UTELAMNAT:
                feedback.pushWarning(q.rad)
        # Filerna kan ha fatt reservnamn (filbyte.byt_in) om de gamla var oppna.
        blad = s.blad_gpkg + "|layername=blad" if s.blad_gpkg else None
        ar = rapport.ar_text(s.ar).replace("-", "–") if s.ar else ""
        if s.vrt:
            context.addLayerToLoadOnCompletion(s.vrt, QgsProcessingContext.LayerDetails(
                f"Ekonomiska kartan {ar}".strip(), context.project(), "VRT_LAGER"))
        if blad:
            context.addLayerToLoadOnCompletion(blad, QgsProcessingContext.LayerDetails(
                "Ekonomiska kartan – blad", context.project(), "BLAD"))
            context.layerToLoadOnCompletionDetails(blad).setPostProcessor(
                stil.efter(stil.blad))
        skrivna = sum(b.status == brickmod.SKRIVEN for b in s.brickor)
        tomma = sum(b.status == brickmod.TOM for b in s.brickor)
        if s.brickor:
            feedback.pushInfo(f"Brickor: {skrivna} skrivna till "
                              f"{os.path.join(utmapp, uttag.BRICKMAPP)}, "
                              f"{tomma} rutor utan kartdata"
                              + (f", {len(s.brickor) - skrivna - tomma} gick inte att skriva"
                                 if len(s.brickor) - skrivna - tomma else ""))
        return {self.UTMAPP: utmapp, "VRT_LAGER": s.vrt or None, "BLAD": blad,
                "RAPPORT": s.rapport_txt or None,
                "LEVERERADE": len(lev), "UTELAMNADE": len(ut), "AR": ar,
                "BRICKOR_SKRIVNA": skrivna, "BRICKOR_TOMMA": tomma}

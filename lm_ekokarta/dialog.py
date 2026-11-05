"""Dialogen: en enkel framsida till Processing-algoritmen.

Alla val blir parametrar till lmeko:hamta_ekonomiska_kartan, och arbetet kors
som en bakgrundsuppgift sa att QGIS gar att anvanda under tiden. Det som
dialogen gor utover algoritmen ar att lata en rita omradet i kartan, bygga
bladrutnatet och valja det som omrade, och lagga in resultatet i en grupp
nar det ar klart.
"""
from __future__ import annotations

import os

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                       QgsProcessingAlgRunnerTask, QgsProcessingContext,
                       QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback,
                       QgsProject, QgsRasterLayer, QgsReferencedGeometry,
                       QgsSettings, QgsVectorLayer)
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                                 QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                                 QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                                 QRadioButton, QVBoxLayout)

from . import stil
from .algoritm import SKALOR, UTGAVOR
from .rita import RitaYta

ALG = "lmeko:hamta_ekonomiska_kartan"
ALG_BLADRUTNAT = "lmeko:bladrutnat"
ALG_FAST = "lmeko:fast_rutnat"
NYCKEL = "lm_ekokarta/"


class _Aterkoppling(QgsProcessingFeedback):
    """Raderna fran arbetstraden till dialogen. Signalerna koas over till
    huvudtraden -- fonstret far inte roras fran algoritmens trad."""
    rad = pyqtSignal(str)

    def pushInfo(self, t):
        super().pushInfo(t)
        self.rad.emit(t)

    def pushWarning(self, t):
        super().pushWarning(t)
        self.rad.emit("⚠ " + t)

    def reportError(self, t, fatal=False):
        super().reportError(t, fatal)
        self.rad.emit("✖ " + t)

    def setProgressText(self, t):
        super().setProgressText(t)
        self.rad.emit(t)


class HamtaDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Hämta ekonomiska kartan")
        self.ritat = None              # (QgsGeometry, QgsCoordinateReferenceSystem)
        self.verktyg = None
        self.foregaende = None
        self.uppgift = None
        self.context = None
        self.aterkoppling = None
        self.r_uppgift = None          # bladrutnatet, en egen uppgift
        self.r_context = None
        self.r_aterkoppling = None
        self.utmapp_senast = ""
        s = QgsSettings()

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Ange ett område. Pluginet tar 1:10 000 eller 1:20 000 (georefererad mot "
            "kartans eget rutnät) efter vad som finns. Där båda finns avgör utgåvan "
            "vilket blad som tas: det yngsta eller det äldsta."))

        # --- Omrade ---
        g = QGroupBox("Område")
        gl = QVBoxLayout(g)
        self.r_karta = QRadioButton("Kartfönstrets utbredning")
        self.r_lager = QRadioButton("Polygonlager")
        self.r_rita = QRadioButton("Rita i kartan")
        self.r_rutnat = QRadioButton("Rutor ur ett rutnät")
        self.r_rutnat.setToolTip("Ett bladrutnät eller ett fast rutnät, med alla eller "
                                 "bara markerade rutor.")
        self.knappar = QButtonGroup(self)
        for i, rb in enumerate((self.r_karta, self.r_lager, self.r_rita, self.r_rutnat)):
            self.knappar.addButton(rb, i)
        self.r_karta.setChecked(True)
        gl.addWidget(self.r_karta)
        rad = QHBoxLayout()
        rad.addWidget(self.r_lager)
        self.lager = QgsMapLayerComboBox()
        self.lager.setFilters(Qgis.LayerFilter.PolygonLayer)
        rad.addWidget(self.lager, 1)
        self.bara_markerade = QCheckBox("Bara markerade objekt")
        rad.addWidget(self.bara_markerade)
        gl.addLayout(rad)
        rad = QHBoxLayout()
        rad.addWidget(self.r_rita)
        self.k_rita = QPushButton("Rita yta…")
        self.k_rita.setToolTip("Vänsterklick sätter hörnen, högerklick avslutar, Esc avbryter.")
        self.k_rita.clicked.connect(self._rita)
        rad.addWidget(self.k_rita)
        self.l_rita = QLabel("ingen yta ritad")
        rad.addWidget(self.l_rita, 1)
        gl.addLayout(rad)

        rad = QHBoxLayout()
        rad.addWidget(self.r_rutnat)
        self.rutlager = QgsMapLayerComboBox()
        self.rutlager.setFilters(Qgis.LayerFilter.PolygonLayer)
        self.rutlager.setToolTip("Bladrutnätet, ett fast rutnät eller ett annat lager med "
                                 "rutor. Rutnamnet tas ur fältet ruta eller blad.")
        rad.addWidget(self.rutlager, 1)
        self.bara_markerade_rutor = QCheckBox("Bara markerade rutor")
        self.bara_markerade_rutor.setChecked(True)
        rad.addWidget(self.bara_markerade_rutor)
        gl.addLayout(rad)
        rad = QHBoxLayout()
        rad.addSpacing(24)
        self.k_bladrutnat = QPushButton("Bygg bladrutnät")
        self.k_bladrutnat.setToolTip(
            "Bladrutorna för båda skalorna ur Lantmäteriets FTP-katalog, med år, antal "
            "utgåvor och om bladet finns i arkivet. Listningen sparas med datum.")
        self.k_bladrutnat.clicked.connect(self._bladrutnat)
        rad.addWidget(self.k_bladrutnat)
        self.lista_om = QCheckBox("lista FTP:n på nytt")
        self.lista_om.setToolTip("Annars används den sparade listningen. En ny listning tar "
                                 "omkring en minut.")
        rad.addWidget(self.lista_om)
        self.k_fast = QPushButton("Skapa fast rutnät…")
        self.k_fast.setToolTip("Rutor i SWEREF 99 TM med jämna koordinater, t.ex. 1, 2,5, "
                               "5 eller 10 km.")
        self.k_fast.clicked.connect(self._fast_rutnat)
        rad.addWidget(self.k_fast)
        rad.addStretch(1)
        gl.addLayout(rad)
        rad = QHBoxLayout()
        rad.addSpacing(24)
        self.brickor = QCheckBox("En GeoTIFF per ruta (brickor), pixelstorlek")
        self.brickor.setToolTip(
            "Varje ruta skärs ut ur mosaiken som en egen GeoTIFF i brickor/, med samma "
            "pixelstorlek och pixelrutnät i alla rutor. Rutor utan kartdata hoppas över.")
        self.brickor.setChecked(s.value(NYCKEL + "brickor", False, type=bool))
        rad.addWidget(self.brickor)
        self.brickpixel = QDoubleSpinBox()
        self.brickpixel.setRange(0.1, 100.0)
        self.brickpixel.setDecimals(1)
        self.brickpixel.setSuffix(" m")
        self.brickpixel.setValue(float(s.value(NYCKEL + "brickpixel", 1.0)))
        rad.addWidget(self.brickpixel)
        rad.addStretch(1)
        gl.addLayout(rad)
        self.r_rutnat.toggled.connect(self._rutnat_val)
        self.brickor.toggled.connect(self._rutnat_val)
        self._rutnat_val()
        lay.addWidget(g)

        # --- Val ---
        f = QFormLayout()
        self.skala = QComboBox()
        self.skala.addItems([t for _, t in SKALOR])
        self.skala.setCurrentIndex(int(s.value(NYCKEL + "skala", 0)))
        f.addRow("Skala", self.skala)
        self.utgava = QComboBox()
        self.utgava.addItems([t for _, t in UTGAVOR])
        self.utgava.setCurrentIndex(int(s.value(NYCKEL + "utgava", 0)))
        self.utgava.setToolTip("Omkring 330 blad i 1:10 000 finns från mer än ett år.")
        f.addRow("Utgåva", self.utgava)
        self.buffert = QDoubleSpinBox()
        self.buffert.setRange(0, 50000)
        self.buffert.setSuffix(" m")
        self.buffert.setValue(float(s.value(NYCKEL + "buffert", 0)))
        f.addRow("Buffert", self.buffert)
        self.crs = QgsProjectionSelectionWidget()
        self.crs.setCrs(QgsCoordinateReferenceSystem(s.value(NYCKEL + "crs", "EPSG:3006")))
        f.addRow("Koordinatsystem", self.crs)
        self.utmapp = QgsFileWidget()
        self.utmapp.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.utmapp.setFilePath(s.value(NYCKEL + "utmapp", ""))
        f.addRow("Utmapp", self.utmapp)
        self.arkiv = QgsFileWidget()
        self.arkiv.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.arkiv.setFilePath(s.value(NYCKEL + "arkiv", ""))
        self.arkiv.setToolTip("Nedladdade och georefererade blad sparas här och hämtas "
                              "inte igen. Samma arkiv som LM Fältunderlag går bra.")
        f.addRow("Arkiv (valfritt)", self.arkiv)
        self.vrt = QCheckBox("Bygg en VRT över hela området")
        self.vrt.setChecked(s.value(NYCKEL + "vrt", True, type=bool))
        f.addRow("", self.vrt)
        lay.addLayout(f)

        # --- Korning ---
        self.framsteg = QProgressBar()
        self.framsteg.setRange(0, 100)
        lay.addWidget(self.framsteg)
        self.logg = QPlainTextEdit()
        self.logg.setReadOnly(True)
        self.logg.setMinimumHeight(140)
        lay.addWidget(self.logg)
        self.resultat = QLabel("")
        self.resultat.setWordWrap(True)
        lay.addWidget(self.resultat)
        rad = QHBoxLayout()
        self.k_mapp = QPushButton("Öppna mappen")
        self.k_mapp.setEnabled(False)
        self.k_mapp.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.utmapp_senast)))
        rad.addWidget(self.k_mapp)
        rad.addStretch(1)
        self.k_avbryt = QPushButton("Avbryt")
        self.k_avbryt.setEnabled(False)
        self.k_avbryt.clicked.connect(self._avbryt)
        rad.addWidget(self.k_avbryt)
        self.k_kor = QPushButton("Hämta")
        self.k_kor.setDefault(True)
        self.k_kor.clicked.connect(self._kor)
        rad.addWidget(self.k_kor)
        lay.addLayout(rad)

    # --- Rita ------------------------------------------------------------------
    def _rita(self):
        canvas = self.iface.mapCanvas()
        self.foregaende = canvas.mapTool()
        self.verktyg = RitaYta(canvas)
        self.verktyg.klar.connect(self._ritad)
        self.verktyg.avbruten.connect(self._rita_slut)
        canvas.setMapTool(self.verktyg)
        self.hide()

    def _ritad(self, geom):
        crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        self.ritat = (geom, crs)
        ha = geom.area()
        self.l_rita.setText(f"yta ritad ({ha / 1e6:.1f} km²)" if crs.mapUnits() ==
                            Qgis.DistanceUnit.Meters else "yta ritad")
        self.r_rita.setChecked(True)
        self._rita_slut()

    def _rita_slut(self):
        canvas = self.iface.mapCanvas()
        if self.foregaende is not None:
            canvas.setMapTool(self.foregaende)
        elif self.verktyg is not None:
            canvas.unsetMapTool(self.verktyg)
        self.verktyg = None
        self.show()
        self.raise_()

    # --- Rutnat -----------------------------------------------------------------
    def _rutnat_val(self, *_):
        pa = self.r_rutnat.isChecked()
        self.brickor.setEnabled(pa)
        self.brickpixel.setEnabled(pa and self.brickor.isChecked())

    def _bladrutnat_fil(self) -> str:
        arkiv = self.arkiv.filePath().strip()
        if arkiv:
            return os.path.join(arkiv, "ekonomiska_kartan", "bladrutnat.gpkg")
        utmapp = self.utmapp.filePath().strip()
        return os.path.join(utmapp, "bladrutnat.gpkg") if utmapp else ""

    def _bladrutnat(self):
        utfil = self._bladrutnat_fil()
        if not utfil:
            self.resultat.setText("Välj ett arkiv eller en utmapp för bladrutnätet.")
            return
        alg = QgsApplication.processingRegistry().createAlgorithmById(ALG_BLADRUTNAT)
        if alg is None:
            self.resultat.setText("Algoritmen är inte registrerad -- starta om QGIS.")
            return
        # Ett inlast bladrutnat haller filen oppen; det ersatts nar det nya ar klart.
        prj = QgsProject.instance()
        gamla = [l.id() for l in prj.mapLayers().values()
                 if os.path.normcase(os.path.abspath(l.source().split("|")[0]))
                 == os.path.normcase(os.path.abspath(utfil))]
        if gamla:
            prj.removeMapLayers(gamla)
        self._spara()
        self.logg.appendPlainText("Bygger bladrutnätet" + (
            ", listar FTP:n på nytt (omkring en minut)" if self.lista_om.isChecked() else ""))
        self.r_context = QgsProcessingContext()
        self.r_context.setProject(prj)
        self.r_aterkoppling = _Aterkoppling()
        self.r_aterkoppling.rad.connect(self.logg.appendPlainText)
        p = {"ARKIV": self.arkiv.filePath().strip(), "LISTA_OM": self.lista_om.isChecked(),
             "CRS": self.crs.crs(), "UTDATA": utfil}
        self.r_uppgift = QgsProcessingAlgRunnerTask(alg, p, self.r_context, self.r_aterkoppling)
        self.r_uppgift.executed.connect(self._bladrutnat_klar)
        self.k_bladrutnat.setEnabled(False)
        QgsApplication.taskManager().addTask(self.r_uppgift)

    def _bladrutnat_klar(self, ok: bool, res: dict):
        self.k_bladrutnat.setEnabled(True)
        self.r_uppgift = None
        if not ok or not res:
            self.resultat.setText("Bladrutnätet gick inte att bygga -- se raderna ovan.")
            return
        v = QgsVectorLayer(res["BLADRUTNAT"], f"Bladrutnät, listat {res['LISTAD']}", "ogr")
        if not v.isValid():
            self.resultat.setText(f"Bladrutnätet gick inte att läsa: {res['BLADRUTNAT']}")
            return
        stil.bladrutnat(v)
        QgsProject.instance().addMapLayer(v, False)
        QgsProject.instance().layerTreeRoot().insertLayer(0, v)
        self.rutlager.setLayer(v)
        self.r_rutnat.setChecked(True)
        self.resultat.setText(
            f"Bladrutnätet: {int(res['RUTOR_10K'])} rutor i 1:10 000 och "
            f"{int(res['BLAD_20K'])} blad i 1:20 000, listat {res['LISTAD']}. Markera "
            "rutorna du vill ha i kartan och tryck Hämta.")

    def _fast_rutnat(self):
        import processing
        res = processing.execAlgorithmDialog(ALG_FAST, {})
        if res and res.get("RUTNAT"):
            # Processing har lagt in lagret; valj det som omrade.
            kalla = os.path.normcase(os.path.abspath(res["RUTNAT"].split("|")[0]))
            for l in QgsProject.instance().mapLayers().values():
                if os.path.normcase(os.path.abspath(l.source().split("|")[0])) == kalla:
                    self.rutlager.setLayer(l)
                    self.r_rutnat.setChecked(True)
                    break

    # --- Kor -------------------------------------------------------------------
    def _parametrar(self) -> dict | None:
        p = {}
        if self.r_karta.isChecked():
            c = self.iface.mapCanvas()
            e = c.extent()
            p["UTBREDNING"] = (f"{e.xMinimum()},{e.xMaximum()},{e.yMinimum()},"
                               f"{e.yMaximum()} [{c.mapSettings().destinationCrs().authid()}]")
        elif self.r_lager.isChecked():
            lager = self.lager.currentLayer()
            if lager is None:
                self.resultat.setText("Välj ett polygonlager.")
                return None
            if self.bara_markerade.isChecked():
                if not lager.selectedFeatureCount():
                    self.resultat.setText("Inga objekt är markerade i lagret.")
                    return None
                p["LAGER"] = QgsProcessingFeatureSourceDefinition(lager.id(), True)
            else:
                p["LAGER"] = lager.id()
        elif self.r_rutnat.isChecked():
            lager = self.rutlager.currentLayer()
            if lager is None:
                self.resultat.setText("Välj ett rutnät, eller bygg bladrutnätet först.")
                return None
            if self.bara_markerade_rutor.isChecked():
                if not lager.selectedFeatureCount():
                    self.resultat.setText("Inga rutor är markerade i rutnätet.")
                    return None
                p["LAGER"] = QgsProcessingFeatureSourceDefinition(lager.id(), True)
            else:
                p["LAGER"] = lager.id()
            p["BRICKOR"] = self.brickor.isChecked()
            p["BRICKPIXEL"] = self.brickpixel.value()
        else:
            if self.ritat is None:
                self.resultat.setText("Rita en yta först.")
                return None
            p["GEOMETRI"] = QgsReferencedGeometry(*self.ritat)
        utmapp = self.utmapp.filePath().strip()
        if not utmapp:
            self.resultat.setText("Välj en utmapp.")
            return None
        p.update({"BUFFERT": self.buffert.value(), "SKALA": self.skala.currentIndex(),
                  "UTGAVA": self.utgava.currentIndex(), "CRS": self.crs.crs(),
                  "ARKIV": self.arkiv.filePath().strip(), "VRT": self.vrt.isChecked(),
                  "UTMAPP": utmapp})
        return p

    def _spara(self):
        s = QgsSettings()
        s.setValue(NYCKEL + "skala", self.skala.currentIndex())
        s.setValue(NYCKEL + "utgava", self.utgava.currentIndex())
        s.setValue(NYCKEL + "buffert", self.buffert.value())
        s.setValue(NYCKEL + "crs", self.crs.crs().authid())
        s.setValue(NYCKEL + "utmapp", self.utmapp.filePath())
        s.setValue(NYCKEL + "arkiv", self.arkiv.filePath())
        s.setValue(NYCKEL + "vrt", self.vrt.isChecked())
        s.setValue(NYCKEL + "brickor", self.brickor.isChecked())
        s.setValue(NYCKEL + "brickpixel", self.brickpixel.value())

    def _kor(self):
        p = self._parametrar()
        if p is None:
            return
        self._spara()
        alg = QgsApplication.processingRegistry().createAlgorithmById(ALG)
        if alg is None:
            self.resultat.setText("Algoritmen är inte registrerad -- starta om QGIS.")
            return
        self.logg.clear()
        self.resultat.setText("")
        self.framsteg.setValue(0)
        self.k_mapp.setEnabled(False)
        self.utmapp_senast = p["UTMAPP"]
        self.context = QgsProcessingContext()
        self.context.setProject(QgsProject.instance())
        self.aterkoppling = _Aterkoppling()
        self.aterkoppling.rad.connect(self.logg.appendPlainText)
        self.aterkoppling.progressChanged.connect(lambda v: self.framsteg.setValue(int(v)))
        self.uppgift = QgsProcessingAlgRunnerTask(alg, p, self.context, self.aterkoppling)
        self.uppgift.executed.connect(self._klar)
        self.k_kor.setEnabled(False)
        self.k_avbryt.setEnabled(True)
        QgsApplication.taskManager().addTask(self.uppgift)

    def _avbryt(self):
        if self.aterkoppling is not None:
            self.aterkoppling.cancel()

    def _klar(self, ok: bool, res: dict):
        self.k_kor.setEnabled(True)
        self.k_avbryt.setEnabled(False)
        self.uppgift = None
        if not ok or not res:
            self.resultat.setText("Avbrutet eller misslyckat -- se raderna ovan.")
            return
        self.k_mapp.setEnabled(True)
        ar = res.get("AR") or ""
        rot = QgsProject.instance().layerTreeRoot()
        grupp = rot.insertGroup(0, f"Ekonomiska kartan {ar}".strip())
        if res.get("BLAD"):
            v = QgsVectorLayer(res["BLAD"], "Blad – källa och lägesfel", "ogr")
            if v.isValid():
                stil.blad(v)
                QgsProject.instance().addMapLayer(v, False)
                grupp.addLayer(v)
        if res.get("VRT_LAGER"):
            r = QgsRasterLayer(res["VRT_LAGER"], f"Ekonomiska kartan {ar}".strip())
            if r.isValid():
                QgsProject.instance().addMapLayer(r, False)
                grupp.addLayer(r)
        self.resultat.setText(
            f"{int(res.get('LEVERERADE', 0))} blad levererade, "
            f"{int(res.get('UTELAMNADE', 0))} utelämnade"
            + (f", tryckår {ar}" if ar else "")
            + (f", {int(res['BRICKOR_SKRIVNA'])} brickor skrivna och "
               f"{int(res['BRICKOR_TOMMA'])} rutor utan kartdata"
               if res.get("BRICKOR_SKRIVNA") or res.get("BRICKOR_TOMMA") else "")
            + ". Orsaker och lägesfel per blad står i rapport.txt och i bladlagret.")

    def stang(self):
        for a in (self.aterkoppling, self.r_aterkoppling):
            if a is not None:
                a.cancel()
        if self.verktyg is not None:
            self.iface.mapCanvas().unsetMapTool(self.verktyg)
            self.verktyg = None
        self.close()

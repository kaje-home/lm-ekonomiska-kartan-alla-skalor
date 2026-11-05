"""Skalet: Processing-providern, menyn och verktygsknappen."""
from __future__ import annotations

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon

# QAction ligger i QtWidgets i Qt 5 men i QtGui i Qt 6 (QGIS 4).
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

MENY = "&Ekonomiska kartan"


class EkonomiskaKartan:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.atgard = None
        self.dialog = None

    def initProcessing(self):
        from .provider import Provider
        self.provider = Provider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        ikon = QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))
        self.atgard = QAction(ikon, "Hämta ekonomiska kartan…", self.iface.mainWindow())
        self.atgard.setToolTip("Ekonomiska kartan över ett område, georefererad, "
                               "i 1:10 000 eller 1:20 000 efter vad som finns.")
        self.atgard.triggered.connect(self.visa)
        self.iface.addPluginToMenu(MENY, self.atgard)
        self.iface.addToolBarIcon(self.atgard)

    def visa(self):
        from .dialog import HamtaDialog
        if self.dialog is None:
            self.dialog = HamtaDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()

    def unload(self):
        if self.dialog is not None:
            try:
                self.dialog.stang()
                self.dialog.deleteLater()
            except RuntimeError:
                pass
            self.dialog = None
        if self.atgard is not None:
            self.iface.removePluginMenu(MENY, self.atgard)
            self.iface.removeToolBarIcon(self.atgard)
            self.atgard.deleteLater()
            self.atgard = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

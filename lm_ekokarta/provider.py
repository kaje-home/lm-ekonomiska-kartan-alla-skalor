"""Processing-providern: hamta_ekonomiska_kartan, bladrutnat och fast_rutnat."""
from __future__ import annotations

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algoritm import HamtaEkonomiskaKartan
from .algoritm_rutnat import Bladrutnat, FastRutnat


class Provider(QgsProcessingProvider):
    def id(self):
        return "lmeko"

    def name(self):
        return "LM Ekonomiska kartan"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))

    def loadAlgorithms(self):
        self.addAlgorithm(HamtaEkonomiskaKartan())
        self.addAlgorithm(Bladrutnat())
        self.addAlgorithm(FastRutnat())

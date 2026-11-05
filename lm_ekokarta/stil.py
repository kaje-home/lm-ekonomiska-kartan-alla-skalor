"""Stilar for pluginets vektorlager, i dialogen och efter Processing.

Bladrutnatet fargas efter tryckar (decennium) och skiljs at efter skala:
1:10 000-rutorna ar halvgenomskinligt fyllda, 1:20 000-bladen bara
streckade konturer, sa att de syns ovanpa varandra.
"""
from __future__ import annotations

from qgis.core import (QgsCategorizedSymbolRenderer, QgsFillSymbol,
                       QgsPalLayerSettings, QgsProcessingLayerPostProcessorInterface,
                       QgsRendererCategory, QgsRuleBasedRenderer, QgsSingleSymbolRenderer,
                       QgsVectorLayer, QgsVectorLayerSimpleLabeling)

# Decennierna 1940-1980; viridis, lasbar aven for fargsvaga.
DECENNIER = [(1940, "#440154"), (1950, "#3b528b"), (1960, "#21918c"),
             (1970, "#5ec962"), (1980, "#fde725")]


def blad(lager: QgsVectorLayer) -> None:
    """Uttagets bladlager: konturer fargade efter utfall."""
    kat = []
    for varde, farg, text in (("levererat", "#2e7d32", "levererat"),
                              ("utelämnat", "#c62828", "utelämnat (se orsak)"),
                              ("saknas", "#757575", "ingen karta")):
        sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": farg,
                                          "outline_width": "0.6"})
        kat.append(QgsRendererCategory(varde, sym, text))
    lager.setRenderer(QgsCategorizedSymbolRenderer("status", kat))


def _etikett(lager: QgsVectorLayer, falt: str, max_skala: float) -> None:
    s = QgsPalLayerSettings()
    s.fieldName = falt
    s.scaleVisibility = True
    s.maximumScale = 1.0
    s.minimumScale = max_skala
    lager.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lager.setLabelsEnabled(True)


def bladrutnat(lager: QgsVectorLayer) -> None:
    rot = QgsRuleBasedRenderer.Rule(None)
    for skala, namn in ((10000, "1:10 000"), (20000, "1:20 000")):
        for ar, farg in DECENNIER:
            if skala == 10000:
                sym = QgsFillSymbol.createSimple({
                    "color": farg, "outline_color": farg, "outline_width": "0.2"})
                sym.setOpacity(0.45)
            else:
                sym = QgsFillSymbol.createSimple({
                    "color": "0,0,0,0", "outline_color": farg, "outline_width": "0.8",
                    "outline_style": "dash"})
            rot.appendChild(QgsRuleBasedRenderer.Rule(
                sym, filterExp=f'"skala" = {skala} AND "ar" >= {ar} AND "ar" < {ar + 10}',
                label=f"{namn}, {ar}-talet"))
        sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#9e9e9e",
                                          "outline_width": "0.4"})
        rot.appendChild(QgsRuleBasedRenderer.Rule(
            sym, filterExp=f'"skala" = {skala} AND "ar" IS NULL', label=f"{namn}, utan år"))
    lager.setRenderer(QgsRuleBasedRenderer(rot))
    _etikett(lager, "blad", 150000)


def rutnat(lager: QgsVectorLayer) -> None:
    lager.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({
        "color": "0,0,0,0", "outline_color": "#e65100", "outline_width": "0.4"})))
    _etikett(lager, "ruta", 50000)


class _Efter(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, stil, namn: str = ""):
        super().__init__()
        self.stil, self.namn = stil, namn

    def postProcessLayer(self, layer, context, feedback):
        if isinstance(layer, QgsVectorLayer):
            self.stil(layer)
            if self.namn:
                layer.setName(self.namn)
            layer.triggerRepaint()


# Processing haller inte sjalv efterbehandlarna vid liv.
_LEVANDE: list[_Efter] = []


def efter(stil, namn: str = "") -> _Efter:
    p = _Efter(stil, namn)
    _LEVANDE.append(p)
    return p

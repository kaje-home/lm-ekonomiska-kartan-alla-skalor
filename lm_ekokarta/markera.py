"""Markera rutor i kartan med QGIS eget markeringsverktyg.

Rutnatslagret blir aktivt och markeringsverktyget (rektangel) startas; alla
dess satt fungerar, aven Skift och Ctrl for att lagga till och ta bort. Enter
eller hogerklick avslutar, liksom Esc. Byter anvandaren sjalv verktyg ar
markeringen ocksa slut. Efterat atergar kartan till verktyget som var valt
fore, som i Rita yta.

Hogerklicket och tangenterna fangas med ett handelsfilter pa kartan innan
verktyget ser dem: annars skulle hogerklicket markera om under markoren.
"""
from __future__ import annotations

from qgis.core import Qgis
from qgis.PyQt.QtCore import QEvent, QObject, Qt, pyqtSignal


class MarkeraIKartan(QObject):
    klar = pyqtSignal()

    _SLUTA = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)

    def __init__(self, iface, lager):
        super().__init__()
        self.iface = iface
        self.lager = lager
        self.canvas = None
        self.verktyg = None
        self.foregaende = None
        self.meddelande = None

    def starta(self) -> None:
        self.canvas = self.iface.mapCanvas()
        self.foregaende = self.canvas.mapTool()
        self.iface.setActiveLayer(self.lager)
        self.iface.actionSelectRectangle().trigger()
        self.verktyg = self.canvas.mapTool()
        self.canvas.installEventFilter(self)
        self.canvas.viewport().installEventFilter(self)
        self.canvas.mapToolSet.connect(self._bytt)
        self.canvas.setFocus()
        self.meddelande = self.iface.messageBar().createMessage(
            "Markera rutor",
            f"Markera rutor i {self.lager.name()}. Enter eller högerklick tar dig tillbaka "
            f"till dialogen.")
        self.iface.messageBar().pushWidget(self.meddelande, Qgis.MessageLevel.Info)

    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.Type.KeyPress and e.key() in self._SLUTA:
            self.avsluta()
            return True
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                 QEvent.Type.MouseButtonDblClick) and e.button() == Qt.MouseButton.RightButton:
            if t == QEvent.Type.MouseButtonRelease:
                self.avsluta()
            return True
        if t == QEvent.Type.ContextMenu:
            return True
        return False

    def _bytt(self, ny, *_):
        if ny is not self.verktyg:
            self.avsluta(aterstall=False)

    def avsluta(self, aterstall: bool = True) -> None:
        if self.canvas is None:
            return
        canvas, self.canvas = self.canvas, None
        canvas.mapToolSet.disconnect(self._bytt)
        canvas.removeEventFilter(self)
        canvas.viewport().removeEventFilter(self)
        if aterstall and self.foregaende is not None and self.foregaende is not self.verktyg:
            canvas.setMapTool(self.foregaende)
        try:
            self.iface.messageBar().popWidget(self.meddelande)
        except RuntimeError:                    # redan stangt av anvandaren
            pass
        self.klar.emit()

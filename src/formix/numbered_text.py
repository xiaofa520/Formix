"""Editable OCR text with a gutter; line numbers are never part of copied text."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QPlainTextEdit, QWidget

class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    def paintEvent(self, event):
        self.editor.paint_numbers(event)

class NumberedTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gutter = LineNumbers(self)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.update_margin()
    def gutter_width(self):
        return 16 + self.fontMetrics().horizontalAdvance('9') * len(str(max(1, self.blockCount())))
    def update_margin(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        self.gutter.setGeometry(QRect(self.contentsRect().left(), self.contentsRect().top(), self.gutter_width(), self.contentsRect().height()))
        self.gutter.update()
    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_margin()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_margin()
    def paint_numbers(self, event):
        painter = QPainter(self.gutter)
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(block).height()
            if block.isVisible() and top + height >= event.rect().top():
                painter.drawText(0, round(top), self.gutter.width()-8, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(block.blockNumber()+1))
            top += height
            block = block.next()

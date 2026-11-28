from PySide6.QtCore import QElapsedTimer, QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QSortFilterProxyModel, Qt
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QComboBox, QLayout, QListView, QScrollArea, QSlider, QStyle, QStyleOptionSlider, QStyledItemDelegate, QWidget


class SettingsScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()
        bar = self.verticalScrollBar()
        self.scroll_animation = QPropertyAnimation(bar, b"value", self)
        self.scroll_animation.setDuration(155)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        bar.sliderPressed.connect(self.scroll_animation.stop)
        bar.actionTriggered.connect(lambda _: self.scroll_animation.stop())

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        anim = self.scroll_animation
        if not event.pixelDelta().isNull() or not delta or event.modifiers():
            anim.stop()
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        current = bar.value()
        base = current
        if anim.state() == QPropertyAnimation.State.Running:
            previous = anim.endValue()
            if (previous - current) * delta < 0:
                base = previous
        step = min(bar.pageStep(), bar.singleStep() * QApplication.wheelScrollLines())
        target = max(bar.minimum(), min(bar.maximum(), round(base - delta * step / 120)))
        anim.stop()
        if target != current:
            anim.setStartValue(current)
            anim.setEndValue(target)
            anim.start()
        event.accept()


class SettingsSlider(QSlider):
    """Keep wheel scrolling on the page and soften pointer movement on the handle."""
    def __init__(self, orientation):
        super().__init__(orientation)
        self.follow = QPropertyAnimation(self, b"value", self)
        self.follow.setDuration(85)
        self.follow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drag_offset = None

    def wheelEvent(self, event):
        event.ignore()

    def handle_geometry(self):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        style = self.style()
        groove = style.subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
        handle = style.subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        return option, groove, handle

    def mousePressEvent(self, event):
        self.follow.stop()
        _, _, handle = self.handle_geometry()
        super().mousePressEvent(event)
        if self.isSliderDown():
            self.drag_offset = event.position().x() - handle.left()

    def pointer_value(self, event):
        option, groove, handle = self.handle_geometry()
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                round(event.position().x() - self.drag_offset - groove.left()),
                max(1, groove.width() - handle.width()), option.upsideDown)

    def mouseMoveEvent(self, event):
        if self.drag_offset is None:
            return super().mouseMoveEvent(event)
        self.follow.stop()
        self.follow.setStartValue(self.value())
        self.follow.setEndValue(self.pointer_value(event))
        self.follow.start()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.follow.stop()
            self.setValue(self.pointer_value(event))
            self.drag_offset = None
        super().mouseReleaseEvent(event)


class DropdownItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), option.fontMetrics.height() + 16, 34))
        return size


class Dropdown(QComboBox):
    """Keep Qt's selection and keyboard handling while revealing the list below the field."""

    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView()
        view.setMouseTracking(True)
        view.setUniformItemSizes(True)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(view)
        popup = view.window()
        popup.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setStyleSheet("QFrame#dropdownPopup { background: transparent; border: none; }")
        popup.setObjectName("dropdownPopup")
        self.setItemDelegate(DropdownItemDelegate(self))
        self.setMaxVisibleItems(7)
        self.last_open = QElapsedTimer()
        self.reveal = QPropertyAnimation(self)
        self.reveal.setPropertyName(b"geometry")
        self.reveal.setDuration(135)
        self.reveal.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.reveal.finished.connect(lambda: view.scrollTo(view.currentIndex()))

        self.reveal.valueChanged.connect(self.round_popup)

    def round_popup(self, geometry):
        popup = self.reveal.targetObject()
        if popup is not None:
            path = QPainterPath()
            path.addRoundedRect(0, 0, geometry.width(), geometry.height(), 9, 9)
            popup.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def wheelEvent(self, event):
        if self.property("pageScroll") and not self.view().isVisible():
            event.ignore()
            return
        super().wheelEvent(event)

    def showPopup(self):
        if not self.count() or (self.last_open.isValid() and self.last_open.elapsed() < 180):
            return
        self.reveal.stop()
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(self, 0, 100)
                break
            parent = parent.parentWidget()
        anchor = self.mapToGlobal(QPoint(0, self.height() + 3))
        screen = self.screen().availableGeometry()
        room = screen.bottom() - anchor.y() + 1
        above = self.mapToGlobal(QPoint(0, 0)).y() - screen.top() - 3
        open_above = room < 80 and above > room
        if open_above:
            room = above
        if room <= 0:
            return
        super().showPopup()
        view = self.view()
        popup = view.window()
        if not popup.isVisible() or popup is self.window():
            return
        self.last_open.start()
        height = min(room, 12 + sum(view.sizeHintForRow(i) for i in range(min(self.count(), self.maxVisibleItems()))))
        if open_above:
            anchor.setY(self.mapToGlobal(QPoint(0, 0)).y() - height - 3)
        requested_width = self.property("popupWidth")
        try:
            requested_width = max(self.width(), int(requested_width)) if requested_width else 0
        except (TypeError, ValueError):
            requested_width = 0
        width = min(screen.width(), max(self.width(), popup.width(), requested_width))
        left = max(screen.left(), min(anchor.x(), screen.right() - width + 1))
        target = QRect(left, anchor.y(), width, height)
        popup.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        popup.setMinimumSize(1, 1)
        popup.setMaximumSize(16777215, 16777215)
        start = QRect(left, anchor.y(), width, min(8, height))
        popup.setGeometry(start)
        self.reveal.setTargetObject(popup)
        self.reveal.setStartValue(start)
        self.reveal.setEndValue(target)
        self.reveal.start()

    def hidePopup(self):
        self.reveal.stop()
        super().hidePopup()


class SearchDropdown(Dropdown):
    """Keep the committed selection while the editor filters a separate list."""

    def __init__(self):
        super().__init__()
        self.searching = False
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setCompleter(None)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setObjectName("searchEditor")
        self.lineEdit().installEventFilter(self)
        self.lineEdit().textEdited.connect(self.filter_items)
        self.matches = QSortFilterProxyModel(self)
        self.matches.setSourceModel(self.model())
        self.matches.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.results = QListView(self)
        self.results.setObjectName("searchResults")
        self.results.setModel(self.matches)
        self.results.setUniformItemSizes(True)
        self.results.setItemDelegate(DropdownItemDelegate(self.results))
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.clicked.connect(self.choose)
        self.results.hide()
        self.search_reveal = QPropertyAnimation(self.results, b"geometry", self)
        self.search_reveal.setDuration(135)
        self.search_reveal.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showPopup(self):
        if self.searching:
            self.end_search()
        super().showPopup()

    def begin_search(self, query):
        area = self.parentWidget()
        while area and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area:
            area.ensureWidgetVisible(self, 0, 130)
        self.searching = True
        self.results.setParent(self.window())
        self.lineEdit().setReadOnly(False)
        self.lineEdit().setFocus()
        self.lineEdit().setText(query)
        QApplication.instance().installEventFilter(self)
        self.filter_items(query)

    def filter_items(self, query):
        if not self.searching:
            self.begin_search(query)
            return
        self.matches.setFilterFixedString(query)
        self.search_reveal.stop()
        count = self.matches.rowCount()
        if not count:
            self.results.hide()
            return
        self.results.setCurrentIndex(self.matches.index(0, 0))
        self.results.scrollToTop()
        anchor = self.mapTo(self.window(), QPoint(0, self.height() + 3))
        height = min(12 + min(count, 7) * max(27, self.results.sizeHintForRow(0)),
                     self.window().height() - anchor.y())
        target = QRect(anchor.x(), anchor.y(), self.width(), max(0, height))
        opening = self.results.isHidden()
        self.results.setGeometry(target)
        self.results.show()
        self.results.raise_()
        if opening and height > 8:
            self.search_reveal.setStartValue(QRect(anchor.x(), anchor.y(), self.width(), 8))
            self.search_reveal.setEndValue(target)
            self.search_reveal.start()

    def choose(self, index):
        if index.isValid():
            self.setCurrentIndex(self.matches.mapToSource(index).row())
        self.end_search()

    def end_search(self):
        self.searching = False
        QApplication.instance().removeEventFilter(self)
        self.search_reveal.stop()
        self.results.hide()
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setText(self.itemText(self.currentIndex()))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj is self.lineEdit() and not self.searching and event.button() == Qt.MouseButton.LeftButton:
                self.begin_search("")
            elif self.searching and isinstance(obj, QWidget) and obj is not self and not self.isAncestorOf(obj):
                if obj is not self.results and not self.results.isAncestorOf(obj):
                    self.end_search()
        if self.searching and obj in (self, self.lineEdit()):
            if event.type() in (QEvent.Type.FocusOut, QEvent.Type.Hide):
                self.end_search()
            elif event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Escape:
                    self.end_search()
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.choose(self.results.currentIndex())
                    return True
                if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    step = 1 if key == Qt.Key.Key_Down else -1
                    row = max(0, min(self.matches.rowCount() - 1, self.results.currentIndex().row() + step))
                    self.results.setCurrentIndex(self.matches.index(row, 0))
                    return True
        return super().eventFilter(obj, event)

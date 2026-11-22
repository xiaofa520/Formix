from time import monotonic

from PySide6.QtCore import QTimer


def connect_action(button, callback):
    """Run the first activation immediately and ignore repeats on this button."""
    next_allowed = 0.0

    def activate():
        nonlocal next_allowed
        now = monotonic()
        if now >= next_allowed:
            next_allowed = now + 0.25
            callback()

    button.clicked.connect(activate)


def connect_navigation(group, stack):
    timer = QTimer(group)
    timer.setSingleShot(True)
    timer.setInterval(90)

    def show_selected():
        index = group.checkedId()
        if not timer.isActive() and index >= 0 and index != stack.currentIndex():
            timer.start()
            stack.setCurrentIndex(index)

    timer.timeout.connect(show_selected)
    group.idClicked.connect(show_selected)
    return timer

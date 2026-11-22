"""Paint the shared background and theme-colored frosted surfaces."""
from math import hypot
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QWidget
if __package__:
    from .background_work import run_background
else:
    from background_work import run_background


class RadialReveal(QLabel):
    """Reveal the live content from a control's position in the previous frame."""
    def __init__(self, surface, duration, *, feather_fraction=0.12):
        super().__init__(surface)
        self.feather_fraction = feather_fraction
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.mask_effect = QGraphicsOpacityEffect(self)
        self.mask_effect.setOpacity(1)
        self.setGraphicsEffect(self.mask_effect)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self.update_mask)
        self.animation.finished.connect(self.finish)
        self.hide()

    def start(self, origin, snapshot):
        self.animation.stop()
        self.setPixmap(snapshot)
        self.setGeometry(self.parentWidget().rect())
        self.origin = QPointF(origin)
        dx = max(self.origin.x(), self.width() - self.origin.x())
        dy = max(self.origin.y(), self.height() - self.origin.y())
        self.distance = hypot(dx, dy) + 1
        self.feather = min(920.0, self.distance) * self.feather_fraction
        self.update_mask(0.0)
        self.raise_()
        self.show()
        self.animation.start()

    def update_mask(self, progress):
        outer = progress * (self.distance + self.feather)
        inner = outer - self.feather
        gradient = QRadialGradient(self.origin, self.distance + self.feather)
        gradient.setColorAt(max(0.0, inner) / gradient.radius(),
                            QColor.fromRgbF(0, 0, 0, max(0.0, -inner / self.feather)))
        gradient.setColorAt(progress, Qt.GlobalColor.black)
        self.mask_effect.setOpacityMask(QBrush(gradient))

    def finish(self):
        self.animation.stop()
        self.hide()
        self.clear()


BACKGROUND_DEFAULTS = {"image_opacity": 100, "mask_opacity": 15, "blur": 5}


@lru_cache(maxsize=192)
def contrast_icon(filename, ink, checked_ink=None):
    source = QIcon(str(Path(__file__).with_name("assets") / "icons" / filename))
    result = QIcon()
    for size in (16, 24, 32, 48, 64):
        for color in {ink, checked_ink or ink}:
            pixmap = source.pixmap(size, size)
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(color))
            painter.end()
            for mode in (QIcon.Normal, QIcon.Disabled, QIcon.Active, QIcon.Selected):
                if color == ink:
                    result.addPixmap(pixmap, mode, QIcon.Off)
                if color == (checked_ink or ink):
                    result.addPixmap(pixmap, mode, QIcon.On)
    return result


def blur_source(image, limit):
    from PIL import Image
    if max(image.width(), image.height()) > limit:
        image = image.scaled(limit, limit, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    image = image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    return Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.constBits()))


def gaussian_image(source, radius):
    from PIL import ImageFilter
    blurred = source.filter(ImageFilter.GaussianBlur(radius))
    return QImage(blurred.tobytes(), blurred.width, blurred.height, blurred.width * 4,
                  QImage.Format.Format_RGBA8888_Premultiplied).copy()


class BackgroundCanvas(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.dark = False
        self.image = QImage()
        self.frosted_image = QImage()
        self.image_opacity = BACKGROUND_DEFAULTS["image_opacity"]
        self.mask_opacity = BACKGROUND_DEFAULTS["mask_opacity"]
        self.blur = BACKGROUND_DEFAULTS["blur"]
        self._blur_source = None
        self._display_image = QImage()
        self.brightness = 0.5
        self._blur_generation = 0
        self._blur_running = False

    def set_background_image(self, image):
        self.image = QImage(image)
        self._display_image = self.image
        self.frosted_image = QImage()
        self.brightness = .5
        if not image.isNull():
            thumbnail = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            weight = light = 0.0
            for y in range(thumbnail.height()):
                for x in range(thumbnail.width()):
                    color = thumbnail.pixelColor(x, y)
                    weight += color.alphaF()
                    light += color.alphaF() * (.213 * color.redF() + .715 * color.greenF() + .072 * color.blueF())
            if weight:
                self.brightness = light / weight
        self._blur_source = None
        self._refresh_blur()

    def set_effects(self, image_opacity, blur, mask_opacity=BACKGROUND_DEFAULTS["mask_opacity"]):
        previous_blur = self.blur
        self.image_opacity = max(0, min(100, image_opacity))
        self.mask_opacity = max(0, min(100, mask_opacity))
        self.blur = blur
        if blur != previous_blur:
            self._refresh_blur()
            return
        self.update()
        self.changed.emit()

    def _refresh_blur(self):
        self._blur_generation += 1
        if not self._blur_running:
            self._start_blur()
        self.update()
        self.changed.emit()

    def _start_blur(self):
        generation = self._blur_generation
        image, amount, cached = QImage(self.image), self.blur, self._blur_source
        self._blur_running = True

        def render():
            display, frosted, source = image, QImage(), cached
            if amount and not image.isNull():
                source = source or blur_source(image, 768)
                display = gaussian_image(source, max(source.size) * amount / 2600)
            if not display.isNull():
                small = blur_source(display, 320)
                frosted = gaussian_image(small, max(small.size) / 100)
            return display, frosted, source

        def ready(result, error):
            self._blur_running = False
            if generation != self._blur_generation:
                self._start_blur()
            elif not error:
                self._display_image, self.frosted_image, self._blur_source = result
                self.update()
                self.changed.emit()
        run_background(render, ready)

    def mask_strength(self):
        base = self.mask_opacity / 100
        mismatch = self.brightness if self.dark else 1 - self.brightness
        adjustment = max(0., (mismatch - .45) / .55)
        compensation = .56 if self.dark else .40
        return base + (1 - base) * min(1., base / .15) * adjustment * compensation

    def contrast_map(self, frosted):
        image = QImage(80, 48, QImage.Format_RGB32)
        painter = QPainter(image)
        bounds = QRectF(self.rect())
        painter.scale(80 / max(1., bounds.width()), 48 / max(1., bounds.height()))
        self.paint_background(painter, preview=frosted, bounds=bounds)
        painter.end()
        return image

    def text_ink(self, region, image, tint=None):
        # Sample the same reference layout across window sizes and display scales.
        left, top, right, bottom = region
        lights = []
        for v in (.3, .7):
            for u in (.15, .35, .5, .65, .85):
                x = int((left + u * (right - left)) * image.width())
                y = int((top + v * (bottom - top)) * image.height())
                color = image.pixelColor(max(0, min(image.width()-1, x)), max(0, min(image.height()-1, y)))
                rgb = color.getRgbF()[:3]
                if tint is not None:
                    rgb = [a * (1-tint.alphaF()) + b*tint.alphaF() for a,b in zip(rgb,tint.getRgbF())]
                linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
                lights.append(sum(w * c for w, c in zip((.2126, .7152, .0722), linear)))
        lights.sort()
        return "#ffffff" if 1.05 / (lights[-2] + .05) > (lights[1] + .05) / .059 else "#101820"

    def paint_background(self, painter, preview=False, bounds=None):
        if bounds is None:
            bounds = QRectF(self.rect())
        gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        colors = ("#151b24", "#202731", "#111820") if self.dark else ("#f7f8fa", "#fcfcfd", "#f1f3f6")
        for pos, color in zip((0, 0.52, 1), colors):
            gradient.setColorAt(pos, QColor(color))
        painter.fillRect(bounds, gradient)
        if self.image_opacity and not self.image.isNull():
            scale = max(bounds.width()/self.image.width(), bounds.height()/self.image.height())
            destination = QRectF(0, 0, self.image.width()*scale, self.image.height()*scale)
            destination.moveCenter(bounds.center())
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            opacity = self.image_opacity / 100
            veil = opacity * self.mask_strength()
            if opacity > veil:
                painter.setOpacity((opacity - veil) / (1 - veil))
                painter.drawImage(destination, self.frosted_image if preview else self._display_image)
            painter.setOpacity(veil)
            painter.fillRect(bounds, Qt.GlobalColor.black if self.dark else Qt.GlobalColor.white)
            painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.paint_background(painter)
        painter.end()

class GlassFrame(QFrame):
    """Paint the shared frosted backdrop through the shape of this surface."""
    def __init__(self, radius=17):
        super().__init__()
        self.radius = radius

    def surface_tint(self, dark):
        if self.parentWidget() and self.parentWidget().objectName() == "topBar":
            return QColor(32, 40, 53, 142) if dark else QColor(247, 249, 252, 152)
        return QColor(32, 40, 53, 96) if dark else QColor(251, 253, 255, 98)

    def paintEvent(self, event):
        canvas = getattr(self.window(), "canvas", None)
        if canvas is None:
            return super().paintEvent(event)
        bounds = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(bounds, self.radius, self.radius)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipPath(path)
        if not canvas.image.isNull():
            origin = self.mapTo(canvas, self.rect().topLeft())
            painter.save()
            painter.translate(-origin.x(), -origin.y())
            canvas.paint_background(painter, preview=True)
            painter.restore()
        painter.fillPath(path, self.surface_tint(canvas.dark))
        painter.end()


class SidebarGlass(GlassFrame):
    def __init__(self):
        super().__init__(radius=0)

    def surface_tint(self, dark):
        return QColor(24, 32, 44, 64) if dark else QColor(248, 250, 253, 68)



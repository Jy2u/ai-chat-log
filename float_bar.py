"""复制内容后弹出的悬浮条：存为提问 / 存为回答 / 忽略。"""

import re

from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

AUTO_HIDE_MS = 3000
LEAVE_HIDE_MS = 3000


class FloatBar(QWidget):
    saved = Signal(str, str, object)  # (role, kind, 文本或 QImage)

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._kind = "text"
        self._data = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._anim = None

        card = QFrame(self)
        card.setObjectName("card")
        lay = QHBoxLayout(self)
        # 周围留白给投影用
        lay.setContentsMargins(20, 14, 20, 28)
        lay.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(15, 20, 45, 150))
        card.setGraphicsEffect(shadow)

        self._thumb = QLabel(card)
        self._thumb.setObjectName("thumb")
        self._thumb.setVisible(False)

        self._label = QLabel(card)
        self._label.setObjectName("preview")
        self._label.setTextFormat(Qt.PlainText)
        self._label.setFixedWidth(300)

        self._btn_q = QPushButton("提问", card)
        self._btn_q.setObjectName("btnQ")
        self._btn_a = QPushButton("回答", card)
        self._btn_a.setObjectName("btnA")
        self._btn_x = QPushButton("\u00d7", card)
        self._btn_x.setObjectName("btnX")
        for b in (self._btn_q, self._btn_a, self._btn_x):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)

        inner = QHBoxLayout(card)
        inner.setContentsMargins(16, 10, 10, 10)
        inner.setSpacing(8)
        inner.addWidget(self._thumb)
        inner.addWidget(self._label)
        inner.addWidget(self._btn_q)
        inner.addWidget(self._btn_a)
        inner.addWidget(self._btn_x)

        self._btn_q.clicked.connect(lambda: self._on_save("user"))
        self._btn_a.clicked.connect(lambda: self._on_save("ai"))
        self._btn_x.clicked.connect(self._fade_out)

        self.setStyleSheet(
            """
            #card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(48, 54, 76, 0.96),
                    stop:1 rgba(28, 32, 48, 0.94));
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-top: 1px solid rgba(255, 255, 255, 0.38);
                border-bottom: 1px solid rgba(8, 10, 22, 0.55);
            }
            #preview {
                color: #e2e7f5;
                font-size: 12px;
                font-family: "Microsoft YaHei", "Segoe UI";
                background: transparent;
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                padding: 7px 16px;
                font-size: 12px;
                font-weight: 600;
                color: #ffffff;
                font-family: "Microsoft YaHei", "Segoe UI";
            }
            #btnQ {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7d99ff, stop:0.5 #5f7cf9, stop:1 #4a63f0);
                border: 1px solid rgba(255, 255, 255, 0.38);
                border-top: 1px solid rgba(255, 255, 255, 0.62);
                border-bottom: 1px solid rgba(48, 66, 168, 0.7);
            }
            #btnQ:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8ea6ff, stop:0.5 #6e89fb, stop:1 #5670f3);
            }
            #btnQ:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5670f3, stop:1 #4459de);
            }
            #btnA {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ed3ab, stop:0.5 #16b58a, stop:1 #0e9a76);
                border: 1px solid rgba(255, 255, 255, 0.32);
                border-top: 1px solid rgba(255, 255, 255, 0.55);
                border-bottom: 1px solid rgba(8, 96, 74, 0.65);
            }
            #btnA:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3fddb6, stop:0.5 #1cc79b, stop:1 #12a882);
            }
            #btnA:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #12a882, stop:1 #0c8a68);
            }
            #btnX {
                background: transparent;
                color: #9aa2b5;
                font-size: 16px;
                padding: 4px 10px;
                font-weight: normal;
            }
            #btnX:hover { color: #ffffff; }
            """
        )

    # ---------- 对外接口 ----------

    def show_for(self, text: str):
        """剪贴板有新文本时调用。"""
        self._kind = "text"
        self._data = text
        self._thumb.setVisible(False)
        self._thumb.clear()
        preview = re.sub(r"\s+", " ", text).strip()
        fm = QFontMetrics(self._label.font())
        elided = fm.elidedText(preview, Qt.ElideRight, 220)
        self._label.setText(f"已复制 {len(text)} 字　{elided}")
        self._popup(AUTO_HIDE_MS)

    def show_for_image(self, image: QImage):
        """剪贴板有新图片时调用。"""
        self._kind = "image"
        self._data = image
        pm = QPixmap.fromImage(image).scaledToHeight(
            34, Qt.SmoothTransformation
        )
        if pm.width() > 120:
            pm = pm.scaledToWidth(120, Qt.SmoothTransformation)
        self._thumb.setPixmap(pm)
        self._thumb.setVisible(True)
        self._label.setText(
            f"已复制图片 {image.width()}\u00d7{image.height()}"
        )
        self._popup(AUTO_HIDE_MS)

    # ---------- 内部 ----------

    def _on_save(self, role: str):
        # 点击后立刻消失，保存动作随后进行
        self._hide_timer.stop()
        self._stop_anim()
        self.hide()
        self.saved.emit(role, self._kind, self._data)

    def _popup(self, timeout_ms: int):
        self._hide_timer.stop()
        self.adjustSize()
        self._move_near_cursor()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._animate(0.0, 1.0, 160)
        else:
            self._stop_anim()
            self.setWindowOpacity(1.0)
        self._hide_timer.start(timeout_ms)

    def _move_near_cursor(self):
        """出现在鼠标指针旁：优先右下方，越界时翻到上方并收进屏幕内。"""
        pos = QCursor.pos()
        screen = (
            QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        )
        geo = screen.availableGeometry()
        x = pos.x() + 12
        y = pos.y() + 18
        if y + self.height() > geo.bottom() - 8:
            y = pos.y() - self.height() - 14
        x = max(geo.left() + 8, min(x, geo.right() - self.width() - 8))
        y = max(geo.top() + 8, min(y, geo.bottom() - self.height() - 8))
        self.move(x, y)

    def _fade_out(self):
        self._hide_timer.stop()
        if self.isVisible():
            self._animate(self.windowOpacity(), 0.0, 200, hide_after=True)

    def _animate(self, start, end, ms, hide_after=False):
        self._stop_anim()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if hide_after:
            anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isVisible():
            self._hide_timer.start(LEAVE_HIDE_MS)
        super().leaveEvent(event)

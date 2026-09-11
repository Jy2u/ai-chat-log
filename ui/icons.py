"""侧栏与工具栏用的绘制图标。"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygon


def _make_subject_icon() -> QIcon:
    """画一个笔记本图标，表示课题。"""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(90, 110, 230, 235))
    p.drawRoundedRect(8, 6, 32, 36, 6, 6)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(14, 8, 24, 32, 4, 4)
    p.setBrush(QColor(90, 110, 230, 90))
    p.drawRoundedRect(18, 14, 16, 3, 1, 1)
    p.drawRoundedRect(18, 21, 16, 3, 1, 1)
    p.drawRoundedRect(18, 28, 11, 3, 1, 1)
    p.end()
    return QIcon(pm)


def _make_folder_icon() -> QIcon:
    """画一个文件夹图标。"""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(133, 156, 235, 235))
    p.drawRoundedRect(5, 10, 18, 12, 4, 4)
    p.drawRoundedRect(5, 15, 38, 24, 5, 5)
    p.setBrush(QColor(255, 255, 255, 70))
    p.drawRoundedRect(5, 15, 38, 10, 5, 5)
    p.end()
    return QIcon(pm)


def _make_chat_icon() -> QIcon:
    """画一个对话气泡图标。"""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(148, 160, 190, 220))
    p.drawRoundedRect(6, 8, 36, 26, 9, 9)
    p.drawPolygon(
        QPolygon([QPoint(14, 32), QPoint(24, 32), QPoint(13, 42)])
    )
    p.end()
    return QIcon(pm)


def _make_map_icon() -> QIcon:
    """画一个简单的分叉节点图标。"""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(80, 200, 170, 210))
    p.drawEllipse(6, 16, 16, 16)
    p.setBrush(QColor(100, 140, 255, 210))
    p.drawEllipse(28, 6, 14, 14)
    p.setBrush(QColor(170, 130, 255, 210))
    p.drawEllipse(28, 28, 14, 14)
    p.setPen(QColor(120, 140, 190, 180))
    p.setBrush(Qt.NoBrush)
    p.drawLine(22, 24, 28, 13)
    p.drawLine(22, 24, 28, 35)
    p.end()
    return QIcon(pm)


def _make_doc_icon() -> QIcon:
    """画一个文档页图标。"""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(10, 6, 28, 36, 4, 4)
    p.setBrush(QColor(90, 150, 230, 220))
    path_pts = QPolygon(
        [QPoint(26, 6), QPoint(38, 18), QPoint(26, 18)]
    )
    p.drawPolygon(path_pts)
    p.setBrush(QColor(90, 150, 230, 90))
    p.drawRoundedRect(16, 22, 16, 3, 1, 1)
    p.drawRoundedRect(16, 28, 16, 3, 1, 1)
    p.drawRoundedRect(16, 34, 11, 3, 1, 1)
    p.end()
    return QIcon(pm)


def _make_gear_icon() -> QIcon:
    """画一个齿轮图标（8 齿 + 中孔），用于设置入口。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#525b70"))
    p.translate(32, 32)
    for i in range(8):
        p.save()
        p.rotate(i * 45)
        p.drawRoundedRect(-5, -27, 10, 13, 3, 3)
        p.restore()
    p.drawEllipse(-19, -19, 38, 38)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(-8, -8, 16, 16)
    p.end()
    return QIcon(pm)


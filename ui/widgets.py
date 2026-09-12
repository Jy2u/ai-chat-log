"""侧栏树、设置弹窗、聊天页 WebEngine 封装。"""

import os
import re

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QUrl, Signal, QEvent
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextOption,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextBrowser,
    QTreeWidget,
    QVBoxLayout,
)

from db import DATA_DIR, IMAGES_DIR

# 树节点上挂的数据角色
ROLE_KIND = Qt.UserRole  # "folder" / "session" / "mindmap" / "document"
ROLE_ID = Qt.UserRole + 1
ROLE_LABEL = Qt.UserRole + 2  # 文件夹不带箭头的原始标签
ROLE_MATCH_COLOR = Qt.UserRole + 3  # 会话匹配高亮色 key
ROLE_CREATED = Qt.UserRole + 4
ROLE_UPDATED = Qt.UserRole + 5

_TIME_KINDS = ("session", "mindmap", "document")

MATCH_BTN_W = 46
MATCH_BTN_H = 22
MATCH_BTN_MARGIN = 8
MATCH_BTN_EXTRA = MATCH_BTN_W + MATCH_BTN_MARGIN + 4
MATCH_CHECK_W = 20

# key -> 显示名、色板、填充、描边
MATCH_COLORS = {
    "orange": {
        "name": "亮橙色",
        "swatch": QColor("#ff9a3d"),
        "fill": QColor(255, 154, 61, 125),
        "border": QColor("#ff8a2a"),
    },
    "pink": {
        "name": "淡粉色",
        "swatch": QColor("#ffc2d4"),
        "fill": QColor(255, 194, 212, 140),
        "border": QColor("#f39ab3"),
    },
    "blue": {
        "name": "淡蓝色",
        "swatch": QColor("#b4d4ff"),
        "fill": QColor(180, 212, 255, 145),
        "border": QColor("#7eb0f0"),
    },
    "gray": {
        "name": "灰色",
        "swatch": QColor("#c5cad3"),
        "fill": QColor(197, 202, 211, 150),
        "border": QColor("#9aa1ad"),
    },
    "purple": {
        "name": "淡紫色",
        "swatch": QColor("#d4c2f5"),
        "fill": QColor(212, 194, 245, 145),
        "border": QColor("#b89ae0"),
    },
}


def match_button_rect(item_rect: QRect) -> QRect:
    return QRect(
        item_rect.right() - MATCH_BTN_MARGIN - MATCH_BTN_W,
        item_rect.center().y() - MATCH_BTN_H // 2,
        MATCH_BTN_W,
        MATCH_BTN_H,
    )


def _color_swatch_icon(color: QColor) -> QIcon:
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(QPen(QColor(0, 0, 0, 40)))
    p.drawEllipse(1, 1, 16, 16)
    p.end()
    return QIcon(pm)


class MatchColorPopup(QFrame):
    """第二次点【匹配】时弹出的颜色选择。"""

    color_picked = Signal(object)  # str key 或 None 表示清除

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("matchColorPopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        cap = QLabel("选择高亮颜色")
        cap.setObjectName("matchColorCaption")
        lay.addWidget(cap)
        for key, spec in MATCH_COLORS.items():
            btn = QPushButton(spec["name"])
            btn.setObjectName("matchColorBtn")
            btn.setIcon(_color_swatch_icon(spec["swatch"]))
            btn.setIconSize(QSize(16, 16))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(btn)
        clear = QPushButton("清除匹配")
        clear.setObjectName("matchColorClear")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(lambda: self._pick(None))
        lay.addWidget(clear)

    def _pick(self, key):
        self.color_picked.emit(key)
        self.hide()

    def popup_at(self, global_pos: QPoint):
        self.adjustSize()
        self.move(global_pos + QPoint(-8, 6))
        self.show()
        self.raise_()

def _ordered_insert(ids, dragged_id, target_id, place: str):
    """把 dragged_id 插到 target 前（above）或后（below）。target_id 为 None 则放到末尾。"""
    ids = [i for i in ids if i != dragged_id]
    if not ids:
        return [dragged_id]
    if target_id is None or target_id not in ids:
        if place == "above":
            ids.insert(0, dragged_id)
        else:
            ids.append(dragged_id)
        return ids
    idx = ids.index(target_id)
    if place != "above":
        idx += 1
    ids.insert(idx, dragged_id)
    return ids


def _enable_tree_wrap(tree: QTreeWidget):
    tree.setWordWrap(True)
    tree.setTextElideMode(Qt.ElideNone)
    tree.setUniformRowHeights(False)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


def _drop_place(view) -> str:
    ind = view.dropIndicatorPosition()
    pos = QAbstractItemView.DropIndicatorPosition
    if ind == pos.AboveItem:
        return "above"
    if ind == pos.OnItem:
        return "on"
    return "below"


def _safe_export_stem(name: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem[:80]


def _unique_export_stem(stem: str, used: set) -> str:
    key = stem.lower()
    if key not in used:
        used.add(key)
        return stem
    i = 2
    while f"{stem} ({i})".lower() in used:
        i += 1
    out = f"{stem} ({i})"
    used.add(out.lower())
    return out

class SettingsDialog(QDialog):
    """齿轮按钮打开的设置弹窗。"""

    def __init__(self, parent, pause_action, autostart_action):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedWidth(400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(12)

        cap_general = QLabel("常规")
        cap_general.setObjectName("settingsCaption")

        cb_auto = QCheckBox("开机自启动（开机后静默缩在托盘）")
        cb_auto.setChecked(autostart_action.isChecked())
        cb_auto.toggled.connect(autostart_action.setChecked)

        cb_pause = QCheckBox("暂停记录（复制内容不再弹出悬浮条）")
        cb_pause.setChecked(pause_action.isChecked())
        cb_pause.toggled.connect(pause_action.setChecked)

        cap_data = QLabel("数据")
        cap_data.setObjectName("settingsCaption")

        row = QHBoxLayout()
        info = QLabel("所有记录保存在 data\\chatlog.db")
        btn_open = QPushButton("打开数据文件夹")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR))
        )
        row.addWidget(info)
        row.addStretch(1)
        row.addWidget(btn_open)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.button(QDialogButtonBox.Close).setText("关闭")
        box.rejected.connect(self.reject)

        lay.addWidget(cap_general)
        lay.addWidget(cb_auto)
        lay.addWidget(cb_pause)
        lay.addSpacing(6)
        lay.addWidget(cap_data)
        lay.addLayout(row)
        lay.addSpacing(4)
        lay.addWidget(box)


class SessionTreeDelegate(QStyledItemDelegate):
    """只在文字+图标区域画选中/悬停气泡；长标题换行完整显示。"""

    _PAD_X = 10
    _PAD_Y = 10
    _GAP = 8
    _META_H = 16

    def _fmt_ts(self, ts: str) -> str:
        text = (ts or "").strip()
        if len(text) >= 16 and text[4:5] == "-" and text[10:11] == " ":
            return text[:16]
        return text or "—"

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.State_Selected)
        hover = bool(opt.state & QStyle.State_MouseOver)
        bubble = opt.rect.adjusted(2, 3, -6, -3)
        kind = index.data(ROLE_KIND)
        iid = index.data(ROLE_ID)
        match_color = index.data(ROLE_MATCH_COLOR)
        tree = self.parent()
        match_fid = getattr(tree, "match_folder_id", None)
        match_sel = getattr(tree, "match_selected", set()) or set()
        hover_fid = getattr(tree, "_match_btn_hover_fid", None)
        matching_session = False
        if kind == "session" and match_fid is not None:
            parent = index.parent()
            matching_session = (
                parent.isValid()
                and parent.data(ROLE_KIND) == "folder"
                and parent.data(ROLE_ID) == match_fid
            )
        spec = MATCH_COLORS.get(match_color) if kind == "session" else None

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(bubble), 12, 12)
        if spec is not None:
            fill = QColor(spec["fill"])
            if selected:
                fill.setAlpha(min(255, fill.alpha() + 40))
            painter.setBrush(fill)
            painter.setPen(QPen(spec["border"], 1.4))
            painter.drawPath(path)
            accent = QRect(bubble.x() + 4, bubble.y() + 7, 4, bubble.height() - 14)
            painter.setPen(Qt.NoPen)
            painter.setBrush(spec["swatch"])
            painter.drawRoundedRect(accent, 2, 2)
        elif selected or hover:
            if selected:
                painter.setBrush(QColor(255, 255, 255, 178))
                painter.setPen(QPen(QColor(255, 255, 255, 230)))
            else:
                painter.setBrush(QColor(255, 255, 255, 102))
                painter.setPen(QPen(QColor(255, 255, 255, 153)))
            painter.drawPath(path)
        if matching_session and iid in match_sel:
            dash = QPainterPath()
            dash.addRoundedRect(QRectF(bubble), 12, 12)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#4a63f0"), 1.8, Qt.DashLine))
            painter.drawPath(dash)
        painter.restore()

        icon_size = (
            opt.decorationSize if opt.decorationSize.isValid() else QSize(16, 16)
        )
        x = opt.rect.x() + self._PAD_X
        y = opt.rect.y() + self._PAD_Y
        if not opt.icon.isNull():
            opt.icon.paint(
                painter,
                QRect(x, y, icon_size.width(), icon_size.height()),
                Qt.AlignCenter,
            )
            x += icon_size.width() + self._GAP

        right_reserve = 8
        if kind == "folder":
            right_reserve = MATCH_BTN_EXTRA
        elif matching_session:
            right_reserve = MATCH_CHECK_W + 10
        has_meta = kind in _TIME_KINDS
        title_h = max(
            16,
            opt.rect.height()
            - 2 * (self._PAD_Y - 2)
            - (self._META_H + 2 if has_meta else 0),
        )
        text_rect = QRectF(
            x,
            opt.rect.y() + self._PAD_Y - 2,
            max(24, opt.rect.right() - right_reserve - x),
            title_h,
        )
        font = QFont(opt.font)
        item_font = index.data(Qt.FontRole)
        if item_font is not None:
            font = QFont(item_font)
        if selected:
            font.setBold(True)
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor("#4a63f0") if selected else QColor("#2c3345"))
        text_opt = QTextOption()
        text_opt.setWrapMode(QTextOption.WrapAnywhere)
        text_opt.setAlignment(
            Qt.AlignLeft | (Qt.AlignTop if has_meta else Qt.AlignVCenter)
        )
        painter.drawText(text_rect, opt.text or "", text_opt)
        painter.restore()

        if has_meta:
            created = self._fmt_ts(index.data(ROLE_CREATED) or "")
            updated = self._fmt_ts(index.data(ROLE_UPDATED) or "")
            if updated == "—" or not updated:
                updated = created
            meta = f"创建 {created}  ·  编辑 {updated}"
            meta_rect = QRect(
                int(text_rect.x()),
                bubble.bottom() - self._META_H - 3,
                int(text_rect.width()),
                self._META_H,
            )
            meta_font = QFont(opt.font)
            meta_font.setPointSize(max(8, meta_font.pointSize() - 2))
            meta_font.setBold(False)
            painter.save()
            painter.setFont(meta_font)
            painter.setPen(QColor("#8b94ad"))
            fm = QFontMetrics(meta_font)
            painter.drawText(
                meta_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                fm.elidedText(meta, Qt.ElideRight, meta_rect.width()),
            )
            painter.restore()

        if matching_session:
            self._paint_match_check(
                painter, opt.rect, iid in match_sel
            )
        if kind == "folder":
            active = match_fid == iid
            btn_hover = hover_fid == iid
            self._paint_match_button(painter, opt.rect, active, btn_hover)

    def _paint_match_button(self, painter, item_rect, active, hover):
        btn = match_button_rect(item_rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(btn), 8, 8)
        if active:
            painter.setBrush(QColor(74, 99, 240, 230))
            painter.setPen(QPen(QColor(74, 99, 240)))
            text_color = QColor("#ffffff")
        elif hover:
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.setPen(QPen(QColor(74, 99, 240, 160)))
            text_color = QColor("#4a63f0")
        else:
            painter.setBrush(QColor(255, 255, 255, 175))
            painter.setPen(QPen(QColor(170, 180, 210, 200)))
            text_color = QColor("#5d6684")
        painter.drawPath(path)
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(btn, Qt.AlignCenter, "匹配")
        painter.restore()

    def _paint_match_check(self, painter, item_rect, checked):
        box = QRect(
            item_rect.right() - 10 - 16,
            item_rect.center().y() - 8,
            16,
            16,
        )
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#4a63f0"), 1.4))
        painter.setBrush(QColor(74, 99, 240) if checked else QColor(255, 255, 255, 200))
        painter.drawEllipse(box)
        if checked:
            painter.setPen(QPen(QColor("#ffffff"), 1.8))
            cx, cy = box.center().x(), box.center().y()
            painter.drawLine(cx - 3, cy, cx - 1, cy + 3)
            painter.drawLine(cx - 1, cy + 3, cx + 4, cy - 3)
        painter.restore()

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text or ""
        font = QFont(opt.font)
        item_font = index.data(Qt.FontRole)
        if item_font is not None:
            font = QFont(item_font)
        if opt.state & QStyle.State_Selected:
            font.setBold(True)
        fm = QFontMetrics(font)
        icon_w = 0
        icon_h = 16
        if not opt.icon.isNull():
            sz = opt.decorationSize if opt.decorationSize.isValid() else QSize(16, 16)
            icon_w = sz.width() + self._GAP
            icon_h = sz.height()
        text_w = self._text_width(option, index, icon_w)
        br = fm.boundingRect(
            0, 0, text_w, 8000, Qt.TextWordWrap | Qt.TextWrapAnywhere, text
        )
        h = max(icon_h, br.height()) + 2 * self._PAD_Y
        if index.data(ROLE_KIND) in _TIME_KINDS:
            h += self._META_H + 4
            return QSize(max(option.rect.width(), 40), max(h, 56))
        return QSize(max(option.rect.width(), 40), max(h, 38))

    def _text_width(self, option, index, icon_w: int) -> int:
        tree = self.parent()
        vw = 0
        depth = 0
        indent = 0
        if isinstance(tree, QTreeWidget):
            vw = tree.viewport().width()
            indent = tree.indentation()
            parent = index.parent()
            while parent.isValid():
                depth += 1
                parent = parent.parent()
        extra_right = 10
        kind = index.data(ROLE_KIND)
        if kind == "folder":
            extra_right += MATCH_BTN_EXTRA
        else:
            tree = self.parent()
            match_fid = getattr(tree, "match_folder_id", None)
            if kind == "session" and match_fid is not None:
                parent = index.parent()
                if (
                    parent.isValid()
                    and parent.data(ROLE_KIND) == "folder"
                    and parent.data(ROLE_ID) == match_fid
                ):
                    extra_right += MATCH_CHECK_W
        if vw <= 1:
            vw = option.rect.width() if option.rect.width() > 1 else 160
        return max(48, vw - indent * depth - icon_w - 2 * self._PAD_X - extra_right)


class SessionTree(QTreeWidget):
    """会话树：拖拽会话/导图换序或进文件夹，拖动文件夹改顺序。

    不能用 `tree.dropEvent = fn` 打补丁——Qt 从 C++ 虚表调用事件处理器，
    实例属性不会被调用，必须子类重写。
    """

    session_dropped = Signal(int, object)  # (session_id, folder_id | None)
    folder_dropped = Signal(int, object, str)  # (folder_id, target_id | None, above/below)
    entry_dropped = Signal(str, int, object, object, str)
    # src_kind, src_id, target_kind | None, target_id | None, above/below/on
    match_clicked = Signal(int, QPoint)  # folder_id, 按钮附近的全局坐标
    match_cancelled = Signal()
    match_session_toggled = Signal(int)  # 匹配模式下点选的会话 id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.match_folder_id = None
        self.match_selected = set()
        self._press_on_match_btn = False
        self._press_on_match_session = None
        self._match_btn_hover_fid = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def viewportEvent(self, event):
        if event.type() == QEvent.Leave:
            if self._match_btn_hover_fid is not None:
                self._match_btn_hover_fid = None
                self.viewport().unsetCursor()
                self.viewport().update()
        return super().viewportEvent(event)

    def _match_button_at(self, pos):
        item = self.itemAt(pos)
        if item is None or item.data(0, ROLE_KIND) != "folder":
            return None
        if match_button_rect(self.visualItemRect(item)).contains(pos):
            return item.data(0, ROLE_ID)
        return None

    def _matchable_session_at(self, pos):
        if self.match_folder_id is None:
            return None
        item = self.itemAt(pos)
        if item is None or item.data(0, ROLE_KIND) != "session":
            return None
        parent = item.parent()
        if (
            parent is None
            or parent.data(0, ROLE_KIND) != "folder"
            or parent.data(0, ROLE_ID) != self.match_folder_id
        ):
            return None
        return item.data(0, ROLE_ID)

    def mousePressEvent(self, event):
        self._press_on_match_session = None
        if event.button() == Qt.LeftButton:
            fid = self._match_button_at(event.position().toPoint())
            self._press_on_match_btn = fid is not None
            if self._press_on_match_btn:
                event.accept()
                return
            sid = self._matchable_session_at(event.position().toPoint())
            if sid is not None:
                self._press_on_match_session = sid
                event.accept()
                return
        else:
            self._press_on_match_btn = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        fid = self._match_button_at(event.position().toPoint())
        if fid != self._match_btn_hover_fid:
            self._match_btn_hover_fid = fid
            self.viewport().update()
        if fid is not None:
            self.viewport().setCursor(Qt.PointingHandCursor)
        elif self._matchable_session_at(event.position().toPoint()) is not None:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_on_match_btn:
            self._press_on_match_btn = False
            pos = event.position().toPoint()
            fid = self._match_button_at(pos)
            if fid is not None:
                item = self.itemAt(pos)
                btn = match_button_rect(self.visualItemRect(item))
                global_pos = self.viewport().mapToGlobal(btn.bottomLeft())
                self.match_clicked.emit(fid, global_pos)
            event.accept()
            return
        if self._press_on_match_session is not None:
            sid = self._matchable_session_at(event.position().toPoint())
            if sid == self._press_on_match_session:
                self.match_session_toggled.emit(sid)
            self._press_on_match_session = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._match_btn_hover_fid is not None:
            self._match_btn_hover_fid = None
            self.viewport().unsetCursor()
            self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.match_folder_id is not None:
            self.match_cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event):
        if self.match_folder_id is not None:
            event.ignore()
            return
        source = self.currentItem()
        if source is None:
            event.ignore()
            return
        kind = source.data(0, ROLE_KIND)
        if kind not in ("folder", "session", "mindmap", "document"):
            event.ignore()
            return
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        target = self.itemAt(event.position().toPoint())
        place = _drop_place(self)
        src_id = source.data(0, ROLE_ID)
        if target is None:
            self.entry_dropped.emit(kind, src_id, None, None, place)
            return
        self.entry_dropped.emit(
            kind,
            src_id,
            target.data(0, ROLE_KIND),
            target.data(0, ROLE_ID),
            place,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.doItemsLayout()

    def _folder_drop_target(self, item):
        """文件夹只在顶层之间换序，不会嵌进另一个文件夹。"""
        place = _drop_place(self)
        if item is None:
            return None, "below"
        nested = False
        folder_item = item
        while (
            folder_item is not None
            and folder_item.data(0, ROLE_KIND) != "folder"
        ):
            folder_item = folder_item.parent()
            nested = True
        if folder_item is None:
            return None, "below"
        target_id = folder_item.data(0, ROLE_ID)
        if nested:
            return target_id, "below"
        return target_id, place


class SubjectTree(QTreeWidget):
    """课题列表：拖动换序。"""

    subject_dropped = Signal(int, object, str)  # (id, target_id | None, above/below)

    def dropEvent(self, event):
        source = self.currentItem()
        if source is None or source.data(0, ROLE_KIND) != "subject":
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        src_id = source.data(0, ROLE_ID)
        if target is None:
            self.subject_dropped.emit(src_id, None, "below")
            return
        target_id = target.data(0, ROLE_ID)
        if target_id == src_id:
            return
        self.subject_dropped.emit(src_id, target_id, _drop_place(self))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.doItemsLayout()


class LocalOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    """聊天页面只允许加载本地资源。

    粘贴内容里的远程图片（![x](http://...)）会在查看时自动发请求、
    向外暴露 IP，这里一律拦截；点击 http 链接不受影响（那是导航，
    会被 ChatPage 转交系统浏览器）。
    """

    _ALLOWED = ("file", "data", "about", "qrc", "chrome", "app")

    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in self._ALLOWED:
            info.block(True)


class ChatPage(QWebEnginePage):
    """拦截气泡上的操作链接（app://action/arg）。"""

    app_action = Signal(str, str, str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame):
        scheme = url.scheme()
        if scheme == "app":
            self.app_action.emit(
                url.host(),
                url.path().strip("/"),
                url.fragment(QUrl.FullyDecoded),
            )
            return False
        if scheme in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        if scheme == "file" and not url.path().endswith("view.html"):
            # 只放行本应用图片目录里的文件（点击图片看原图），
            # 记录内容里指向其他本地文件的链接一律拦截——
            # 防止点到 file:///...something.exe 这类链接直接执行程序
            local = os.path.normcase(os.path.abspath(url.toLocalFile()))
            images = os.path.normcase(os.path.abspath(IMAGES_DIR))
            if local.startswith(images + os.sep):
                QDesktopServices.openUrl(url)
            else:
                self.app_action.emit("blocked", "", "")
            return False
        return True


class MarkdownHelpDialog(QDialog):
    """工具栏「markdown语法」打开的说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Markdown 语法")
        self.resize(720, 620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        from render_doc import markdown_help_html

        browser.setHtml(markdown_help_html())
        lay.addWidget(browser)
        box = QDialogButtonBox(QDialogButtonBox.Ok)
        box.accepted.connect(self.accept)
        lay.addWidget(box)


"""侧栏树、设置弹窗、聊天页 WebEngine 封装。"""

import os
import re

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
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
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextBrowser,
    QToolTip,
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
ROLE_SOURCE = Qt.UserRole + 6  # cursor / codex
ROLE_DONE = Qt.UserRole + 7  # 已完成

SESSION_SOURCES = {
    "cursor": "Cursor",
    "codex": "Codex",
}
NOTE_TIP_SHOW_MS = 200
SESSION_TAG_RESERVE = 58
_TAG_CHIP_H = 20
_TAG_CHIP_GAP = 5
_TAG_COL_GAP = 6
_TAG_SPECS = {
    "cursor": {
        "label": "Cursor",
        "fg": QColor("#2a4ec4"),
        "g0": QColor(190, 208, 255, 170),
        "g1": QColor(74, 99, 240, 78),
    },
    "codex": {
        "label": "Codex",
        "fg": QColor("#0b6b5c"),
        "g0": QColor(170, 232, 214, 170),
        "g1": QColor(32, 168, 140, 78),
    },
    "done": {
        "label": "已完成",
        "fg": QColor("#187a48"),
        "g0": QColor(176, 232, 198, 170),
        "g1": QColor(46, 168, 108, 72),
    },
}

_TIME_KINDS = ("session", "mindmap", "document")

MATCH_BTN_W = 46
MATCH_BTN_H = 22
MATCH_BTN_MARGIN = 8
MATCH_BTN_EXTRA = MATCH_BTN_W + MATCH_BTN_MARGIN + 4
IMPORT_BTN_W = 46
IMPORT_BTN_GAP = 5
FOLDER_BTNS_EXTRA = MATCH_BTN_EXTRA + IMPORT_BTN_W + IMPORT_BTN_GAP
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


def norm_session_source(value) -> str:
    key = (value or "").strip().lower()
    return key if key in SESSION_SOURCES else ""


def session_tag_keys(source, done) -> list:
    keys = []
    src = norm_session_source(source)
    if src:
        keys.append(src)
    if done:
        keys.append("done")
    return keys


def match_button_rect(item_rect: QRect) -> QRect:
    return QRect(
        item_rect.right() - MATCH_BTN_MARGIN - MATCH_BTN_W,
        item_rect.center().y() - MATCH_BTN_H // 2,
        MATCH_BTN_W,
        MATCH_BTN_H,
    )


def import_button_rect(item_rect: QRect) -> QRect:
    match = match_button_rect(item_rect)
    return QRect(
        match.left() - IMPORT_BTN_GAP - IMPORT_BTN_W,
        match.top(),
        IMPORT_BTN_W,
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

class GlassNoteDialog(QDialog):
    """液态玻璃风的会话备注编辑框。"""

    def __init__(self, parent=None, text=""):
        super().__init__(parent)
        self.setObjectName("glassNoteDialog")
        self.setWindowTitle("会话备注")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(440, 300)
        self._drag_pos = None

        panel = QFrame()
        panel.setObjectName("glassNotePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(70, 90, 140, 55))
        panel.setGraphicsEffect(shadow)

        title = QLabel("会话备注")
        title.setObjectName("glassNoteTitle")
        title.setAlignment(Qt.AlignCenter)

        self._edit = QPlainTextEdit()
        self._edit.setObjectName("glassNoteEdit")
        self._edit.setPlainText(text)
        self._edit.setPlaceholderText("写一点备注，指针停在对话上会看到")
        self._edit.setTabChangesFocus(True)

        cancel = QPushButton("取消")
        cancel.setObjectName("glassNoteCancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存")
        ok.setObjectName("glassNoteOk")
        ok.setDefault(True)
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(10)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(12)
        inner.addWidget(title, 0, Qt.AlignHCenter)
        inner.addWidget(self._edit, 1)
        inner.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 22)
        outer.addWidget(panel)
        self._edit.setFocus()
        self._edit.selectAll()

    def text(self) -> str:
        return self._edit.toPlainText()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._over_edit(event):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _over_edit(self, event) -> bool:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        w = self.childAt(pos)
        while w is not None and w is not self:
            if w is self._edit:
                return True
            w = w.parentWidget()
        return False


class SettingsDialog(QDialog):
    """齿轮按钮打开的设置弹窗。"""

    def __init__(self, parent, pause_action, autostart_action):
        super().__init__(parent)
        self.setObjectName("glassNoteDialog")
        self.setWindowTitle("设置")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(440)
        self._drag_pos = None

        panel = QFrame()
        panel.setObjectName("glassNotePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(70, 90, 140, 55))
        panel.setGraphicsEffect(shadow)

        title = QLabel("设置")
        title.setObjectName("glassNoteTitle")
        title.setAlignment(Qt.AlignCenter)

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
        btn_open.setObjectName("glassNoteCancel")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR))
        )
        row.addWidget(info)
        row.addStretch(1)
        row.addWidget(btn_open)

        close = QPushButton("关闭")
        close.setObjectName("glassNoteOk")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(close)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(12)
        inner.addWidget(title, 0, Qt.AlignHCenter)
        inner.addWidget(cap_general)
        inner.addWidget(cb_auto)
        inner.addWidget(cb_pause)
        inner.addSpacing(4)
        inner.addWidget(cap_data)
        inner.addLayout(row)
        inner.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 22)
        outer.addWidget(panel)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


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
        kind = index.data(ROLE_KIND)
        iid = index.data(ROLE_ID)
        match_color = index.data(ROLE_MATCH_COLOR)
        tree = self.parent()
        match_fid = getattr(tree, "match_folder_id", None)
        match_sel = getattr(tree, "match_selected", set()) or set()
        hover_fid = getattr(tree, "_match_btn_hover_fid", None)
        import_hover_fid = getattr(tree, "_import_btn_hover_fid", None)
        matching_session = False
        if kind == "session" and match_fid is not None:
            parent = index.parent()
            matching_session = (
                parent.isValid()
                and parent.data(ROLE_KIND) == "folder"
                and parent.data(ROLE_ID) == match_fid
            )
        tags = (
            session_tag_keys(index.data(ROLE_SOURCE), index.data(ROLE_DONE))
            if kind == "session"
            else []
        )
        tag_cut = SESSION_TAG_RESERVE + _TAG_COL_GAP if tags else 0
        card = kind in ("session", "mindmap", "document", "folder")
        float_t = 1.0 if selected else 0.0
        if card and not selected:
            getter = getattr(tree, "hover_float", None)
            if callable(getter):
                float_t = getter(kind, iid)
            elif hover:
                float_t = 1.0
        lift = int(round(3 * float_t))
        bubble = opt.rect.adjusted(2, 3 - lift, -(6 + tag_cut), -3 - lift)
        spec = MATCH_COLORS.get(match_color) if kind == "session" else None

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if float_t > 0.02:
            shadow = bubble.adjusted(2, 5, -2, 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(70, 90, 150, int(48 * float_t)))
            painter.drawRoundedRect(shadow, 12, 12)
        path = QPainterPath()
        path.addRoundedRect(QRectF(bubble), 12, 12)
        if spec is not None:
            fill = QColor(spec["fill"])
            extra = 48 if selected else int(48 * float_t)
            fill.setAlpha(min(255, fill.alpha() + extra))
            painter.setBrush(fill)
            painter.setPen(QPen(spec["border"], 1.4))
            painter.drawPath(path)
        elif card:
            if selected:
                fill_a, border_a, hi_a = 220, 250, 255
            else:
                fill_a = int(158 + 48 * float_t)
                border_a = int(220 + 25 * float_t)
                hi_a = int(230 + 25 * float_t)
            painter.setBrush(QColor(255, 255, 255, fill_a))
            painter.setPen(QPen(QColor(255, 255, 255, border_a), 1.25))
            painter.drawPath(path)
            painter.setPen(QPen(QColor(255, 255, 255, hi_a), 1))
            painter.drawLine(
                bubble.left() + 12,
                bubble.top() + 1,
                bubble.right() - 12,
                bubble.top() + 1,
            )
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
        y = opt.rect.y() + self._PAD_Y - lift
        if not opt.icon.isNull():
            opt.icon.paint(
                painter,
                QRect(x, y, icon_size.width(), icon_size.height()),
                Qt.AlignCenter,
            )
            x += icon_size.width() + self._GAP

        right_reserve = 8
        if kind == "folder":
            right_reserve = FOLDER_BTNS_EXTRA
        elif matching_session:
            right_reserve = MATCH_CHECK_W + 10
        text_right = min(opt.rect.right() - right_reserve, bubble.right() - 8)
        has_meta = kind in _TIME_KINDS
        title_h = max(
            16,
            opt.rect.height()
            - 2 * (self._PAD_Y - 2)
            - (self._META_H + 2 if has_meta else 0),
        )
        text_rect = QRectF(
            x,
            opt.rect.y() + self._PAD_Y - 2 - lift,
            max(24, text_right - x),
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

        if tags:
            col = QRect(
                bubble.right() + _TAG_COL_GAP,
                opt.rect.y() + 4,
                SESSION_TAG_RESERVE,
                opt.rect.height() - 8,
            )
            self._paint_session_tags(painter, col, tags)
        if matching_session:
            self._paint_match_check(
                painter, opt.rect, iid in match_sel
            )
        if kind == "folder":
            active = match_fid == iid
            btn_hover = hover_fid == iid
            self._paint_match_button(painter, opt.rect, active, btn_hover)
            self._paint_import_button(
                painter, opt.rect, import_hover_fid == iid
            )

    def _paint_session_tags(self, painter, col: QRect, tags):
        if not tags:
            return
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(True)
        fm = QFontMetrics(font)
        chips = []
        for key in tags:
            spec = _TAG_SPECS[key]
            w = min(col.width(), fm.horizontalAdvance(spec["label"]) + 14)
            chips.append((key, spec, w))
        total_h = len(chips) * _TAG_CHIP_H + (len(chips) - 1) * _TAG_CHIP_GAP
        y = col.center().y() - total_h // 2
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(font)
        for _key, spec, w in chips:
            chip = QRect(col.left() + (col.width() - w) // 2, y, w, _TAG_CHIP_H)
            path = QPainterPath()
            path.addRoundedRect(QRectF(chip), 10, 10)
            grad = QLinearGradient(chip.topLeft(), chip.bottomLeft())
            grad.setColorAt(0, spec["g0"])
            grad.setColorAt(1, spec["g1"])
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(255, 255, 255, 230), 1.1))
            painter.drawPath(path)
            painter.setPen(QPen(QColor(255, 255, 255, 245), 1))
            painter.drawLine(
                chip.left() + 6, chip.top() + 1, chip.right() - 6, chip.top() + 1
            )
            painter.setPen(spec["fg"])
            painter.drawText(chip, Qt.AlignCenter, spec["label"])
            y += _TAG_CHIP_H + _TAG_CHIP_GAP
        painter.restore()

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

    def _paint_import_button(self, painter, item_rect, hover):
        btn = import_button_rect(item_rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(btn), 8, 8)
        painter.setBrush(QColor(255, 255, 255, 230 if hover else 175))
        painter.setPen(QPen(QColor(74, 99, 240, 160) if hover else QColor(170, 180, 210, 200)))
        painter.drawPath(path)
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#4a63f0") if hover else QColor("#5d6684"))
        painter.drawText(btn, Qt.AlignCenter, "导入")
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

    def helpEvent(self, event, view, option, index):
        if event is not None and event.type() == QEvent.ToolTip:
            # 会话备注由 SessionTree 自己画，避免系统 QToolTip 抢走鼠标。
            if index.data(ROLE_KIND) == "session" and (
                index.data(Qt.ToolTipRole) or ""
            ).strip():
                return True
            note = (index.data(Qt.ToolTipRole) or "").strip()
            if note:
                QToolTip.showText(event.globalPos(), note, view)
            else:
                QToolTip.hideText()
            return True
        return super().helpEvent(event, view, option, index)

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
            min_h = 56
            n_tags = len(
                session_tag_keys(index.data(ROLE_SOURCE), index.data(ROLE_DONE))
            )
            if n_tags:
                min_h = max(
                    min_h,
                    n_tags * _TAG_CHIP_H + (n_tags - 1) * _TAG_CHIP_GAP + 16,
                )
            return QSize(max(option.rect.width(), 40), max(h, min_h))
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
            extra_right += FOLDER_BTNS_EXTRA
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
            if kind == "session" and session_tag_keys(
                index.data(ROLE_SOURCE), index.data(ROLE_DONE)
            ):
                extra_right += SESSION_TAG_RESERVE + _TAG_COL_GAP
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
    import_clicked = Signal(int)  # folder_id
    match_cancelled = Signal()
    match_session_toggled = Signal(int)  # 匹配模式下点选的会话 id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.match_folder_id = None
        self.match_selected = set()
        self._press_on_match_btn = False
        self._press_on_import_btn = False
        self._press_on_match_session = None
        self._match_btn_hover_fid = None
        self._import_btn_hover_fid = None
        self._note_tip_timer = QTimer(self)
        self._note_tip_timer.setSingleShot(True)
        self._note_tip_timer.timeout.connect(self._show_note_tip)
        self._note_tip_item = None
        self._note_tip_shown = None
        self._note_tip_pos = QPoint()
        self._note_bubble = None
        self._float_key = None
        self._float_leaving = None
        self._float_t = 0.0
        self._float_anim = QVariantAnimation(self)
        self._float_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._float_anim.valueChanged.connect(self._on_float_tick)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def hover_float(self, kind, iid) -> float:
        pair = (kind, iid)
        if pair == self._float_key:
            return self._float_t
        if pair == self._float_leaving:
            return self._float_t
        return 0.0

    def _on_float_tick(self, value):
        self._float_t = float(value)
        if self._float_t <= 0.01:
            self._float_leaving = None
        self.viewport().update()

    def _set_float_key(self, key):
        if key == self._float_key:
            return
        self._float_anim.stop()
        if key is None:
            self._float_leaving = self._float_key
            self._float_key = None
            self._float_anim.setEasingCurve(QEasingCurve.InCubic)
            self._float_anim.setDuration(160)
            self._float_anim.setStartValue(self._float_t)
            self._float_anim.setEndValue(0.0)
        else:
            self._float_leaving = None
            self._float_key = key
            self._float_t = 0.0
            self._float_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._float_anim.setDuration(220)
            self._float_anim.setStartValue(0.0)
            self._float_anim.setEndValue(1.0)
        self._float_anim.start()

    def _track_hover_float(self, pos):
        item = self.itemAt(pos)
        if item is None:
            self._set_float_key(None)
            return
        kind = item.data(0, ROLE_KIND)
        if kind not in ("session", "mindmap", "document", "folder"):
            self._set_float_key(None)
            return
        self._set_float_key((kind, item.data(0, ROLE_ID)))

    def viewportEvent(self, event):
        if event.type() == QEvent.Leave:
            self._set_float_key(None)
            self._hide_note_tip()
            if self._match_btn_hover_fid is not None:
                self._match_btn_hover_fid = None
                self.viewport().unsetCursor()
                self.viewport().update()
            if self._import_btn_hover_fid is not None:
                self._import_btn_hover_fid = None
                self.viewport().unsetCursor()
                self.viewport().update()
        return super().viewportEvent(event)

    def _note_text(self, item) -> str:
        if item is None or item.data(0, ROLE_KIND) != "session":
            return ""
        return (item.toolTip(0) or "").strip()

    def _note_bubble_widget(self) -> QLabel:
        host = self.viewport()
        if self._note_bubble is not None and self._note_bubble.parent() is host:
            return self._note_bubble
        if self._note_bubble is not None:
            self._note_bubble.deleteLater()
        tip = QLabel(host)
        tip.setObjectName("sessionNoteTip")
        tip.setWordWrap(True)
        tip.setMaximumWidth(260)
        tip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        tip.setAttribute(Qt.WA_StyledBackground, True)
        tip.setStyleSheet(
            "#sessionNoteTip {"
            " background: rgba(40, 44, 60, 0.94); color: #eef1fb;"
            " border: none; padding: 6px 10px; border-radius: 8px;"
            " font-size: 12px;"
            "}"
        )
        tip.hide()
        self._note_bubble = tip
        return tip

    def _track_note_tip(self, event):
        if hasattr(event, "globalPosition"):
            self._note_tip_pos = event.globalPosition().toPoint()
        else:
            self._note_tip_pos = event.globalPos()
        item = self.itemAt(event.position().toPoint())
        note = self._note_text(item)
        if not note:
            self._hide_note_tip()
            return
        if item is self._note_tip_shown:
            self._place_note_tip()
            return
        if item is self._note_tip_item and self._note_tip_timer.isActive():
            return
        if self._note_tip_shown is not None:
            self._note_tip_shown = None
            if self._note_bubble is not None:
                self._note_bubble.hide()
        self._note_tip_item = item
        self._note_tip_timer.start(NOTE_TIP_SHOW_MS)

    def _show_note_tip(self):
        item = self._note_tip_item
        note = self._note_text(item)
        if not note:
            self._hide_note_tip()
            return
        tip = self._note_bubble_widget()
        tip.setText(note)
        tip.adjustSize()
        self._place_note_tip()
        tip.show()
        tip.raise_()
        self._note_tip_shown = item

    def _place_note_tip(self):
        tip = self._note_bubble
        if tip is None:
            return
        host = tip.parentWidget()
        if host is None:
            return
        br = tip.size()
        pos = host.mapFromGlobal(self._note_tip_pos + QPoint(14, 18))
        x = min(max(8, pos.x()), max(8, host.width() - br.width() - 8))
        y = pos.y()
        if y + br.height() > host.height() - 8:
            above = host.mapFromGlobal(self._note_tip_pos + QPoint(14, -10))
            y = above.y() - br.height()
        tip.move(x, max(8, y))

    def _hide_note_tip(self):
        self._note_tip_timer.stop()
        self._note_tip_item = None
        self._note_tip_shown = None
        if self._note_bubble is not None:
            self._note_bubble.hide()

    def _match_button_at(self, pos):
        item = self.itemAt(pos)
        if item is None or item.data(0, ROLE_KIND) != "folder":
            return None
        if match_button_rect(self.visualItemRect(item)).contains(pos):
            return item.data(0, ROLE_ID)
        return None

    def _import_button_at(self, pos):
        item = self.itemAt(pos)
        if item is None or item.data(0, ROLE_KIND) != "folder":
            return None
        if import_button_rect(self.visualItemRect(item)).contains(pos):
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
        self._press_on_import_btn = False
        if event.button() == Qt.LeftButton:
            import_fid = self._import_button_at(event.position().toPoint())
            self._press_on_import_btn = import_fid is not None
            if self._press_on_import_btn:
                event.accept()
                return
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
        import_fid = self._import_button_at(event.position().toPoint())
        if fid != self._match_btn_hover_fid:
            self._match_btn_hover_fid = fid
            self.viewport().update()
        if import_fid != self._import_btn_hover_fid:
            self._import_btn_hover_fid = import_fid
            self.viewport().update()
        if fid is not None or import_fid is not None:
            self.viewport().setCursor(Qt.PointingHandCursor)
        elif self._matchable_session_at(event.position().toPoint()) is not None:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().unsetCursor()
        self._track_hover_float(event.position().toPoint())
        self._track_note_tip(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_on_import_btn:
            self._press_on_import_btn = False
            fid = self._import_button_at(event.position().toPoint())
            if fid is not None:
                self.import_clicked.emit(fid)
            event.accept()
            return
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
        self._set_float_key(None)
        if self._match_btn_hover_fid is not None:
            self._match_btn_hover_fid = None
            self.viewport().unsetCursor()
            self.viewport().update()
        if self._import_btn_hover_fid is not None:
            self._import_btn_hover_fid = None
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

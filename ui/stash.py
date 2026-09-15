"""窗口底部的常用栏（密钥、账号、提示词）。"""

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.style import apply_glass_shadow

STASH_KINDS = (
    ("prompt", "提示词"),
    ("key", "密钥"),
    ("account", "账号密码"),
)
STASH_HINT = {
    "key": ("粘贴密钥", "还没有密钥"),
    "account": ("账号和密码", "还没有账号密码"),
    "prompt": ("提示词", "还没有提示词"),
}


class StashRow(QFrame):
    removed = Signal(int)
    copy_requested = Signal(str)
    title_changed = Signal(int, str)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item_id = item["id"]
        self._editing = False
        self._ignore_release = False
        self._title_text = (item.get("title") or "").strip()
        self._body_text = (item.get("body") or "").strip()
        self.setObjectName("todoRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(200)
        self.setMaximumWidth(280)

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._copy)

        self._title = QLabel(self._title_text)
        self._title.setObjectName("todoText")
        self._title.setWordWrap(True)
        self._title.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._body = QLabel(self._body_text)
        self._body.setObjectName("todoNote")
        self._body.setWordWrap(True)
        self._body.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._body.setVisible(bool(self._body_text))

        self._edit = QLineEdit()
        self._edit.setObjectName("todoNoteEdit")
        self._edit.setPlaceholderText("编辑内容")
        self._edit.hide()
        self._edit.editingFinished.connect(self._finish_edit)
        self._edit.installEventFilter(self)

        btn = QToolButton()
        btn.setObjectName("todoDelete")
        btn.setText("×")
        btn.setAutoRaise(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self.removed.emit(self.item_id))
        self._delete = btn

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(self._title)
        text_col.addWidget(self._body)
        text_col.addWidget(self._edit)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 6, 8)
        lay.setSpacing(6)
        lay.addLayout(text_col, 1)
        lay.addWidget(btn, 0, Qt.AlignTop)

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or self._hit_chrome(ev):
            super().mouseReleaseEvent(ev)
            return
        if self._editing:
            ev.accept()
            return
        if self._ignore_release:
            self._ignore_release = False
            ev.accept()
            return
        self._click_timer.start(QApplication.doubleClickInterval())
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.LeftButton or self._hit_chrome(ev):
            super().mouseDoubleClickEvent(ev)
            return
        self._click_timer.stop()
        self._ignore_release = True
        self._begin_edit()
        ev.accept()

    def _hit_chrome(self, ev) -> bool:
        pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        w = self.childAt(pos)
        while w is not None and w is not self:
            if w is self._delete or w is self._edit:
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, ev):
        if obj is self._edit and ev.type() == QEvent.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self._cancel_edit()
                return True
        return super().eventFilter(obj, ev)

    def _copy_text(self) -> str:
        return self._body_text or self._title_text

    def _copy(self):
        if self._editing:
            return
        text = self._copy_text()
        if text:
            self.copy_requested.emit(text)

    def _begin_edit(self):
        if self._editing:
            return
        self._editing = True
        self._edit_origin = self._copy_text()
        self._title.hide()
        self._body.hide()
        self._edit.blockSignals(True)
        self._edit.setText(self._edit_origin)
        self._edit.blockSignals(False)
        self._edit.show()
        QTimer.singleShot(0, self._focus_edit)

    def _focus_edit(self):
        if not self._editing:
            return
        self._edit.setFocus()
        self._edit.selectAll()

    def _finish_edit(self):
        if not self._editing:
            return
        text = self._edit.text().strip()
        self._editing = False
        self._edit.hide()
        if not text:
            self._apply_text(self._edit_origin)
            return
        self._apply_text(text)
        if text != self._edit_origin:
            self.title_changed.emit(self.item_id, text)

    def _cancel_edit(self):
        if not self._editing:
            return
        self._editing = False
        self._edit.hide()
        self._apply_text(self._edit_origin)

    def _apply_text(self, text: str):
        self._title_text = (text or "").strip()
        self._body_text = ""
        self._title.setText(self._title_text)
        self._title.setVisible(True)
        self._body.clear()
        self._body.hide()


class StashPanel(QFrame):
    """窗口底部的常用栏：左分类，右列表。"""

    copied = Signal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._kind = "prompt"
        self.setObjectName("stashBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(148)

        nav = QFrame()
        nav.setObjectName("stashNav")
        nav.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(nav)
        nav.setFixedSize(132, 132)
        self._kind_group = QButtonGroup(self)
        self._kind_group.setExclusive(True)
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(8, 10, 8, 10)
        nav_lay.setSpacing(6)
        for i, (key, label) in enumerate(STASH_KINDS):
            btn = QToolButton()
            btn.setObjectName("stashNavBtn")
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if i == 0:
                btn.setChecked(True)
            self._kind_group.addButton(btn)
            btn.clicked.connect(lambda _=False, k=key: self._set_kind(k))
            nav_lay.addWidget(btn)

        glass = QFrame()
        glass.setObjectName("todoGlass")
        glass.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(glass)

        self._input = QLineEdit()
        self._input.setObjectName("todoInput")
        self._input.setFixedWidth(180)
        self._input.returnPressed.connect(self._add)

        add_btn = QToolButton()
        add_btn.setObjectName("todoAdd")
        add_btn.setText("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setToolTip("添加到当前分类")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)
        input_row.addWidget(self._input, 0)
        input_row.addWidget(add_btn, 0, Qt.AlignVCenter)
        input_row.addStretch(1)

        self._empty = QLabel()
        self._empty.setObjectName("todoEmpty")
        self._empty.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._list = QWidget()
        self._list.setObjectName("todoList")
        self._list_lay = QHBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 4, 0)
        self._list_lay.setSpacing(8)
        self._list_lay.addWidget(self._empty)
        self._list_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("todoScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(self._list)

        body = QVBoxLayout(glass)
        body.setContentsMargins(12, 10, 12, 10)
        body.setSpacing(8)
        body.addLayout(input_row)
        body.addWidget(scroll, 1)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(10)
        inner.addWidget(nav, 0, Qt.AlignVCenter)
        inner.addWidget(glass, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(0)
        lay.addLayout(inner, 1)

        self._apply_kind_hints()
        self.reload()

    def _set_kind(self, kind: str):
        if kind == self._kind:
            return
        self._kind = kind
        self._apply_kind_hints()
        self.reload()

    def _apply_kind_hints(self):
        name_ph, empty = STASH_HINT.get(self._kind, STASH_HINT["key"])
        self._input.setPlaceholderText(name_ph)
        self._empty.setText(empty)

    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._db.add_stash(text, self._kind)
        self._input.clear()
        self.reload()

    def _remove(self, item_id: int):
        self._db.delete_stash(item_id)
        self.reload()

    def _set_title(self, item_id: int, title: str):
        self._db.set_stash_title(item_id, title)

    def reload(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is self._empty:
                continue
            if w is not None:
                w.deleteLater()
        rows = self._db.list_stash(self._kind)
        if not rows:
            self._empty.setVisible(True)
            if self._list_lay.indexOf(self._empty) < 0:
                self._list_lay.insertWidget(0, self._empty)
            return
        self._empty.setVisible(False)
        for item in rows:
            w = StashRow(item)
            w.removed.connect(self._remove)
            w.copy_requested.connect(self.copied)
            w.title_changed.connect(self._set_title)
            self._list_lay.insertWidget(self._list_lay.count() - 1, w)


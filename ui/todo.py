"""窗口最右侧的待办栏（液态玻璃风）。"""

import re
from datetime import date

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import MATCH_COLORS

TODO_PANEL_W = 260
DATE_COLOR_CYCLE = list(MATCH_COLORS.keys())
TODO_MARKS = {
    "later": "延后",
    "skip": "不做了",
}
_DATED_TODO = re.compile(
    r"^【?\s*(\d{4})-(\d{1,2})-(\d{1,2})-(.+?)\s*】?$"
)


def parse_dated_todo(content: str):
    """识别「年-月-日-事情」，返回 (日期信息, 展示正文)。"""
    text = (content or "").strip()
    m = _DATED_TODO.match(text)
    if not m:
        return None, text
    try:
        dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None, text
    task = m.group(4).strip().lstrip("-").strip()
    if not task:
        return None, text
    tone = DATE_COLOR_CYCLE[dt.toordinal() % len(DATE_COLOR_CYCLE)]
    return {
        "date": dt,
        "label": dt.strftime("%Y-%m-%d"),
        "tone": tone,
    }, task


def _group_todos(todos: list) -> list:
    """同一天的待办收成一组；无日期的单独一条。日期新的在前。"""
    buckets = {}
    undated = []
    for todo in todos:
        info, _ = parse_dated_todo(todo["content"])
        if info is None:
            undated.append(todo)
            continue
        buckets.setdefault(info["date"], {"info": info, "todos": []})
        buckets[info["date"]]["todos"].append(todo)
    blocks = []
    for dt in sorted(buckets.keys(), reverse=True):
        group = buckets[dt]
        group["todos"].sort(
            key=lambda t: (
                3 if t.get("done") else {"skip": 2, "later": 1}.get(t.get("mark") or "", 0),
                t.get("sort_order") or 0,
                -t["id"],
            )
        )
        blocks.append({"kind": "date", **group})
    for todo in undated:
        blocks.append({"kind": "plain", "todo": todo})
    return blocks


class TodoRow(QFrame):
    toggled = Signal(int, bool)
    removed = Signal(int)
    note_changed = Signal(int, str)
    mark_changed = Signal(int, str)

    def __init__(self, todo: dict, parent=None):
        super().__init__(parent)
        self.todo_id = todo["id"]
        done = bool(todo["done"])
        self._editing = False
        self._note_text = (todo.get("note") or "").strip()
        self._mark_kind = (todo.get("mark") or "").strip()
        if self._mark_kind not in TODO_MARKS:
            self._mark_kind = ""
        self.setObjectName("todoRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("done", "true" if done else "false")
        self.setProperty("mark", self._mark_kind)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("单击添加备注 · 右键标记延后或不做了")
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self._mark = QLabel()
        self._mark.setObjectName("todoMark")
        self._mark.setAlignment(Qt.AlignCenter)
        self._mark.setAttribute(Qt.WA_StyledBackground, True)
        self._mark.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._check = QToolButton()
        self._check.setObjectName("todoCheck")
        self._check.setCheckable(True)
        self._check.setChecked(done)
        self._check.setText("✓" if done else "")
        self._check.setFixedSize(22, 22)
        self._check.setToolTip("勾选标记完成")
        self._check.setCursor(Qt.PointingHandCursor)
        self._check.toggled.connect(self._on_check)

        _dated, display = parse_dated_todo(todo["content"])
        self._text = QLabel(display)
        self._text.setObjectName("todoText")
        self._text.setWordWrap(True)
        self._text.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._apply_done_text(done)

        self._note = QLabel()
        self._note.setObjectName("todoNote")
        self._note.setWordWrap(True)
        self._note.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._apply_note(self._note_text)

        self._note_edit = QLineEdit()
        self._note_edit.setObjectName("todoNoteEdit")
        self._note_edit.setPlaceholderText("添加备注")
        self._note_edit.hide()
        self._note_edit.editingFinished.connect(self._finish_note)
        self._note_edit.installEventFilter(self)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        body.addWidget(self._text)
        body.addWidget(self._note)
        body.addWidget(self._note_edit)

        btn = QToolButton()
        btn.setObjectName("todoDelete")
        btn.setText("×")
        btn.setToolTip("删除")
        btn.setAutoRaise(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self.removed.emit(self.todo_id))
        self._delete = btn

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        content.addWidget(self._check, 0, Qt.AlignTop)
        content.addLayout(body, 1)
        content.addWidget(btn, 0, Qt.AlignTop)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 6, 8)
        lay.setSpacing(6)
        lay.addWidget(self._mark)
        lay.addLayout(content)
        self._apply_mark(self._mark_kind, emit=False)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and not self._hit_chrome(ev):
            self._begin_edit()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        later = menu.addAction("【延后】")
        later.setCheckable(True)
        later.setChecked(self._mark_kind == "later")
        skip = menu.addAction("【不做了】")
        skip.setCheckable(True)
        skip.setChecked(self._mark_kind == "skip")
        clear = None
        if self._mark_kind:
            menu.addSeparator()
            clear = menu.addAction("取消标记")
        chosen = menu.exec(ev.globalPos())
        if chosen is later:
            self._apply_mark("" if self._mark_kind == "later" else "later")
        elif chosen is skip:
            self._apply_mark("" if self._mark_kind == "skip" else "skip")
        elif clear is not None and chosen is clear:
            self._apply_mark("")

    def _hit_chrome(self, ev) -> bool:
        pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        w = self.childAt(pos)
        while w is not None and w is not self:
            if w is self._check or w is self._delete or w is self._note_edit:
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, ev):
        if obj is self._note_edit and ev.type() == QEvent.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self._cancel_edit()
                return True
        return super().eventFilter(obj, ev)

    def _begin_edit(self):
        if self._editing:
            return
        self._editing = True
        self._edit_origin = self._note_text
        self._note.hide()
        self._note_edit.setText(self._note_text)
        self._note_edit.show()
        self._note_edit.setFocus()
        self._note_edit.selectAll()

    def _finish_note(self):
        if not self._editing:
            return
        text = self._note_edit.text().strip()
        self._editing = False
        self._note_edit.hide()
        self._apply_note(text)
        if text != self._edit_origin:
            self.note_changed.emit(self.todo_id, text)

    def _cancel_edit(self):
        if not self._editing:
            return
        self._editing = False
        self._note_edit.hide()
        self._apply_note(self._edit_origin)

    def _apply_note(self, text: str):
        self._note_text = (text or "").strip()
        self._note.setText(self._note_text)
        self._note.setVisible(bool(self._note_text))

    def _apply_mark(self, kind: str, emit: bool = True):
        kind = kind if kind in TODO_MARKS else ""
        changed = kind != self._mark_kind
        self._mark_kind = kind
        self.setProperty("mark", kind)
        self._mark.setProperty("kind", kind)
        if kind:
            self._mark.setText(TODO_MARKS[kind])
            self._mark.setVisible(True)
        else:
            self._mark.clear()
            self._mark.setVisible(False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._mark.style().unpolish(self._mark)
        self._mark.style().polish(self._mark)
        if emit and changed:
            self.mark_changed.emit(self.todo_id, kind)

    def _on_check(self, on: bool):
        self._check.setText("✓" if on else "")
        self.setProperty("done", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_done_text(on)
        self.toggled.emit(self.todo_id, on)

    def _apply_done_text(self, done: bool):
        font = self._text.font()
        font.setStrikeOut(done)
        self._text.setFont(font)


class TodoDateGroup(QFrame):
    """同一天的待办归在一个日期玻璃框下。"""

    toggled = Signal(int, bool)
    removed = Signal(int)
    note_changed = Signal(int, str)
    mark_changed = Signal(int, str)

    def __init__(self, info: dict, todos: list, parent=None):
        super().__init__(parent)
        self.setObjectName("todoGroup")
        self.setAttribute(Qt.WA_StyledBackground, True)

        chip = QLabel(info["label"])
        chip.setObjectName("todoDate")
        chip.setAttribute(Qt.WA_StyledBackground, True)
        chip.setAlignment(Qt.AlignCenter)
        chip.setProperty("tone", info["tone"])
        chip.setToolTip(MATCH_COLORS[info["tone"]]["name"])
        chip.style().unpolish(chip)
        chip.style().polish(chip)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        lay.addWidget(chip)
        for todo in todos:
            row = TodoRow(todo)
            row.setObjectName("todoRowInner")
            row.style().unpolish(row)
            row.style().polish(row)
            row.toggled.connect(self.toggled)
            row.removed.connect(self.removed)
            row.note_changed.connect(self.note_changed)
            row.mark_changed.connect(self.mark_changed)
            lay.addWidget(row)


class TodoPanel(QFrame):
    """独立于会话树 / 聊天区的待办侧栏。"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self.setObjectName("todoDock")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setFixedWidth(TODO_PANEL_W)

        glass = QFrame()
        glass.setObjectName("todoGlass")
        glass.setAttribute(Qt.WA_StyledBackground, True)

        title = QLabel("待办")
        title.setObjectName("todoTitle")
        title.setAlignment(Qt.AlignCenter)

        hint = QLabel("年-月-日-事情 · 单击待办可加备注")
        hint.setObjectName("todoHint")
        hint.setAlignment(Qt.AlignCenter)

        self._input = QLineEdit()
        self._input.setObjectName("todoInput")
        self._input.setPlaceholderText("2026-09-11-事情")
        self._input.returnPressed.connect(self._add)

        add_btn = QToolButton()
        add_btn.setObjectName("todoAdd")
        add_btn.setText("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setToolTip("添加待办")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(add_btn, 0, Qt.AlignVCenter)

        self._empty = QLabel("还没有待办")
        self._empty.setObjectName("todoEmpty")
        self._empty.setAlignment(Qt.AlignCenter)

        self._list = QWidget()
        self._list.setObjectName("todoList")
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(8)
        self._list_lay.addWidget(self._empty)
        self._list_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("todoScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self._list)
        scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._scroll = scroll

        inner = QVBoxLayout(glass)
        inner.setContentsMargins(10, 12, 10, 12)
        inner.setSpacing(10)
        inner.addWidget(title, 0, Qt.AlignHCenter)
        inner.addWidget(hint)
        inner.addLayout(input_row)
        inner.addWidget(scroll, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 10, 12)
        lay.setSpacing(0)
        lay.addWidget(glass, 1)

        self.reload()

    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._db.add_todo(text)
        self._input.clear()
        self.reload()

    def _toggle(self, todo_id: int, done: bool):
        self._db.set_todo_done(todo_id, done)
        self.reload()

    def _remove(self, todo_id: int):
        self._db.delete_todo(todo_id)
        self.reload()

    def _set_note(self, todo_id: int, note: str):
        self._db.set_todo_note(todo_id, note)

    def _set_mark(self, todo_id: int, mark: str):
        self._db.set_todo_mark(todo_id, mark)

    def reload(self):
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is self._empty:
                continue
            if w is not None:
                w.deleteLater()
        todos = self._db.list_todos()
        if not todos:
            self._empty.setVisible(True)
            if self._list_lay.indexOf(self._empty) < 0:
                self._list_lay.insertWidget(0, self._empty)
            return
        self._empty.setVisible(False)
        for block in _group_todos(todos):
            if block["kind"] == "date":
                w = TodoDateGroup(block["info"], block["todos"])
            else:
                w = TodoRow(block["todo"])
            w.toggled.connect(self._toggle)
            w.removed.connect(self._remove)
            w.note_changed.connect(self._set_note)
            w.mark_changed.connect(self._set_mark)
            self._list_lay.insertWidget(self._list_lay.count() - 1, w)
